from __future__ import annotations
from datetime import datetime, timezone
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen.canvas import Canvas
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from .auth import password_hash
from .finance import calculate
from .models import (AuditEvent,CalculationVersion,Case,Decision,EvidenceReference,InputQuestion,Membership,Organization,ReviewerAssignment,Review,SourceDocument,User)
from .storage import storage

DEMO_PASSWORD="TernfoldDemo!"
DEMO_NOW=datetime(2026,9,3,9,0,tzinfo=timezone.utc)

def demo_data(current:bool=True,freight_known:bool=False,revised:bool=False)->dict:
    buys=[("Contactor LC1D","100","nos","18A, 415V","1000","850","890" if not revised else "860"),
          ("Control relay RXM","100","nos","4CO, 230V AC","600","510","540" if not revised else "520"),
          ("Terminal kit TB","100","kits","10-way kit","400","340","350" if not revised else "340")]
    lines=[{"id":str(i+1),"item":a,"qty":b,"unit":c,"spec":d,"sell_unit":e,"original_buy_unit":f,"current_buy_unit":g} for i,(a,b,c,d,e,f,g) in enumerate(buys)]
    return {"lines":lines,"tax_basis_confirmed":True,"matching_confirmed":True,"applicability_confirmed":True,"baseline_comparable":True,
            "original_freight_status":"included","original_freight":"0","original_handling_status":"confirmed_none","original_handling":"0","original_other_status":"confirmed_none","original_other":"0",
            "current_freight_status":"confirmed" if freight_known else "unknown","current_freight":"5000" if freight_known else None,
            "current_handling_status":"confirmed_none","current_handling":"0","current_other_status":"confirmed_none","current_other":"0",
            "review_confirmed":False,"evidence_expired":False,"revision_label":"Revised supplier offer" if revised else "Current supplier offer"}

def synthetic_pdf(title:str,lines:list[str])->bytes:
    buf=BytesIO(); c=Canvas(buf,pagesize=A4); w,h=A4
    c.setFillColorRGB(.08,.25,.22); c.rect(0,h-74,w,74,fill=1,stroke=0)
    c.setFillColorRGB(1,1,1); c.setFont("Helvetica-Bold",14); c.drawString(42,h-43,"SYNTHETIC DEMONSTRATION - NOT CUSTOMER DATA")
    c.setFillColorRGB(.08,.12,.12); c.setFont("Helvetica-Bold",22); c.drawString(42,h-112,title)
    y=h-150; c.setFont("Helvetica",11)
    for line in lines: c.drawString(42,y,line); y-=23
    c.setFont("Helvetica",8); c.setFillColorRGB(.3,.35,.34); c.drawString(42,40,"Generated fixture for the Ternfold local demonstration.")
    c.save(); return buf.getvalue()

def add_doc(db:Session,case:Case,user:User,category:str,filename:str,title:str,body:list[str],valid:datetime|None=None)->SourceDocument:
    data=synthetic_pdf(title,body); key,digest=storage.put(f"org/{case.organization_id}/case/{case.id}",".pdf",data)
    doc=SourceDocument(case_id=case.id,organization_id=case.organization_id,category=category,filename=filename,content_type="application/pdf",size_bytes=len(data),sha256=digest,storage_key=key,uploaded_by_id=user.id,validity_end=valid,revision_added=case.working_revision)
    db.add(doc); db.flush(); return doc

def make_calculation(db:Session,case:Case,reviewer:User,org:Organization,data:dict,version:int)->CalculationVersion:
    result=calculate(data,org.min_contribution_pct,org.erosion_warning_pp)
    review=Review(case_id=case.id,revision=case.working_revision,reviewer_id=reviewer.id,notes="Synthetic fixture reviewed.")
    db.add(review); db.flush()
    calc=CalculationVersion(case_id=case.id,organization_id=org.id,version_number=version,working_revision=case.working_revision,snapshot=result,revenue=result["revenue"],original_cost=result["original_cost"],current_cost=result["current_cost"],original_contribution=result["original_contribution"],current_contribution=result["current_contribution"],original_pct=result["original_pct"],current_pct=result["current_pct"],erosion_rupees=result["erosion_rupees"],erosion_pp=result["erosion_pp"],financial_status=result["financial_status"],reviewer_id=reviewer.id)
    db.add(calc); db.flush(); case.current_calculation_id=calc.id; case.financial_status=calc.financial_status; case.workflow_status="REVIEWED"; case.next_actor="Meera"
    return calc

def seed_demo(db:Session)->dict:
    existing=db.scalar(select(Organization).where(Organization.slug=="demo-sample-distributor"))
    if existing: return {"organization_id":existing.id,"created":False}
    users={}
    for key,name,email,admin in [
        ("meera","Meera Shah","meera@example.test",False),("rohan","Rohan Desai","rohan@example.test",False),
        ("kavita","Kavita Rao","kavita@example.test",False),("reviewer","Ananya Iyer","reviewer@ternfold.test",False),
        ("outsider","Dev Malhotra","dev@otherco.test",False),("admin","Service Admin","admin@ternfold.test",True)]:
        users[key]=User(name=name,email=email,password_hash=password_hash(DEMO_PASSWORD),service_admin=admin); db.add(users[key])
    db.flush()
    org=Organization(slug="demo-sample-distributor",name="Sample Distributor A",synthetic=True); other=Organization(slug="demo-other-company",name="Other Company",synthetic=True)
    db.add_all([org,other]); db.flush()
    db.add_all([Membership(organization_id=org.id,user_id=users["meera"].id,role="OWNER",title="Owner"),
        Membership(organization_id=org.id,user_id=users["rohan"].id,role="CONTRIBUTOR",title="Operations"),
        Membership(organization_id=org.id,user_id=users["kavita"].id,role="CONTRIBUTOR",title="Purchasing"),
        Membership(organization_id=other.id,user_id=users["outsider"].id,role="OWNER",title="Owner"),
        ReviewerAssignment(organization_id=org.id,user_id=users["reviewer"].id)])
    valid=datetime(2026,9,30,18,29,tzinfo=timezone.utc); deadline=datetime(2026,9,5,10,0,tzinfo=timezone.utc)
    case=Case(organization_id=org.id,reference="A-107",decision_owner_id=users["meera"].id,purchasing_contact="Kavita Rao",purchase_deadline=deadline,proposed_purchase_at=deadline,service_deadline=datetime(2026,9,4,10,0,tzinfo=timezone.utc),workflow_status="NEEDS_INPUT",financial_status="INCOMPLETE",next_actor="Rohan - Operations",working_data=demo_data(),synthetic=True)
    db.add(case); db.flush()
    order=add_doc(db,case,users["rohan"],"accepted_order","A-107_accepted_order.pdf","Accepted customer order A-107",["100 Contactors at INR 1,000 net each","100 Relays at INR 600 net each","100 Terminal kits at INR 400 net each","Confirmed consistent net tax basis."],valid)
    original=add_doc(db,case,users["rohan"],"original_costing","A-107_original_costing.pdf","Original comparable costing",["Contactors INR 850 x 100","Relays INR 510 x 100","Terminal kits INR 340 x 100","Delivered terms: freight included."],valid)
    current=add_doc(db,case,users["rohan"],"current_supplier","A-107_current_supplier_offer.pdf","Current supplier offer",["Contactors INR 890 x 100","Relays INR 540 x 100","Terminal kits INR 350 x 100","Freight is not stated. Confirmation required."],valid)
    for field,doc,excerpt in [("revenue",order,"Customer line amounts"),("original_goods",original,"Original supplier rates and delivered terms"),("current_goods",current,"Current supplier rates; freight absent")]:
        db.add(EvidenceReference(case_id=case.id,source_document_id=doc.id,field_key=field,locator="Page 1",excerpt=excerpt))
    db.add(InputQuestion(case_id=case.id,revision=1,field_key="current_freight",question="Is delivery included in this supplier price? If not, add the freight amount and its source.",assigned_to="Rohan - Operations"))
    nochange=Case(organization_id=org.id,reference="A-105",decision_owner_id=users["meera"].id,purchasing_contact="Kavita Rao",purchase_deadline=deadline,proposed_purchase_at=deadline,workflow_status="READY_FOR_REVIEW",financial_status="NOT_EVALUATED",next_actor="Ananya - Reviewer",working_data=demo_data(freight_known=True),synthetic=True)
    db.add(nochange); db.flush(); same=demo_data(freight_known=True); same["lines"]=[{**x,"current_buy_unit":x["original_buy_unit"]} for x in same["lines"]]; same["current_freight_status"]="included"; same["current_freight"]="0"; nochange.working_data=same
    expired=Case(organization_id=org.id,reference="A-106",decision_owner_id=users["meera"].id,purchasing_contact="Kavita Rao",purchase_deadline=deadline,proposed_purchase_at=deadline,workflow_status="NEEDS_INPUT",financial_status="INCOMPLETE",next_actor="Rohan - Operations",working_data={**demo_data(freight_known=True),"evidence_expired":True},synthetic=True)
    unsupported=Case(organization_id=org.id,reference="A-104",decision_owner_id=users["meera"].id,purchasing_contact="Kavita Rao",purchase_deadline=deadline,proposed_purchase_at=deadline,workflow_status="UNSUPPORTED",financial_status="NOT_EVALUATED",next_actor="None",working_data={},unsupported_reason="USD and mixed-stock costing are outside the India/INR back-to-back MVP.",synthetic=True)
    othercase=Case(organization_id=other.id,reference="SECRET-1",decision_owner_id=users["outsider"].id,purchasing_contact="Private Buyer",purchase_deadline=deadline,proposed_purchase_at=deadline,workflow_status="DRAFT",financial_status="NOT_EVALUATED",next_actor="Operations",working_data={},synthetic=True)
    db.add_all([expired,unsupported,othercase]); db.add(AuditEvent(organization_id=org.id,case_id=case.id,actor_id=users["rohan"].id,action="DEMO_CASE_CREATED",detail={"synthetic":True}))
    db.commit(); return {"organization_id":org.id,"case_id":case.id,"created":True}
