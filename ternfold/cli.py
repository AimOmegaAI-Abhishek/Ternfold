from __future__ import annotations
import argparse
from datetime import datetime, timedelta, timezone
from alembic import command
from alembic.config import Config
from sqlalchemy import delete, select
from .db import SessionLocal, init_database
from .fixtures import seed_demo
from .models import AuditEvent, Case, Organization, ReportArtifact, SourceDocument, User
from .storage import storage

def init() -> None:
    config=Config("alembic.ini")
    command.upgrade(config,"head")
    print("Database schema ready.")

def seed() -> None:
    init_database()
    with SessionLocal() as db:
        result=seed_demo(db)
    print("Synthetic demonstration ready." if result.get("created") else "Synthetic demonstration already exists; no duplicate data added.")

def reset_demo() -> None:
    init_database()
    with SessionLocal() as db:
        orgs=list(db.scalars(select(Organization)))
        if any(not org.synthetic for org in orgs):
            raise SystemExit("Reset refused: this database contains non-synthetic organizations. Customer records were not changed.")
        db.execute(delete(Organization)); db.flush()
        db.execute(delete(User)); db.commit()
        seed_demo(db)
    print("Synthetic organizations reset. This command cannot run on a database containing customer organizations.")

def apply_retention(at:datetime|None=None) -> dict[str,int]:
    """Apply the agreed post-closure schedule; backup expiry belongs to deployment operations."""
    at=at or datetime.now(timezone.utc)
    counts={"sources":0,"reports":0,"cases":0}
    with SessionLocal() as db:
        cases=list(db.scalars(select(Case).where(Case.closed_at.is_not(None))))
        for case in cases:
            org=db.get(Organization,case.organization_id)
            if at >= case.closed_at + timedelta(days=org.retention_source_days):
                for doc in db.scalars(select(SourceDocument).where(SourceDocument.case_id==case.id,SourceDocument.deleted_at.is_(None))):
                    storage.delete(doc.storage_key); doc.deleted_at=at; counts["sources"]+=1
                db.add(AuditEvent(organization_id=org.id,case_id=case.id,action="SOURCE_RETENTION_APPLIED",detail={"closed_at":case.closed_at.isoformat(),"applied_at":at.isoformat()}))
            if at >= case.closed_at + timedelta(days=org.retention_record_days):
                for report in db.scalars(select(ReportArtifact).where(ReportArtifact.case_id==case.id)):
                    storage.delete(report.storage_key); counts["reports"]+=1
                reference=case.reference; case_id=case.id; closed_at=case.closed_at
                db.delete(case); db.flush(); counts["cases"]+=1
                db.add(AuditEvent(organization_id=org.id,case_id=None,action="CASE_RETENTION_APPLIED",detail={"deleted_case_id":case_id,"reference":reference,"closed_at":closed_at.isoformat(),"applied_at":at.isoformat()}))
        db.commit()
    return counts

def retention() -> None:
    result=apply_retention()
    print(f"Retention applied: {result['sources']} source files, {result['reports']} reports, {result['cases']} case records deleted.")

def main() -> None:
    parser=argparse.ArgumentParser(prog="python -m ternfold.cli")
    parser.add_argument("command",choices=["init","seed","reset-demo","apply-retention"])
    args=parser.parse_args()
    {"init":init,"seed":seed,"reset-demo":reset_demo,"apply-retention":retention}[args.command]()

if __name__=="__main__": main()
