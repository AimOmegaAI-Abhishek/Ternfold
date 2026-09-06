from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
import tomllib
from pypdf import PdfReader
from ternfold.finance import calculate
from ternfold.fixtures import demo_data
from ternfold.reports import decision_pdf, change_explanation


def report_fixture(data=None, reason='Honour the customer commitment; supplier terms and delivery confirmed.'):
    now=datetime(2026,9,6,12,tzinfo=timezone.utc)
    snap=calculate(data or demo_data(freight_known=True,revised=True))
    case=SimpleNamespace(synthetic=True,reference='A-107',purchase_deadline=now)
    calc=SimpleNamespace(id='calculation-v2',version_number=2,snapshot=snap,reviewed_at=now)
    decision=SimpleNamespace(id='decision-v2',choice='proceed',recorded_at=now,rationale=reason,purchasing_action='Kavita: place the order using reviewed v2: goods ₹1,72,000; freight ₹5,000; contribution ₹23,000 / 11.50%.')
    return case,calc,decision


def test_reference_report_is_one_page_and_matches_frozen_values():
    case,calc,decision=report_fixture()
    pdf=decision_pdf(case,calc,decision,'Meera','Assigned reviewer')
    reader=PdfReader(BytesIO(pdf)); text=' '.join(page.extract_text() for page in reader.pages)
    assert len(reader.pages)==1
    for expected in ['₹2,00,000','₹1,72,000','₹5,000','₹23,000','11.50%','12.00%','Meera','Reviewed version 2','decision-v2','calculation-v2','(included)']:
        assert expected in text
    fonts=reader.pages[0]['/Resources']['/Font']
    assert any('NotoSans' in str(font.get_object().get('/BaseFont')) for font in fonts.values())


def test_untrusted_long_text_is_escaped_and_never_clipped():
    reason=('Buyer <b>literal terms</b> & Supplier <unclosed> ' * 100) + ' END OF REASON'
    case,calc,decision=report_fixture(reason=reason)
    case.reference='Order <tag> & '+ 'long-reference-'*50
    pdf=decision_pdf(case,calc,decision,'Meera & Partners <b>','Reviewer <invalid>')
    reader=PdfReader(BytesIO(pdf)); text=' '.join(page.extract_text() for page in reader.pages)
    assert '<b>literal terms</b>' in text
    assert 'END OF REASON' in text and 'decision-v2' in text
    assert len(reader.pages)>1


def test_variance_explains_all_charges_and_freight_is_not_always_included():
    data=demo_data(freight_known=True)
    data.update(original_freight_status='confirmed',original_freight='2000',original_handling_status='confirmed',original_handling='300',current_handling_status='confirmed',current_handling='500',current_other_status='confirmed',current_other='100')
    case,calc,decision=report_fixture(data=data)
    explanation=change_explanation(calc.snapshot)
    for expected in ['goods ₹8,000 higher','freight ₹3,000 higher','handling ₹200 higher','other ₹100 higher']:
        assert expected in explanation
    text=PdfReader(BytesIO(decision_pdf(case,calc,decision,'Meera','Reviewer'))).pages[0].extract_text()
    assert '(included)' not in text
    assert 'Handling charges' in text and 'Other charges' in text


def test_unchanged_and_improved_explanations():
    data=demo_data(freight_known=True)
    data['current_freight_status']='included'
    for line in data['lines']: line['current_buy_unit']=line['original_buy_unit']
    assert 'unchanged' in change_explanation(calculate(data))
    data['lines'][0]['current_buy_unit']='800'
    assert '₹5,000 higher than' in change_explanation(calculate(data))


def test_vercel_configuration_uses_explicit_fastapi_entrypoint_and_india():
    import json
    config=tomllib.loads(Path('pyproject.toml').read_text(encoding='utf-8'))
    assert config['tool']['vercel']['entrypoint']=='ternfold.app:app'
    assert json.loads(Path('vercel.json').read_text())['regions']==['bom1']
