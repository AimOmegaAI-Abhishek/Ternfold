from __future__ import annotations
from io import BytesIO
import os
from pathlib import Path
from zoneinfo import ZoneInfo
from decimal import Decimal
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT,TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle,getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph,SimpleDocTemplate,Spacer,Table,TableStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from .finance import fmt_money,fmt_pct

def decision_pdf(case,calculation,decision,owner_name:str,reviewer_name:str)->bytes:
    regular="Helvetica"; bold="Helvetica-Bold"
    font_dir=Path(os.environ.get("WINDIR","C:\\Windows"))/"Fonts"
    if (font_dir/"segoeui.ttf").exists() and (font_dir/"segoeuib.ttf").exists():
        if "Ternfold" not in pdfmetrics.getRegisteredFontNames(): pdfmetrics.registerFont(TTFont("Ternfold",str(font_dir/"segoeui.ttf")))
        if "Ternfold-Bold" not in pdfmetrics.getRegisteredFontNames(): pdfmetrics.registerFont(TTFont("Ternfold-Bold",str(font_dir/"segoeuib.ttf")))
        regular="Ternfold"; bold="Ternfold-Bold"
    buf=BytesIO(); doc=SimpleDocTemplate(buf,pagesize=A4,rightMargin=15*mm,leftMargin=15*mm,topMargin=14*mm,bottomMargin=13*mm)
    styles=getSampleStyleSheet()
    for name in ("Normal","BodyText","Title","Heading2"): styles[name].fontName=bold if name in {"Title","Heading2"} else regular
    styles.add(ParagraphStyle(name="Kicker",parent=styles["Normal"],fontName=bold,fontSize=8,textColor=colors.HexColor("#3d6b62"),spaceAfter=4))
    styles.add(ParagraphStyle(name="Value",parent=styles["Normal"],fontName=bold,fontSize=10))
    story=[]
    if case.synthetic: story.append(Paragraph("TERNFOLD · SYNTHETIC DEMONSTRATION",styles["Kicker"]))
    story += [Paragraph("Margin decision summary",styles["Title"]),Paragraph(f"Order {case.reference} · Reviewed version {calculation.version_number}",styles["Heading2"])]
    snap=calculation.snapshot
    story += [Spacer(1,3*mm),Table([
        ["Reviewed metric","Original estimate","Current reviewed"],
        ["Net sales revenue",fmt_money(snap["revenue"]),fmt_money(snap["revenue"])],
        ["Goods cost",fmt_money(snap["original_goods"]),fmt_money(snap["current_goods"])],
        ["Additional freight",f"{fmt_money(snap['original_freight'])} — included",fmt_money(snap["current_freight"])],
        ["Contribution before overhead",f"{fmt_money(snap['original_contribution'])} / {fmt_pct(snap['original_pct'])}",f"{fmt_money(snap['current_contribution'])} / {fmt_pct(snap['current_pct'])}"],
    ],colWidths=[58*mm,54*mm,54*mm],style=TableStyle([
        ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#e7efec")),("TEXTCOLOR",(0,0),(-1,0),colors.HexColor("#173a34")),
        ("FONTNAME",(0,0),(-1,0),bold),("FONTNAME",(0,1),(0,-1),bold),("FONTNAME",(1,1),(-1,-1),regular),
        ("GRID",(0,0),(-1,-1),0.4,colors.HexColor("#c7d3d0")),("VALIGN",(0,0),(-1,-1),"TOP"),("FONTSIZE",(0,0),(-1,-1),8.5),("LEADING",(0,0),(-1,-1),11),("LEFTPADDING",(0,0),(-1,-1),6),("RIGHTPADDING",(0,0),(-1,-1),6),("TOPPADDING",(0,0),(-1,-1),6),("BOTTOMPADDING",(0,0),(-1,-1),6)
    ])),Spacer(1,5*mm)]
    goods_change=Decimal(snap["current_goods"])-Decimal(snap["original_goods"])
    story += [Paragraph("What changed",styles["Heading2"]),Paragraph(f"Contribution is {fmt_money(snap['erosion_rupees'])} lower than the original estimate: goods cost changed by {fmt_money(goods_change)} and additional freight is {fmt_money(snap['current_freight'])}. This is a variance explanation, not money saved.",styles["BodyText"])]
    ist=ZoneInfo("Asia/Kolkata"); dt=lambda value:value.astimezone(ist).strftime("%d %b %Y, %H:%M IST")
    story += [Spacer(1,4*mm),Paragraph("Customer decision",styles["Heading2"]),Paragraph(f"<b>{decision.choice.replace('_',' ').title()}</b> · {owner_name} · {dt(decision.recorded_at)}",styles["BodyText"]),Paragraph(f"Reason: {decision.rationale}",styles["BodyText"])]
    story += [Spacer(1,4*mm),Paragraph("Purchasing handoff",styles["Heading2"]),Paragraph(decision.purchasing_action,styles["BodyText"]),Spacer(1,4*mm),Paragraph(f"Reviewed by {reviewer_name} at {dt(calculation.reviewed_at)}. Purchasing deadline: {dt(case.purchase_deadline)}",styles["BodyText"])]
    story += [Spacer(1,5*mm),Paragraph("Decision support based on supplied evidence. Not an ERP purchase block or a savings guarantee.",styles["Kicker"])]
    doc.build(story); return buf.getvalue()
