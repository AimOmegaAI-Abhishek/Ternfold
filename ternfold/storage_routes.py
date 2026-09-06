"""Authenticated direct-upload routes. No customer file traverses a Vercel request."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import uuid

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select

from .db import get_db
from .models import AuditEvent, Case, SourceDocument, now_utc
from .storage import StorageUnavailable
from .storage_upload_models import UploadIntent

CATEGORIES = {'current_supplier', 'accepted_order', 'original_costing', 'revised_supplier', 'actual_cost'}
EXTENSIONS = {'.pdf', '.png', '.jpg', '.jpeg', '.csv'}


def active_reservations(db, case_id):
    return list(db.scalars(select(UploadIntent).where(UploadIntent.case_id == case_id, UploadIntent.status == 'PENDING', UploadIntent.expires_at > now_utc())))


def check_capacity(documents, reservations, size):
    if len(documents) + len(reservations) >= 10:
        raise ValueError('This case has 10 retained files or active uploads. Finish pending uploads or wait for their two-hour reservation to expire. Existing evidence is preserved.')
    if sum(d.size_bytes for d in documents) + sum(r.size_bytes for r in reservations) + size > 50_000_000:
        raise ValueError('Adding this file would exceed the 50 MB case limit, including retained files and active uploads. Existing evidence is preserved.')


def store_document(db, case, user, *, filename, category, validity_end, data, storage, validate_upload, parse_csv_lines):
    """Caller holds the case row lock and has checked capacity and permissions."""
    ctype = validate_upload(filename, '', data)
    parsed = parse_csv_lines(data) if Path(filename).suffix.lower() == '.csv' else None
    digest = hashlib.sha256(data).hexdigest()
    duplicate = db.scalar(select(SourceDocument).where(SourceDocument.case_id == case.id, SourceDocument.sha256 == digest))
    if duplicate:
        return duplicate
    key, digest = storage.put(f'org/{case.organization_id}/case/{case.id}', Path(filename).suffix, data)
    if category != 'actual_cost':
        case.working_revision += 1
        case.current_calculation_id = None
        case.financial_status = 'NOT_EVALUATED'
        case.workflow_status = 'NEEDS_INPUT'
        case.next_actor = 'Operations / reviewer'
        working = case.working_data.copy()
        # Uploading new material never inherits an earlier confirmation.
        for flag in ('tax_basis_confirmed', 'matching_confirmed', 'applicability_confirmed', 'baseline_comparable'):
            working[flag] = False
        if parsed is not None:
            working['lines'] = parsed
            for side in ('original', 'current'):
                for component in ('freight', 'handling', 'other'):
                    working.setdefault(f'{side}_{component}_status', 'unknown')
        case.working_data = working
    source = SourceDocument(case_id=case.id, organization_id=case.organization_id, category=category, filename=filename, content_type=ctype, size_bytes=len(data), sha256=digest, storage_key=key, uploaded_by_id=user.id, validity_end=validity_end, revision_added=case.working_revision)
    db.add(source)
    db.flush()
    db.add(AuditEvent(organization_id=case.organization_id, case_id=case.id, actor_id=user.id, action='DOCUMENT_UPLOADED', detail={'document_id': source.id, 'category': category, 'hash': digest}))
    return source


def cleanup_expired_uploads(db, storage):
    """Run from the retention job. Repeated cleanup also catches late signed uploads."""
    count = 0
    for intent in db.scalars(select(UploadIntent).where(UploadIntent.status == 'PENDING', UploadIntent.expires_at <= now_utc())):
        storage.delete(intent.storage_key)
        if intent.status == 'PENDING':
            intent.status = 'EXPIRED'
        count += 1
    db.commit()
    return count


def register_storage_routes(app, *, require_user, verify_csrf, case_access, validate_upload, parse_csv_lines, storage):
    @app.get('/storage/upload-capability')
    def capability(request: Request, db=Depends(get_db)):
        require_user(request, db)
        from .storage import UnavailableStorage
        if isinstance(storage, UnavailableStorage):
            raise HTTPException(503, 'Private evidence storage is not configured. Set the Supabase storage credentials before uploading.')
        return {'direct': storage.direct_uploads}

    @app.post('/cases/{case_id}/uploads/reserve')
    async def reserve(case_id: str, request: Request, db=Depends(get_db)):
        user = require_user(request, db)
        case, _, _ = case_access(db, user, case_id, 'customer')
        body = await request.json()
        verify_csrf(request, db, body.get('csrf', ''))
        if not storage.direct_uploads:
            raise HTTPException(503, 'Private direct uploads are unavailable. Configure Supabase storage before deploying.')
        case = db.scalar(select(Case).where(Case.id == case.id).with_for_update().execution_options(populate_existing=True))
        if case.unsupported_reason:
            raise HTTPException(422, 'This case is outside the supported scope.')
        try:
            filename = str(body.get('filename', ''))
            if not filename or len(filename) > 255 or '/' in filename or '\\' in filename or any(ord(c) < 32 for c in filename):
                raise ValueError('Use a filename without path separators or control characters, up to 255 characters.')
            if Path(filename).suffix.lower() not in EXTENSIONS:
                raise ValueError('Use PDF, JPG, PNG or the fixed UTF-8 CSV template.')
            size = body.get('size_bytes')
            if type(size) is not int or not 0 < size <= 10_000_000:
                raise ValueError('Each upload must contain between 1 and 10000000 bytes (10 MB).')
            digest = str(body.get('sha256', ''))
            if not re.fullmatch('[0-9a-f]{64}', digest):
                raise ValueError('The file checksum is missing. Select the file again.')
            category = body.get('category')
            if category not in CATEGORIES:
                raise ValueError('Choose a supported document type.')
            request_key = str(body.get('request_key', ''))
            if not re.fullmatch('[A-Za-z0-9_-]{8,80}', request_key):
                raise ValueError('The upload request identifier is invalid.')
            valid = datetime.fromisoformat(body['validity_end']) if body.get('validity_end') else None
            if valid and valid.tzinfo is None:
                # Browser datetime-local values use the product's India timezone.
                from zoneinfo import ZoneInfo
                valid = valid.replace(tzinfo=ZoneInfo('Asia/Kolkata'))
            payload = hashlib.sha256(json.dumps({k: body.get(k) for k in ('filename', 'size_bytes', 'sha256', 'category', 'validity_end')}, sort_keys=True).encode()).hexdigest()
            intent = db.scalar(select(UploadIntent).where(UploadIntent.case_id == case.id, UploadIntent.request_key == request_key))
            if intent:
                if intent.payload_hash != payload or intent.uploaded_by_id != user.id:
                    raise HTTPException(409, 'This upload identifier was already used for another request.')
                if intent.status == 'FINALIZED':
                    return {'document_id': intent.document_id, 'complete': True, 'next_url': f'/cases/{case.id}'}
                if intent.expires_at <= now_utc() or intent.status != 'PENDING':
                    raise HTTPException(409, 'This upload reservation expired. Select the file again.')
            else:
                docs = list(db.scalars(select(SourceDocument).where(SourceDocument.case_id == case.id)))
                duplicate = next((d for d in docs if d.sha256 == digest), None)
                if duplicate:
                    return {'document_id': duplicate.id, 'complete': True, 'next_url': f'/cases/{case.id}'}
                check_capacity(docs, active_reservations(db, case.id), size)
                identifier = str(uuid.uuid4())
                intent = UploadIntent(id=identifier, case_id=case.id, organization_id=case.organization_id, uploaded_by_id=user.id, request_key=request_key, payload_hash=payload, filename=filename, size_bytes=size, sha256=digest, category=category, validity_end=valid, storage_key=f'org/{case.organization_id}/case/{case.id}/pending/{identifier}{Path(filename).suffix.lower()}', expires_at=now_utc() + timedelta(hours=2, minutes=5))
                db.add(intent)
                db.flush()
            signed = storage.signed_upload(intent.storage_key)
            intent.expires_at = now_utc() + timedelta(hours=2, minutes=5)
            db.commit()
            return {'intent_id': intent.id, 'upload_url': signed, 'complete': False}
        except (ValueError, StorageUnavailable, FileNotFoundError) as exc:
            db.rollback()
            raise HTTPException(422, str(exc)) from None

    @app.post('/cases/{case_id}/uploads/{intent_id}/finalize')
    async def finalize(case_id: str, intent_id: str, request: Request, db=Depends(get_db)):
        user = require_user(request, db)
        case, _, _ = case_access(db, user, case_id, 'customer')
        body = await request.json()
        verify_csrf(request, db, body.get('csrf', ''))
        case = db.scalar(select(Case).where(Case.id == case.id).with_for_update().execution_options(populate_existing=True))
        if case.unsupported_reason:
            raise HTTPException(422, 'This case is outside the supported scope.')
        intent = db.get(UploadIntent, intent_id)
        if not intent or intent.case_id != case.id or intent.uploaded_by_id != user.id:
            raise HTTPException(404)
        if intent.status == 'FINALIZED':
            return {'complete': True, 'document_id': intent.document_id, 'next_url': f'/cases/{case.id}'}
        if intent.status != 'PENDING' or intent.expires_at <= now_utc():
            raise HTTPException(409, 'Upload reservation expired. Select the file again.')
        try:
            raw = storage.read(intent.storage_key, max_bytes=10_000_000)
            if len(raw) != intent.size_bytes or hashlib.sha256(raw).hexdigest() != intent.sha256:
                raise ValueError('The uploaded bytes do not match the selected file. Select the original file again.')
            source = store_document(db, case, user, filename=intent.filename, category=intent.category, validity_end=intent.validity_end, data=raw, storage=storage, validate_upload=validate_upload, parse_csv_lines=parse_csv_lines)
            intent.status = 'FINALIZED'
            intent.document_id = source.id
            db.commit()
            # Safe to retry cleanup after a commit; final evidence uses another immutable key.
            try:
                storage.delete(intent.storage_key)
            except (StorageUnavailable, FileNotFoundError):
                pass
            return {'complete': True, 'document_id': source.id, 'next_url': f'/cases/{case.id}'}
        except (ValueError, StorageUnavailable, FileNotFoundError) as exc:
            db.rollback()
            raise HTTPException(422, str(exc)) from None
