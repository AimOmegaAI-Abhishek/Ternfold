from __future__ import annotations
from datetime import datetime, timezone
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from .finance import charge, fmt_money, fmt_pct


def _fonts():
    font_dir = Path(__file__).resolve().parent / 'fonts'
    for name, filename in [('Ternfold', 'NotoSans-Regular.ttf'), ('Ternfold-Bold', 'NotoSans-Bold.ttf')]:
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name, str(font_dir / filename)))
    pdfmetrics.registerFontFamily('Ternfold', normal='Ternfold', bold='Ternfold-Bold', italic='Ternfold', boldItalic='Ternfold-Bold')


def change_explanation(snap: dict) -> str:
    variance = Decimal(snap['erosion_rupees'])
    movement = f"{fmt_money(abs(variance))} {'lower' if variance > 0 else 'higher'}" if variance else 'unchanged'
    parts = [('goods', Decimal(snap['current_goods']) - Decimal(snap['original_goods']))]
    data = snap.get('data', {})
    for key in ('freight', 'handling', 'other'):
        original = charge(data, 'original', key)
        current = charge(data, 'current', key)
        if key == 'freight':
            original = Decimal(snap['original_freight'])
            current = Decimal(snap['current_freight'])
        if original is not None and current is not None:
            parts.append((key, current - original))
    changes = [f"{label} {fmt_money(abs(amount))} {'higher' if amount > 0 else 'lower'}" for label, amount in parts if amount]
    return f"Contribution is {movement} than the original estimate. " + ('; '.join(changes) + '.' if changes else 'There is no direct-cost variance.')


def decision_pdf(case, calculation, decision, owner_name: str, reviewer_name: str) -> bytes:
    """Render only frozen financial values; arbitrary customer text is always escaped."""
    _fonts()
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, rightMargin=15*mm, leftMargin=15*mm, topMargin=13*mm, bottomMargin=15*mm)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='SummaryBody', fontName='Ternfold', fontSize=8.5, leading=12, spaceAfter=3, splitLongWords=True))
    styles.add(ParagraphStyle(name='SummaryTitle', parent=styles['SummaryBody'], fontName='Ternfold-Bold', fontSize=19, leading=23, spaceAfter=8))
    styles.add(ParagraphStyle(name='SummaryHeading', parent=styles['SummaryBody'], fontName='Ternfold-Bold', fontSize=10, leading=14, spaceBefore=7, spaceAfter=4, keepWithNext=True))
    styles.add(ParagraphStyle(name='SummaryKicker', parent=styles['SummaryBody'], fontName='Ternfold-Bold', fontSize=7, leading=10, textColor=colors.HexColor('#3d6b62')))
    def p(text, style='SummaryBody'):
        return Paragraph(escape(str(text)).replace('\n', '<br/>'), styles[style])
    snap = calculation.snapshot
    context = snap.get('case_context', {})
    reference = context.get('reference', case.reference)
    owner_name = context.get('owner_name', owner_name)
    reviewer_name = context.get('reviewer_name', reviewer_name)
    def dt(value):
        if isinstance(value, str): value = datetime.fromisoformat(value)
        if value.tzinfo is None: value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(ZoneInfo('Asia/Kolkata')).strftime('%d %b %Y, %H:%M IST')
    story = []
    if case.synthetic: story.append(p('TERNFOLD · SYNTHETIC DEMONSTRATION', 'SummaryKicker'))
    story += [p('Margin decision summary', 'SummaryTitle'), p(f'Order {reference} · Reviewed version {calculation.version_number}', 'SummaryHeading')]
    status = snap.get('financial_status', 'UNAVAILABLE')
    qualification = f"Below your {fmt_pct(snap['min_pct'])} floor" if status == 'BELOW_FLOOR' and snap.get('current_pct') is not None else status.replace('_', ' ').title()
    story.append(p(f'Workflow: Decision recorded · Financial: {qualification}'))
    data = snap.get('data', {})
    def freight(side):
        suffix = ' (included)' if data.get(f'{side}_freight_status') == 'included' else ''
        return fmt_money(snap[f'{side}_freight']) + suffix
    rows = [
        ['Reviewed metric', 'Original estimate', 'Current reviewed'],
        ['Net sales revenue', fmt_money(snap['revenue']), fmt_money(snap['revenue'])],
        ['Goods cost', fmt_money(snap['original_goods']), fmt_money(snap['current_goods'])],
        ['Additional freight', freight('original'), freight('current')],
    ]
    for key in ('handling', 'other'):
        original, current = charge(data, 'original', key), charge(data, 'current', key)
        if original is not None and current is not None and (original or current):
            rows.append([key.title() + ' charges', fmt_money(original), fmt_money(current)])
    rows += [
        ['Total direct cost', fmt_money(snap['original_cost']), fmt_money(snap['current_cost'])],
        ['Contribution before overhead', f"{fmt_money(snap['original_contribution'])} / {fmt_pct(snap['original_pct'])}", f"{fmt_money(snap['current_contribution'])} / {fmt_pct(snap['current_pct'])}"],
    ]
    story.append(Table([[p(cell) for cell in row] for row in rows], colWidths=[67*mm, 54*mm, 54*mm], repeatRows=1, style=TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#e7efec')),
        ('GRID', (0,0), (-1,-1), .35, colors.HexColor('#c7d3d0')),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('LEFTPADDING', (0,0), (-1,-1), 7), ('RIGHTPADDING', (0,0), (-1,-1), 7),
        ('TOPPADDING', (0,0), (-1,-1), 5), ('BOTTOMPADDING', (0,0), (-1,-1), 5),
    ])))
    story += [p('What changed', 'SummaryHeading'), p(change_explanation(snap))]
    for warning in snap.get('warnings', []): story.append(p(warning))
    story += [p('Customer decision', 'SummaryHeading'), p(f"{decision.choice.replace('_', ' ').title()} · {owner_name} · {dt(decision.recorded_at)}"), p(f'Reason: {decision.rationale}')]
    story += [p('Purchasing handoff', 'SummaryHeading'), p(decision.purchasing_action)]
    story += [p('Review record', 'SummaryHeading'), p(f'Reviewed by {reviewer_name} at {dt(calculation.reviewed_at)}. Purchasing deadline: {dt(context.get("purchase_deadline", case.purchase_deadline))}'), p(f'Calculation: {calculation.id} · Decision: {decision.id}', 'SummaryKicker')]
    story += [Spacer(1,3*mm), p('Decision support based on supplied evidence. Purchasing executes the order in its existing system. Variance is not attributed savings.', 'SummaryKicker')]
    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont('Ternfold', 7)
        canvas.setFillColor(colors.HexColor('#64736f'))
        canvas.drawString(15*mm, 8*mm, f'Ternfold · Reviewed v{calculation.version_number}')
        canvas.drawRightString(A4[0]-15*mm, 8*mm, f'Page {document.page}')
        canvas.restoreState()
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()
