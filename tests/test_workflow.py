import re
from io import BytesIO
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from pypdf import PdfReader
from sqlalchemy import func, select
from ternfold.app import app
from ternfold.cli import apply_retention, reset_demo
from ternfold.db import SessionLocal
from ternfold.models import AuditEvent, CalculationVersion, Case, Decision, Membership, Outcome, ReportArtifact, SourceDocument, User
from ternfold.storage import storage

def login(client,email):
    response=client.post("/login",data={"email":email,"password":"TernfoldDemo!"},follow_redirects=False)
    assert response.status_code==303
    return csrf(client)

def csrf(client):
    response=client.get("/")
    match=re.search(r'name="csrf" value="([^"]+)"',response.text)
    assert match
    return match.group(1)

def logout(client,token):
    assert client.post("/logout",data={"csrf":token},follow_redirects=False).status_code==303

def case_id(reference="A-107"):
    with SessionLocal() as db: return db.scalar(select(Case.id).where(Case.reference==reference))

def test_complete_persistent_reviewed_workflow_and_access_controls():
    reset_demo()
    client=TestClient(app)
    cid=case_id()

    rohan_csrf=login(client,"rohan@example.test")
    page=client.get(f"/cases/{cid}"); assert "Resolve missing information" in page.text
    stale=client.post(f"/cases/{cid}/freight",data={"freight_status":"confirmed","amount":"5000","source_note":"Supplier freight confirmation: INR 5,000.","expected_revision":"0","csrf":rohan_csrf},follow_redirects=False)
    assert stale.status_code==303 and "changed" in stale.headers["location"]
    saved=client.post(f"/cases/{cid}/freight",data={"freight_status":"confirmed","amount":"5000","source_note":"Supplier freight confirmation: INR 5,000 for this delivery.","expected_revision":"1","csrf":rohan_csrf},follow_redirects=False)
    assert saved.status_code==303
    forbidden=client.post(f"/cases/{cid}/review/publish",data={"expected_revision":"1","csrf":rohan_csrf})
    assert forbidden.status_code==403
    bad_upload=client.post(f"/cases/{cid}/upload",data={"category":"current_supplier","validity_end":"","csrf":rohan_csrf},files={"file":("wrong.pdf",b"not-pdf","application/pdf")},follow_redirects=False)
    assert bad_upload.status_code==303 and "not%20a%20PDF" in bad_upload.headers["location"]
    docs_before=None
    with SessionLocal() as db: docs_before=db.scalar(select(func.count()).select_from(SourceDocument).where(SourceDocument.case_id==cid))
    assert docs_before==3
    docid=None
    with SessionLocal() as db: docid=db.scalar(select(SourceDocument.id).where(SourceDocument.case_id==cid))
    fallback=client.post(f"/documents/{docid}/extract",data={"csrf":rohan_csrf},follow_redirects=False)
    assert fallback.status_code==303 and "not%20configured" in fallback.headers["location"]
    logout(client,rohan_csrf)

    reviewer_csrf=login(client,"reviewer@ternfold.test")
    assert client.post(f"/cases/{cid}/review/confirm",data={"expected_revision":"1","notes":"Evidence checked.","csrf":reviewer_csrf},follow_redirects=False).status_code==303
    assert client.post(f"/cases/{cid}/review/publish",data={"expected_revision":"1","csrf":reviewer_csrf},follow_redirects=False).status_code==303
    with SessionLocal() as db:
        v1=db.scalar(select(CalculationVersion).where(CalculationVersion.case_id==cid,CalculationVersion.version_number==1))
        assert (v1.revenue,v1.current_contribution,v1.current_pct)==(200000,17000,8.5)
    logout(client,reviewer_csrf)

    meera_csrf=login(client,"meera@example.test")
    seek={"choice":"SEEK_REVISED_TERMS","rationale":"Ask Rohan to obtain revised supplier terms before Purchasing commits.","purchasing_action":"Rohan: request revised supplier pricing and delivery terms; Purchasing should wait.","expected_revision":"1","csrf":meera_csrf}
    assert client.post(f"/cases/{cid}/decision",data=seek,follow_redirects=False).status_code==303
    assert client.post(f"/cases/{cid}/decision",data=seek,follow_redirects=False).status_code==303
    with SessionLocal() as db: assert db.scalar(select(func.count()).select_from(Decision).where(Decision.case_id==cid))==1
    logout(client,meera_csrf)

    rohan_csrf=login(client,"rohan@example.test")
    assert client.post(f"/cases/{cid}/revised-demo",data={"expected_revision":"1","csrf":rohan_csrf},follow_redirects=False).status_code==303
    with SessionLocal() as db:
        case=db.get(Case,cid); assert case.current_calculation_id is None and case.working_revision==2
        assert db.scalar(select(func.count()).select_from(CalculationVersion).where(CalculationVersion.case_id==cid))==1
        assert db.scalar(select(func.count()).select_from(Decision).where(Decision.case_id==cid))==1
    logout(client,rohan_csrf)

    reviewer_csrf=login(client,"reviewer@ternfold.test")
    assert client.post(f"/cases/{cid}/review/confirm",data={"expected_revision":"2","notes":"Revised terms checked.","csrf":reviewer_csrf},follow_redirects=False).status_code==303
    assert client.post(f"/cases/{cid}/review/publish",data={"expected_revision":"2","csrf":reviewer_csrf},follow_redirects=False).status_code==303
    logout(client,reviewer_csrf)

    meera_csrf=login(client,"meera@example.test")
    proceed={"choice":"PROCEED","rationale":"Honour the customer commitment; revised supplier terms and delivery confirmed.","purchasing_action":"Kavita: place the order in the existing purchasing system using the reviewed supplier quote and confirmed terms.","expected_revision":"2","csrf":meera_csrf}
    assert client.post(f"/cases/{cid}/decision",data=proceed,follow_redirects=False).status_code==303
    assert client.post(f"/cases/{cid}/outcome",data={"actual_goods":"172000","actual_freight":"5200","notes":"Supplier invoice received.","csrf":meera_csrf},follow_redirects=False).status_code==303
    page=client.get(f"/cases/{cid}")
    for expected in ("₹23,000","11.50%","Below Floor","Honour the customer commitment","₹22,800","11.40%"):
        assert expected in page.text
    with SessionLocal() as db:
        case=db.get(Case,cid); current=db.get(CalculationVersion,case.current_calculation_id)
        assert current.version_number==2 and current.current_contribution==23000 and current.current_pct==11.5
        outcome=db.scalar(select(Outcome).where(Outcome.case_id==cid)); assert outcome.actual_contribution==Decimal("22800.00") and outcome.actual_pct==Decimal("11.400000000000")
        report=db.scalar(select(ReportArtifact).where(ReportArtifact.case_id==cid).order_by(ReportArtifact.created_at.desc())); rid=report.id
    report_response=client.get(f"/reports/{rid}/download")
    assert report_response.status_code==200 and report_response.content.startswith(b"%PDF")
    text="\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(report_response.content)).pages)
    for expected in ("Order A-107", "Reviewed version 2", "23,000", "11.50%", "Meera Shah", "Honour the customer commitment"):
        assert expected in text
    assert client.get(f"/cases/{cid}/settings").status_code==200
    assert client.post(f"/cases/{cid}/service-closure",data={"action":"close","csrf":meera_csrf},follow_redirects=False).status_code==303
    with SessionLocal() as db: assert db.get(Case,cid).closed_at is not None
    assert client.post(f"/cases/{cid}/service-closure",data={"action":"reopen","csrf":meera_csrf},follow_redirects=False).status_code==303
    with SessionLocal() as db: assert db.get(Case,cid).closed_at is None
    logout(client,meera_csrf)

    outsider_csrf=login(client,"dev@otherco.test")
    assert client.get(f"/cases/{cid}").status_code==404
    assert client.get(f"/reports/{rid}/download").status_code==404
    logout(client,outsider_csrf)

    new_client=TestClient(app); login(new_client,"meera@example.test")
    assert "Decision Recorded" in new_client.get(f"/cases/{cid}").text or "Outcome Captured" in new_client.get(f"/cases/{cid}").text

def test_new_case_manual_input_path_and_service_admin_isolation():
    reset_demo()
    client=TestClient(app)
    token=login(client,"rohan@example.test")
    with SessionLocal() as db:
        owner_id=db.scalar(select(User.id).where(User.email=="meera@example.test"))
    created=client.post("/cases",data={"reference":"A-108","decision_owner_id":owner_id,"purchasing_contact":"Kavita Rao","purchase_deadline":"2026-09-10T16:00","service_deadline":"2026-09-09T16:00","currency":"INR","purchase_basis":"back_to_back","csrf":token},follow_redirects=False)
    assert created.status_code==303
    new_id=created.headers["location"].split("/cases/")[1].split("?")[0]
    input_page=client.get(f"/cases/{new_id}/inputs")
    assert input_page.status_code==200 and "Material inputs · A-108" in input_page.text and 'value="None"' not in input_page.text
    payload={"expected_revision":"1","source_note":"Accepted customer order and supplier quotations, checked beside these fields.","csrf":token}
    rows=[("Contactors","100","nos","Same contactor specification","1000","850","890"),("Relays","100","nos","Same relay specification","600","510","540"),("Terminal kits","100","kits","Same terminal kit specification","400","340","350")]
    for index,row in enumerate(rows,1):
        for key,value in zip(("item","qty","unit","spec","sell","original","current"),row): payload[f"{key}_{index}"]=value
    for side in ("original","current"):
        for charge in ("freight","handling","other"):
            payload[f"{side}_{charge}_status"]="confirmed_none"
            payload[f"{side}_{charge}"]=""
    payload["original_freight_status"]="included"
    payload["current_freight_status"]="confirmed"; payload["current_freight"]="5000"
    saved=client.post(f"/cases/{new_id}/inputs",data=payload,follow_redirects=False)
    assert saved.status_code==303
    with SessionLocal() as db:
        case=db.get(Case,new_id)
        assert case.working_revision==2 and case.current_calculation_id is None
        assert case.working_data["current_freight"]=="5000"
    stale=client.post(f"/cases/{new_id}/inputs",data=payload,follow_redirects=False)
    assert stale.status_code==303 and "changed" in stale.headers["location"]
    logout(client,token)

    reviewer_token=login(client,"reviewer@ternfold.test")
    assert client.post(f"/cases/{new_id}/review/confirm",data={"expected_revision":"2","notes":"Evidence checked beside every material field.","csrf":reviewer_token},follow_redirects=False).status_code==303
    assert client.post(f"/cases/{new_id}/review/publish",data={"expected_revision":"2","csrf":reviewer_token},follow_redirects=False).status_code==303
    with SessionLocal() as db:
        calc=db.scalar(select(CalculationVersion).where(CalculationVersion.case_id==new_id))
        assert (calc.revenue,calc.current_contribution,calc.current_pct)==(200000,17000,Decimal("8.500000000000"))
    logout(client,reviewer_token)

    admin_token=login(client,"admin@ternfold.test")
    assert client.get(f"/cases/{new_id}").status_code==404
    logout(client,admin_token)

def test_agreed_retention_schedule_preserves_receipt():
    reset_demo(); cid=case_id(); clock=datetime(2026,12,20,tzinfo=timezone.utc)
    with SessionLocal() as db:
        case=db.get(Case,cid); case.closed_at=clock-timedelta(days=31)
        keys=list(db.scalars(select(SourceDocument.storage_key).where(SourceDocument.case_id==cid))); db.commit()
    result=apply_retention(clock)
    assert result["sources"]==3 and result["cases"]==0
    with SessionLocal() as db:
        assert db.get(Case,cid) is not None
        assert all(value is not None for value in db.scalars(select(SourceDocument.deleted_at).where(SourceDocument.case_id==cid)))
    for key in keys:
        try: storage.read(key); assert False,"retained source bytes were not deleted"
        except FileNotFoundError: pass

    with SessionLocal() as db:
        case=db.get(Case,cid); case.closed_at=clock-timedelta(days=91); db.commit()
    result=apply_retention(clock)
    assert result["cases"]==1
    with SessionLocal() as db:
        assert db.get(Case,cid) is None
        receipt=db.scalar(select(AuditEvent).where(AuditEvent.action=="CASE_RETENTION_APPLIED"))
        assert receipt and receipt.detail["reference"]=="A-107"

def test_expired_source_blocks_publication_and_duplicate_upload_is_idempotent():
    reset_demo(); cid=case_id(); client=TestClient(app)
    token=login(client,"rohan@example.test")
    with SessionLocal() as db:
        accepted=db.scalar(select(SourceDocument).where(SourceDocument.case_id==cid,SourceDocument.category=="accepted_order"))
        payload=storage.read(accepted.storage_key)
        count_before=db.scalar(select(func.count()).select_from(SourceDocument).where(SourceDocument.case_id==cid))
    duplicate=client.post(f"/cases/{cid}/upload",data={"category":"accepted_order","validity_end":"","csrf":token},files={"file":("same-order.pdf",payload,"application/pdf")},follow_redirects=False)
    assert duplicate.status_code==303 and "already%20exists" in duplicate.headers["location"]
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(SourceDocument).where(SourceDocument.case_id==cid))==count_before
        supplier=db.scalar(select(SourceDocument).where(SourceDocument.case_id==cid,SourceDocument.category=="current_supplier"))
        case=db.get(Case,cid); supplier.validity_end=case.proposed_purchase_at-timedelta(seconds=1); db.commit()
    assert client.post(f"/cases/{cid}/freight",data={"freight_status":"confirmed","amount":"5000","source_note":"Supplier confirmed freight.","expected_revision":"1","csrf":token},follow_redirects=False).status_code==303
    logout(client,token)
    reviewer_token=login(client,"reviewer@ternfold.test")
    assert client.post(f"/cases/{cid}/review/confirm",data={"expected_revision":"1","notes":"Checked","csrf":reviewer_token},follow_redirects=False).status_code==303
    publish=client.post(f"/cases/{cid}/review/publish",data={"expected_revision":"1","csrf":reviewer_token},follow_redirects=False)
    assert publish.status_code==303 and "expired" in publish.headers["location"]
    with SessionLocal() as db: assert db.get(Case,cid).current_calculation_id is None
