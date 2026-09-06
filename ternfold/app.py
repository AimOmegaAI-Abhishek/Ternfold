from __future__ import annotations
import csv, hashlib, io, json, os
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo
import pypdfium2 as pdfium
from PIL import Image
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pypdf import PdfReader
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from .ai import extraction_status, propose_from_text
from .auth import COOKIE, create_session, csrf_for, current_user, password_ok, require_user, token_hash, verify_csrf
from .db import get_db
from .finance import CalculationBlocked, calculate, completeness, dec, fmt_money, fmt_pct, line_amount
from .fixtures import add_doc, demo_data
from .models import (AuditEvent,CalculationVersion,Case,Decision,EvidenceReference,ExtractionDraft,InputQuestion,Membership,Organization,Outcome,ReportArtifact,ReviewerAssignment,Review,SessionToken,SourceDocument,User,now_utc)
from .reports import decision_pdf
from .storage import storage

ROOT=Path(__file__).resolve().parent
app=FastAPI(title="Ternfold Margin Decision Desk",docs_url=None,redoc_url=None)
app.mount("/static",StaticFiles(directory=ROOT/"static"),name="static")
templates=Jinja2Templates(directory=ROOT/"templates")
templates.env.filters.update(money=fmt_money,pct=fmt_pct)
templates.env.filters["delta_money"]=lambda pair: fmt_money(Decimal(pair[0])-Decimal(pair[1]))
templates.env.filters["ist"] = lambda value: value.astimezone(ZoneInfo("Asia/Kolkata")).strftime("%d %b %Y, %H:%M IST")
templates.env.filters["ist_short"] = lambda value: value.astimezone(ZoneInfo("Asia/Kolkata")).strftime("%d %b · %H:%M IST")

def flash_redirect(path:str,message:str,kind:str="success")->RedirectResponse:
    return RedirectResponse(f"{path}{'&' if '?' in path else '?'}notice={quote(message)}&kind={kind}",status_code=303)

def identity(request:Request,db:Session)->tuple[User,Membership|None,bool]:
    user=require_user(request,db)
    membership=db.scalar(select(Membership).where(Membership.user_id==user.id,Membership.active.is_(True)))
    reviewer=db.scalar(select(ReviewerAssignment).where(ReviewerAssignment.user_id==user.id,ReviewerAssignment.active.is_(True))) is not None
    return user,membership,reviewer

def case_access(db:Session,user:User,case_id:str,write_role:str|None=None)->tuple[Case,Membership|None,bool]:
    case=db.get(Case,case_id)
    if not case: raise HTTPException(404,"Case not found")
    membership=db.scalar(select(Membership).where(Membership.organization_id==case.organization_id,Membership.user_id==user.id,Membership.active.is_(True)))
    reviewer=db.scalar(select(ReviewerAssignment).where(ReviewerAssignment.organization_id==case.organization_id,ReviewerAssignment.user_id==user.id,ReviewerAssignment.active.is_(True))) is not None
    if not membership and not reviewer: raise HTTPException(404,"Case not found")
    if write_role=="reviewer" and not reviewer: raise HTTPException(403,"Only the assigned reviewer can publish.")
    if write_role=="customer" and not membership: raise HTTPException(403,"Customer membership required.")
    if write_role=="owner" and (not membership or membership.role!="OWNER" or case.decision_owner_id!=user.id): raise HTTPException(403,"Only the named customer decision owner can record this decision.")
    return case,membership,reviewer

def context(request:Request,db:Session,user:User|None=None,**extra)->dict:
    return {"request":request,"user":user,"csrf":csrf_for(request,db) if user else "","notice":request.query_params.get("notice"),"notice_kind":request.query_params.get("kind","success"),"ai":extraction_status(),"demo_date":os.getenv("TERNFOLD_DEMO_DATE","2026-09-03"),**extra}

def effective_working_data(db:Session,case:Case)->dict:
    """Evaluate source validity for the current working revision without rewriting history."""
    working=case.working_data.copy()
    material=list(db.scalars(select(SourceDocument).where(SourceDocument.case_id==case.id,SourceDocument.category.in_(["current_supplier","revised_supplier"]),SourceDocument.deleted_at.is_(None),SourceDocument.revision_added<=case.working_revision)))
    if material:
        newest_revision=max(doc.revision_added for doc in material)
        active=[doc for doc in material if doc.revision_added==newest_revision]
        working["evidence_expired"]=bool(working.get("evidence_expired")) or any(doc.validity_end is not None and doc.validity_end < case.proposed_purchase_at for doc in active)
    return working

@app.get("/health")
def health(db:Session=Depends(get_db)): db.execute(select(1)); return {"status":"ok","database":"postgresql","ai":extraction_status()["available"]}

@app.get("/login",response_class=HTMLResponse)
def login_page(request:Request,db:Session=Depends(get_db)):
    if current_user(request,db): return RedirectResponse("/",303)
    return templates.TemplateResponse(request=request,name="login.html",context=context(request,db))

@app.post("/login")
def login(request:Request,email:str=Form(...),password:str=Form(...),db:Session=Depends(get_db)):
    user=db.scalar(select(User).where(func.lower(User.email)==email.strip().lower()))
    if not user or not password_ok(user.password_hash,password): return templates.TemplateResponse(request=request,name="login.html",context=context(request,db,error="Email or password is incorrect."),status_code=400)
    raw,_=create_session(db,user); db.commit(); response=RedirectResponse("/",303)
    response.set_cookie(COOKIE,raw,httponly=True,samesite="lax",secure=os.getenv("TERNFOLD_SECURE_COOKIES")=="1",max_age=43200)
    return response

@app.post("/logout")
def logout(request:Request,csrf:str=Form(...),db:Session=Depends(get_db)):
    user=require_user(request,db); verify_csrf(request,db,csrf)
    raw=request.cookies.get(COOKIE); row=db.scalar(select(SessionToken).where(SessionToken.token_hash==token_hash(raw))) if raw else None
    if row: row.revoked_at=now_utc(); db.commit()
    response=RedirectResponse("/login",303); response.delete_cookie(COOKIE); return response

@app.get("/",response_class=HTMLResponse)
def case_list(request:Request,db:Session=Depends(get_db)):
    user,membership,reviewer=identity(request,db)
    if reviewer:
        org_ids=list(db.scalars(select(ReviewerAssignment.organization_id).where(ReviewerAssignment.user_id==user.id,ReviewerAssignment.active.is_(True))))
    elif membership: org_ids=[membership.organization_id]
    else: org_ids=[]
    cases=list(db.scalars(select(Case).where(Case.organization_id.in_(org_ids)).order_by(Case.purchase_deadline)))
    orgs={o.id:o for o in db.scalars(select(Organization).where(Organization.id.in_(org_ids)))}
    return templates.TemplateResponse(request=request,name="cases.html",context=context(request,db,user,cases=cases,orgs=orgs,membership=membership,reviewer=reviewer))

@app.get("/cases/new",response_class=HTMLResponse)
def new_case_page(request:Request,db:Session=Depends(get_db)):
    user,membership,_=identity(request,db)
    if not membership: raise HTTPException(403,"Only customer users can create a case.")
    owners=list(db.scalars(select(User).join(Membership,Membership.user_id==User.id).where(Membership.organization_id==membership.organization_id,Membership.role=="OWNER",Membership.active.is_(True))))
    return templates.TemplateResponse(request=request,name="new_case.html",context=context(request,db,user,owners=owners))

@app.post("/cases")
def create_case(request:Request,reference:str=Form(...),decision_owner_id:str=Form(...),purchasing_contact:str=Form(...),purchase_deadline:str=Form(...),service_deadline:str=Form(""),currency:str=Form(...),purchase_basis:str=Form(...),csrf:str=Form(...),db:Session=Depends(get_db)):
    user,membership,_=identity(request,db); verify_csrf(request,db,csrf)
    if not membership: raise HTTPException(403)
    if currency!="INR" or purchase_basis!="back_to_back":
        reason="Only India/INR back-to-back purchases are supported in this MVP."
        status="UNSUPPORTED"
    else: reason=None; status="DRAFT"
    owner=db.scalar(select(Membership).where(Membership.organization_id==membership.organization_id,Membership.user_id==decision_owner_id,Membership.role=="OWNER"))
    if not owner: raise HTTPException(400,"Choose an owner from this organization.")
    try: pd=datetime.fromisoformat(purchase_deadline).replace(tzinfo=timezone.utc); sd=datetime.fromisoformat(service_deadline).replace(tzinfo=timezone.utc) if service_deadline else None
    except ValueError: raise HTTPException(400,"Enter valid deadlines.")
    case=Case(organization_id=membership.organization_id,reference=reference.strip(),decision_owner_id=decision_owner_id,purchasing_contact=purchasing_contact.strip(),purchase_deadline=pd,proposed_purchase_at=pd,service_deadline=sd,workflow_status=status,unsupported_reason=reason,next_actor="Operations",working_data={},synthetic=False)
    db.add(case); db.flush(); db.add(AuditEvent(organization_id=case.organization_id,case_id=case.id,actor_id=user.id,action="CASE_CREATED",detail={"scope":status})); db.commit()
    return flash_redirect(f"/cases/{case.id}",reason or "Case created.","error" if reason else "success")

def parse_csv_lines(data:bytes)->list[dict]:
    try: text=data.decode("utf-8-sig"); rows=list(csv.DictReader(io.StringIO(text)))
    except UnicodeDecodeError as exc: raise ValueError("CSV must be UTF-8.") from exc
    required={"item","qty","unit","spec","sell_unit","original_buy_unit","current_buy_unit"}
    if not rows or not required.issubset(rows[0]): raise ValueError("CSV must use the fixed Ternfold line-template columns.")
    if len(rows)>15: raise ValueError("This MVP supports up to 15 order lines.")
    result=[]
    for index,row in enumerate(rows,1):
        for key in ("qty","sell_unit","original_buy_unit","current_buy_unit"): dec(row.get(key))
        result.append({"id":str(index),**{key:(row.get(key) or "").strip() for key in required}})
    return result

def validate_upload(filename:str,content_type:str,data:bytes)->str:
    ext=Path(filename).suffix.lower()
    allowed={".pdf":"application/pdf",".png":"image/png",".jpg":"image/jpeg",".jpeg":"image/jpeg",".csv":"text/csv"}
    if ext not in allowed: raise ValueError("Use PDF, JPG, PNG or the fixed UTF-8 CSV template.")
    if len(data)>10_000_000: raise ValueError("This file is larger than the 10 MB limit.")
    if ext==".pdf":
        if not data.startswith(b"%PDF"): raise ValueError("The file extension says PDF, but the content is not a PDF.")
        try:
            reader=PdfReader(io.BytesIO(data))
            if reader.is_encrypted: raise ValueError("Encrypted PDFs cannot be reviewed. Provide an unlocked copy or enter the evidence manually.")
        except ValueError: raise
        except Exception as exc: raise ValueError("This PDF is corrupt or unreadable.") from exc
    elif ext==".png" and not data.startswith(b"\x89PNG"): raise ValueError("The file content is not a PNG.")
    elif ext in {".jpg",".jpeg"} and not data.startswith(b"\xff\xd8"): raise ValueError("The file content is not a JPEG.")
    elif ext==".csv": data.decode("utf-8-sig")
    return allowed[ext]

@app.post("/cases/{case_id}/upload")
async def upload(case_id:str,request:Request,category:str=Form(...),validity_end:str=Form(""),csrf:str=Form(...),file:UploadFile=File(...),db:Session=Depends(get_db)):
    user=require_user(request,db); case,_,_=case_access(db,user,case_id,"customer"); verify_csrf(request,db,csrf)
    docs=list(db.scalars(select(SourceDocument).where(SourceDocument.case_id==case.id)))
    data=await file.read(10_000_001)
    try:
        ctype=validate_upload(file.filename or "evidence",file.content_type or "",data)
        if len(docs)>=10: raise ValueError("This case already has the maximum 10 evidence files. Existing evidence was preserved.")
        if sum(d.size_bytes for d in docs)+len(data)>50_000_000: raise ValueError("Adding this file would exceed the 50 MB case limit. Existing evidence was preserved.")
        valid=datetime.fromisoformat(validity_end).replace(tzinfo=timezone.utc) if validity_end else None
        digest=hashlib.sha256(data).hexdigest()
        duplicate=next((doc for doc in docs if doc.sha256==digest),None)
        if duplicate: return flash_redirect(f"/cases/{case.id}",f"This file already exists in the case as {duplicate.filename}; no duplicate was created.")
        material_change=Path(file.filename or "").suffix.lower()==".csv" or category in {"current_supplier","revised_supplier"}
        if material_change: case.working_revision+=1
        if case.current_calculation_id and material_change: case.current_calculation_id=None; case.financial_status="NOT_EVALUATED"
        key,digest=storage.put(f"org/{case.organization_id}/case/{case.id}",Path(file.filename or "").suffix,data)
        source=SourceDocument(case_id=case.id,organization_id=case.organization_id,category=category,filename=file.filename or "evidence",content_type=ctype,size_bytes=len(data),sha256=digest,storage_key=key,uploaded_by_id=user.id,validity_end=valid,revision_added=case.working_revision)
        db.add(source); db.flush()
        if Path(source.filename).suffix.lower()==".csv":
            working=case.working_data.copy(); working["lines"]=parse_csv_lines(data)
            for flag in ("tax_basis_confirmed","matching_confirmed","applicability_confirmed","baseline_comparable"): working.setdefault(flag,False)
            for side in ("original","current"):
                for key2 in ("freight","handling","other"): working.setdefault(f"{side}_{key2}_status","unknown")
            case.working_data=working
        case.workflow_status="NEEDS_INPUT"; case.next_actor="Operations / reviewer"
        db.add(AuditEvent(organization_id=case.organization_id,case_id=case.id,actor_id=user.id,action="DOCUMENT_UPLOADED",detail={"document_id":source.id,"category":category,"hash":digest}))
        db.commit(); return flash_redirect(f"/cases/{case.id}",f"{source.filename} saved. Review what is still needed.")
    except ValueError as exc:
        db.rollback(); return flash_redirect(f"/cases/{case.id}",str(exc),"error")

@app.post("/cases/{case_id}/freight")
def answer_freight(case_id:str,request:Request,freight_status:str=Form(...),amount:str=Form(""),source_note:str=Form(...),expected_revision:int=Form(...),csrf:str=Form(...),db:Session=Depends(get_db)):
    user=require_user(request,db); case,_,_=case_access(db,user,case_id,"customer"); verify_csrf(request,db,csrf)
    if expected_revision!=case.working_revision: return flash_redirect(f"/cases/{case.id}","The case changed in another session. Your text was not applied; review the latest revision.","error")
    try:
        value="0" if freight_status=="included" else str(dec(amount))
    except ValueError as exc: return flash_redirect(f"/cases/{case.id}",str(exc),"error")
    working=case.working_data.copy(); working["current_freight_status"]=freight_status; working["current_freight"]=value; case.working_data=working
    for q in db.scalars(select(InputQuestion).where(InputQuestion.case_id==case.id,InputQuestion.revision==case.working_revision,InputQuestion.field_key=="current_freight",InputQuestion.resolved_at.is_(None))): q.resolved_at=now_utc(); q.answer=source_note
    db.add(EvidenceReference(case_id=case.id,field_key="current_freight",locator="Named attestation",excerpt=source_note,attested_by_id=user.id))
    case.workflow_status="READY_FOR_REVIEW" if not completeness(working) else "NEEDS_INPUT"; case.next_actor="Assigned reviewer" if case.workflow_status=="READY_FOR_REVIEW" else "Operations"
    db.add(AuditEvent(organization_id=case.organization_id,case_id=case.id,actor_id=user.id,action="FREIGHT_CONFIRMED",detail={"status":freight_status,"revision":case.working_revision})); db.commit()
    return flash_redirect(f"/cases/{case.id}","Freight details saved. The reviewer can now confirm the inputs.")

@app.get("/cases/{case_id}",response_class=HTMLResponse)
def case_page(case_id:str,request:Request,db:Session=Depends(get_db)):
    user=require_user(request,db); case,membership,reviewer=case_access(db,user,case_id)
    org=db.get(Organization,case.organization_id); owner=db.get(User,case.decision_owner_id)
    docs=list(db.scalars(select(SourceDocument).where(SourceDocument.case_id==case.id).order_by(SourceDocument.created_at)))
    calcs=list(db.scalars(select(CalculationVersion).where(CalculationVersion.case_id==case.id).order_by(CalculationVersion.version_number.desc())))
    decisions=list(db.scalars(select(Decision).where(Decision.case_id==case.id).order_by(Decision.recorded_at.desc())))
    outcomes=list(db.scalars(select(Outcome).where(Outcome.case_id==case.id).order_by(Outcome.recorded_at.desc())))
    reports=list(db.scalars(select(ReportArtifact).where(ReportArtifact.case_id==case.id).order_by(ReportArtifact.created_at.desc())))
    drafts=list(db.scalars(select(ExtractionDraft).where(ExtractionDraft.case_id==case.id).order_by(ExtractionDraft.created_at.desc())))
    calc=db.get(CalculationVersion,case.current_calculation_id) if case.current_calculation_id else None
    decision=next((d for d in decisions if calc and d.calculation_id==calc.id),None)
    problems=completeness(effective_working_data(db,case)) if case.workflow_status!="UNSUPPORTED" else [case.unsupported_reason]
    refs=list(db.scalars(select(EvidenceReference).where(EvidenceReference.case_id==case.id)))
    users={u.id:u for u in db.scalars(select(User))}
    return templates.TemplateResponse(request=request,name="case.html",context=context(request,db,user,case=case,org=org,owner=owner,docs=docs,calcs=calcs,calc=calc,decisions=decisions,decision=decision,outcomes=outcomes,reports=reports,drafts=drafts,problems=problems,refs=refs,users=users,membership=membership,reviewer=reviewer))

@app.get("/cases/{case_id}/review",response_class=HTMLResponse)
def review_page(case_id:str,request:Request,db:Session=Depends(get_db)):
    user=require_user(request,db); case,_,_=case_access(db,user,case_id,"reviewer")
    return templates.TemplateResponse(request=request,name="review.html",context=context(request,db,user,case=case,problems=completeness(effective_working_data(db,case))))

@app.get("/cases/{case_id}/inputs",response_class=HTMLResponse)
def input_page(case_id:str,request:Request,db:Session=Depends(get_db)):
    user=require_user(request,db); case,_,_=case_access(db,user,case_id,"customer")
    if case.workflow_status=="UNSUPPORTED": raise HTTPException(400,"Unsupported cases cannot receive material inputs")
    return templates.TemplateResponse(request=request,name="inputs.html",context=context(request,db,user,case=case))

@app.post("/cases/{case_id}/inputs")
async def save_inputs(case_id:str,request:Request,db:Session=Depends(get_db)):
    user=require_user(request,db); case,_,_=case_access(db,user,case_id,"customer")
    if case.workflow_status=="UNSUPPORTED": raise HTTPException(400,"Unsupported cases cannot receive material inputs")
    form=await request.form(); verify_csrf(request,db,str(form.get("csrf","")))
    note=str(form.get("source_note","")).strip()
    if not note: return flash_redirect(f"/cases/{case.id}/inputs","Describe where these material values came from.","error")
    try: expected=int(str(form.get("expected_revision","0")))
    except ValueError: expected=0
    if expected!=case.working_revision: return flash_redirect(f"/cases/{case.id}/inputs","The case changed in another session. Your input was not applied; review the latest revision.","error")
    lines=[]
    try:
        for index in range(1,16):
            item=str(form.get(f"item_{index}","")).strip()
            if not item: continue
            row={"id":str(index),"item":item,"qty":str(form.get(f"qty_{index}","")).strip(),"unit":str(form.get(f"unit_{index}","")).strip(),"spec":str(form.get(f"spec_{index}","")).strip(),"sell_unit":str(form.get(f"sell_{index}","")).strip(),"original_buy_unit":str(form.get(f"original_{index}","")).strip(),"current_buy_unit":str(form.get(f"current_{index}","")).strip()}
            line_amount(row["qty"],row["sell_unit"]); line_amount(row["qty"],row["original_buy_unit"]); line_amount(row["qty"],row["current_buy_unit"]); lines.append(row)
        if not lines: raise ValueError("Add at least one complete order line.")
        working=case.working_data.copy(); working["lines"]=lines
        for side in ("original","current"):
            for charge_key in ("freight","handling","other"):
                status=str(form.get(f"{side}_{charge_key}_status","unknown"))
                if status not in {"confirmed","included","confirmed_none","unknown"}: raise ValueError("Choose a valid direct-charge status.")
                working[f"{side}_{charge_key}_status"]=status
                working[f"{side}_{charge_key}"]="0" if status in {"included","confirmed_none"} else (str(dec(form.get(f"{side}_{charge_key}"))) if status=="confirmed" else "")
    except ValueError as exc: return flash_redirect(f"/cases/{case.id}/inputs",str(exc),"error")
    case.working_revision+=1
    if case.current_calculation_id: case.current_calculation_id=None; case.financial_status="NOT_EVALUATED"
    for key in ("tax_basis_confirmed","matching_confirmed","applicability_confirmed","baseline_comparable","review_confirmed"): working[key]=False
    case.working_data=working
    db.add(EvidenceReference(case_id=case.id,field_key="manual_material_inputs",locator="Named source attestation",excerpt=note,attested_by_id=user.id))
    problems=completeness(working); case.workflow_status="NEEDS_INPUT" if problems else "READY_FOR_REVIEW"; case.next_actor="Assigned reviewer" if not problems else "Operations"
    db.add(AuditEvent(organization_id=case.organization_id,case_id=case.id,actor_id=user.id,action="MATERIAL_INPUTS_SAVED",detail={"revision":case.working_revision,"line_count":len(lines)})); db.commit()
    return flash_redirect(f"/cases/{case.id}","Material inputs saved. The assigned reviewer must confirm their evidence and applicability.")

@app.post("/cases/{case_id}/review/confirm")
def confirm_review(case_id:str,request:Request,expected_revision:int=Form(...),notes:str=Form(""),csrf:str=Form(...),db:Session=Depends(get_db)):
    user=require_user(request,db); case,_,_=case_access(db,user,case_id,"reviewer"); verify_csrf(request,db,csrf)
    if expected_revision!=case.working_revision: return flash_redirect(f"/cases/{case.id}/review","The case changed. Refresh before confirming.","error")
    working=case.working_data.copy()
    for key in ("tax_basis_confirmed","matching_confirmed","applicability_confirmed","baseline_comparable"): working[key]=True
    working["review_confirmed"]=True; case.working_data=working
    problems=completeness(working)
    case.workflow_status="READY_FOR_REVIEW" if not problems else "NEEDS_INPUT"; case.next_actor="Assigned reviewer" if not problems else "Operations"
    db.add(Review(case_id=case.id,revision=case.working_revision,reviewer_id=user.id,notes=notes or "Material inputs and evidence confirmed."))
    db.add(AuditEvent(organization_id=case.organization_id,case_id=case.id,actor_id=user.id,action="INPUTS_CONFIRMED",detail={"revision":case.working_revision})); db.commit()
    return flash_redirect(f"/cases/{case.id}/review","Material inputs confirmed. Publish the reviewed comparison.")

@app.post("/cases/{case_id}/review/publish")
def publish_review(case_id:str,request:Request,expected_revision:int=Form(...),csrf:str=Form(...),db:Session=Depends(get_db)):
    user=require_user(request,db); case,_,_=case_access(db,user,case_id,"reviewer"); verify_csrf(request,db,csrf)
    if expected_revision!=case.working_revision: return flash_redirect(f"/cases/{case.id}/review","The case changed. Refresh before publishing.","error")
    if not case.working_data.get("review_confirmed"): return flash_redirect(f"/cases/{case.id}/review","Confirm the material inputs before publishing.","error")
    org=db.get(Organization,case.organization_id)
    try: result=calculate(effective_working_data(db,case),org.min_contribution_pct,org.erosion_warning_pp)
    except CalculationBlocked as exc: return flash_redirect(f"/cases/{case.id}/review",exc.messages[0],"error")
    version=(db.scalar(select(func.max(CalculationVersion.version_number)).where(CalculationVersion.case_id==case.id)) or 0)+1
    calc=CalculationVersion(case_id=case.id,organization_id=org.id,version_number=version,working_revision=case.working_revision,snapshot=result,revenue=result["revenue"],original_cost=result["original_cost"],current_cost=result["current_cost"],original_contribution=result["original_contribution"],current_contribution=result["current_contribution"],original_pct=result["original_pct"],current_pct=result["current_pct"],erosion_rupees=result["erosion_rupees"],erosion_pp=result["erosion_pp"],financial_status=result["financial_status"],reviewer_id=user.id)
    db.add(calc); db.flush(); case.current_calculation_id=calc.id; case.workflow_status="REVIEWED"; case.financial_status=calc.financial_status; case.next_actor="Decision owner"
    db.add(AuditEvent(organization_id=case.organization_id,case_id=case.id,actor_id=user.id,action="REVIEW_PUBLISHED",detail={"version":version,"revision":case.working_revision})); db.commit()
    return flash_redirect(f"/cases/{case.id}",f"Reviewed version {version} published.")

@app.post("/cases/{case_id}/decision")
def record_decision(case_id:str,request:Request,choice:str=Form(...),rationale:str=Form(...),purchasing_action:str=Form(...),expected_revision:int=Form(...),csrf:str=Form(...),db:Session=Depends(get_db)):
    user=require_user(request,db); case,_,_=case_access(db,user,case_id,"owner"); verify_csrf(request,db,csrf)
    if expected_revision!=case.working_revision or not case.current_calculation_id: return flash_redirect(f"/cases/{case.id}","This reviewed basis changed. Fresh review is required before a decision.","error")
    if choice not in {"PROCEED","SEEK_REVISED_TERMS","WAIT","DO_NOT_PROCEED"} or not rationale.strip() or not purchasing_action.strip(): return flash_redirect(f"/cases/{case.id}","Record the choice, reason and purchasing action.","error")
    calc=db.get(CalculationVersion,case.current_calculation_id)
    if calc.working_revision!=case.working_revision or completeness(effective_working_data(db,case)): return flash_redirect(f"/cases/{case.id}","Evidence is no longer current. Fresh review is required.","error")
    prior=db.scalar(select(Decision).where(Decision.case_id==case.id,Decision.calculation_id==calc.id,Decision.owner_id==user.id,Decision.choice==choice,Decision.rationale==rationale.strip(),Decision.purchasing_action==purchasing_action.strip()).order_by(Decision.recorded_at.desc()))
    if prior: return flash_redirect(f"/cases/{case.id}",f"This decision was already recorded against reviewed version {calc.version_number}.")
    decision=Decision(case_id=case.id,calculation_id=calc.id,owner_id=user.id,choice=choice,rationale=rationale.strip(),purchasing_action=purchasing_action.strip())
    db.add(decision); db.flush(); reviewer=db.get(User,calc.reviewer_id)
    pdf=decision_pdf(case,calc,decision,user.name,reviewer.name); key,digest=storage.put(f"org/{case.organization_id}/case/{case.id}/reports",".pdf",pdf)
    db.add(ReportArtifact(case_id=case.id,calculation_id=calc.id,decision_id=decision.id,storage_key=key,content_hash=digest))
    case.workflow_status="DECISION_RECORDED"
    case.next_actor=case.purchasing_contact if choice=="PROCEED" else ("Operations" if choice=="SEEK_REVISED_TERMS" else "Decision owner")
    db.add(AuditEvent(organization_id=case.organization_id,case_id=case.id,actor_id=user.id,action="DECISION_RECORDED",detail={"choice":choice,"version":calc.version_number})); db.commit()
    return flash_redirect(f"/cases/{case.id}",f"Decision recorded against reviewed version {calc.version_number}.")

@app.post("/cases/{case_id}/revised-demo")
def revised_demo(case_id:str,request:Request,expected_revision:int=Form(...),csrf:str=Form(...),db:Session=Depends(get_db)):
    user=require_user(request,db); case,_,_=case_access(db,user,case_id,"customer"); verify_csrf(request,db,csrf)
    if not case.synthetic: raise HTTPException(404)
    if expected_revision!=case.working_revision: return flash_redirect(f"/cases/{case.id}","The case changed. Review the latest revision.","error")
    case.working_revision+=1; case.working_data=demo_data(freight_known=True,revised=True); case.current_calculation_id=None; case.workflow_status="READY_FOR_REVIEW"; case.financial_status="NOT_EVALUATED"; case.next_actor="Assigned reviewer"
    valid=datetime(2026,9,30,18,29,tzinfo=timezone.utc)
    doc=add_doc(db,case,user,"revised_supplier","A-107_revised_supplier_offer.pdf","Revised supplier offer",["Contactors INR 860 x 100","Relays INR 520 x 100","Terminal kits INR 340 x 100","Additional freight INR 5,000. Same specification and delivery terms."],valid)
    db.add(EvidenceReference(case_id=case.id,source_document_id=doc.id,field_key="revised_goods_and_freight",locator="Page 1",excerpt="Goods INR 1,72,000 plus freight INR 5,000."))
    db.add(AuditEvent(organization_id=case.organization_id,case_id=case.id,actor_id=user.id,action="REVISED_TERMS_ADDED",detail={"revision":case.working_revision,"document_id":doc.id})); db.commit()
    return flash_redirect(f"/cases/{case.id}","Revised supplier terms saved. Prior evidence and decisions remain in history.")

@app.post("/cases/{case_id}/outcome")
def record_outcome(case_id:str,request:Request,actual_goods:str=Form(...),actual_freight:str=Form(...),notes:str=Form(""),csrf:str=Form(...),db:Session=Depends(get_db)):
    user=require_user(request,db); case,_,_=case_access(db,user,case_id,"customer"); verify_csrf(request,db,csrf)
    decision=db.scalar(select(Decision).where(Decision.case_id==case.id).order_by(Decision.recorded_at.desc()))
    if not decision: return flash_redirect(f"/cases/{case.id}","Record a customer decision before adding actual costs.","error")
    calc=db.get(CalculationVersion,decision.calculation_id); goods=dec(actual_goods).quantize(Decimal(".01")); freight=dec(actual_freight).quantize(Decimal(".01")); revenue=Decimal(calc.snapshot["revenue"]); contribution=revenue-goods-freight; pct=contribution/revenue*100 if revenue>0 else None
    db.add(Outcome(case_id=case.id,decision_id=decision.id,actual_goods=goods,actual_freight=freight,actual_contribution=contribution,actual_pct=pct,notes=notes,recorded_by_id=user.id))
    case.workflow_status="OUTCOME_CAPTURED"; db.add(AuditEvent(organization_id=case.organization_id,case_id=case.id,actor_id=user.id,action="OUTCOME_CAPTURED",detail={"decision_id":decision.id})); db.commit()
    return flash_redirect(f"/cases/{case.id}","Actual costs reconciled without changing the decision-time snapshot.")

@app.get("/documents/{document_id}",response_class=HTMLResponse)
def document_page(document_id:str,request:Request,db:Session=Depends(get_db)):
    user=require_user(request,db); doc=db.get(SourceDocument,document_id)
    if not doc: raise HTTPException(404)
    case_access(db,user,doc.case_id)
    if doc.deleted_at: raise HTTPException(410,"This source was deleted under the retention agreement.")
    return templates.TemplateResponse(request=request,name="document.html",context=context(request,db,user,doc=doc))

@app.post("/documents/{document_id}/extract")
def extract_document(document_id:str,request:Request,csrf:str=Form(...),db:Session=Depends(get_db)):
    user=require_user(request,db); verify_csrf(request,db,csrf); doc=db.get(SourceDocument,document_id)
    if not doc: raise HTTPException(404)
    case,_,_=case_access(db,user,doc.case_id)
    if doc.deleted_at: raise HTTPException(410,"This source was deleted under the retention agreement.")
    status=extraction_status()
    if not status["available"]: return flash_redirect(f"/documents/{doc.id}",status["message"],"error")
    raw=storage.read(doc.storage_key)
    try:
        if doc.content_type=="application/pdf":
            reader=PdfReader(io.BytesIO(raw)); pages=[]
            for index,page in enumerate(reader.pages[:20],1): pages.append(f"[PAGE {index}]\n{page.extract_text() or ''}")
            source_text="\n".join(pages)
        elif doc.content_type=="text/csv": source_text=raw.decode("utf-8-sig")
        else: return flash_redirect(f"/documents/{doc.id}","Live text extraction supports text PDFs and CSVs. Use the visible source for manual review.","error")
        if not source_text.strip(): raise ValueError("No machine-readable text was found.")
        result=propose_from_text(source_text[:60000])
        try: proposals=json.loads(result)
        except json.JSONDecodeError: proposals={"raw_response":result}
        draft=ExtractionDraft(case_id=case.id,source_document_id=doc.id,requested_by_id=user.id,provider=status["provider"],model=status["model"],status="SUCCEEDED",proposals=proposals)
        db.add(draft); db.add(AuditEvent(organization_id=case.organization_id,case_id=case.id,actor_id=user.id,action="EXTRACTION_DRAFT_CREATED",detail={"document_id":doc.id,"provider":status["provider"]})); db.commit()
        return flash_redirect(f"/cases/{case.id}","AI draft saved for review. No material value was confirmed automatically.")
    except Exception as exc:
        db.add(ExtractionDraft(case_id=case.id,source_document_id=doc.id,requested_by_id=user.id,provider=status["provider"],model=status["model"],status="FAILED",proposals={},error=str(exc)[:500])); db.commit()
        return flash_redirect(f"/documents/{doc.id}","Extraction failed. The source is preserved and manual review remains available.","error")

@app.get("/documents/{document_id}/preview")
def document_preview(document_id:str,request:Request,db:Session=Depends(get_db)):
    user=require_user(request,db); doc=db.get(SourceDocument,document_id)
    if not doc: raise HTTPException(404)
    case_access(db,user,doc.case_id)
    if doc.deleted_at: raise HTTPException(410,"This source was deleted under the retention agreement.")
    raw=storage.read(doc.storage_key)
    try:
        if doc.content_type=="application/pdf":
            pdf=pdfium.PdfDocument(raw); image=pdf[0].render(scale=1.7).to_pil()
        elif doc.content_type.startswith("image/"): image=Image.open(io.BytesIO(raw)).convert("RGB")
        else: return Response(raw,media_type="text/plain; charset=utf-8")
        buf=io.BytesIO(); image.save(buf,"PNG"); return Response(buf.getvalue(),media_type="image/png")
    except Exception: raise HTTPException(422,"Preview unavailable. Download the original or enter the evidence manually.")

@app.get("/documents/{document_id}/download")
def document_download(document_id:str,request:Request,db:Session=Depends(get_db)):
    user=require_user(request,db); doc=db.get(SourceDocument,document_id)
    if not doc: raise HTTPException(404)
    case_access(db,user,doc.case_id)
    if doc.deleted_at: raise HTTPException(410,"This source was deleted under the retention agreement.")
    return Response(storage.read(doc.storage_key),media_type=doc.content_type,headers={"Content-Disposition":f'attachment; filename="{doc.filename.replace(chr(34),"")}"'})

@app.get("/reports/{report_id}/download")
def report_download(report_id:str,request:Request,db:Session=Depends(get_db)):
    user=require_user(request,db); report=db.get(ReportArtifact,report_id)
    if not report: raise HTTPException(404)
    case,_membership,_reviewer=case_access(db,user,report.case_id)
    calc=db.get(CalculationVersion,report.calculation_id)
    return Response(storage.read(report.storage_key),media_type="application/pdf",headers={"Content-Disposition":f'attachment; filename="Ternfold_{case.reference}_v{calc.version_number}_decision.pdf"'})

@app.get("/cases/{case_id}/settings",response_class=HTMLResponse)
def settings_page(case_id:str,request:Request,db:Session=Depends(get_db)):
    user=require_user(request,db); case,membership,_=case_access(db,user,case_id)
    if not membership or membership.role!="OWNER": raise HTTPException(403)
    org=db.get(Organization,case.organization_id); members=list(db.execute(select(User,Membership).join(Membership,Membership.user_id==User.id).where(Membership.organization_id==org.id)).all())
    return templates.TemplateResponse(request=request,name="settings.html",context=context(request,db,user,case=case,org=org,members=members))

@app.post("/cases/{case_id}/settings")
def save_settings(case_id:str,request:Request,min_pct:str=Form(...),erosion_pp:str=Form(...),csrf:str=Form(...),db:Session=Depends(get_db)):
    user=require_user(request,db); case,membership,_=case_access(db,user,case_id); verify_csrf(request,db,csrf)
    if not membership or membership.role!="OWNER": raise HTTPException(403)
    org=db.get(Organization,case.organization_id); new_floor=dec(min_pct); new_erosion=dec(erosion_pp)
    changed=org.min_contribution_pct!=new_floor or org.erosion_warning_pp!=new_erosion; org.min_contribution_pct=new_floor; org.erosion_warning_pp=new_erosion
    if changed and case.current_calculation_id: case.working_revision+=1; case.current_calculation_id=None; case.workflow_status="READY_FOR_REVIEW"; case.financial_status="NOT_EVALUATED"; case.next_actor="Assigned reviewer"
    db.add(AuditEvent(organization_id=org.id,case_id=case.id,actor_id=user.id,action="THRESHOLDS_CHANGED",detail={"floor":str(new_floor),"erosion_pp":str(new_erosion)})); db.commit()
    return flash_redirect(f"/cases/{case.id}/settings","Settings saved. Any affected decision basis now requires fresh review.")

@app.post("/cases/{case_id}/service-closure")
def close_service_case(case_id:str,request:Request,action:str=Form(...),csrf:str=Form(...),db:Session=Depends(get_db)):
    user=require_user(request,db); case,membership,_=case_access(db,user,case_id); verify_csrf(request,db,csrf)
    if not membership or membership.role!="OWNER": raise HTTPException(403)
    if action=="close":
        if not db.scalar(select(Decision.id).where(Decision.case_id==case.id)): return flash_redirect(f"/cases/{case.id}/settings","Record a decision before closing the service case.","error")
        case.closed_at=now_utc(); message="Service case closed. Source-file retention now runs from this timestamp."
    elif action=="reopen" and case.closed_at:
        case.closed_at=None; message="Service case reopened before retention deletion."
    else: raise HTTPException(400,"Choose a valid service-closure action.")
    db.add(AuditEvent(organization_id=case.organization_id,case_id=case.id,actor_id=user.id,action="SERVICE_CASE_"+action.upper(),detail={"closed_at":case.closed_at.isoformat() if case.closed_at else None})); db.commit()
    return flash_redirect(f"/cases/{case.id}/settings",message)

@app.get("/line-template.csv")
def line_template(request:Request,db:Session=Depends(get_db)):
    require_user(request,db); text="item,qty,unit,spec,sell_unit,original_buy_unit,current_buy_unit\n"
    return Response(text,media_type="text/csv",headers={"Content-Disposition":'attachment; filename="ternfold_line_template.csv"'})
