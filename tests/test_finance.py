from decimal import Decimal
import pytest
from ternfold.finance import CalculationBlocked, calculate, completeness, fmt_money, line_amount
from ternfold.fixtures import demo_data

def test_reference_current_and_revised_calculations():
    current=calculate(demo_data(freight_known=True),"12","3")
    assert current["revenue"]=="200000.00"
    assert current["original_goods"]=="170000.00"
    assert current["current_goods"]=="178000.00"
    assert current["current_freight"]=="5000.00"
    assert current["original_contribution"]=="30000.00"
    assert current["original_pct"]=="15.00"
    assert current["current_contribution"]=="17000.00"
    assert current["current_pct"]=="8.500"
    assert current["erosion_rupees"]=="13000.00"
    revised=calculate(demo_data(freight_known=True,revised=True),"12","3")
    assert revised["current_goods"]=="172000.00"
    assert revised["current_contribution"]=="23000.00"
    assert revised["current_pct"]=="11.500"
    assert revised["financial_status"]=="BELOW_FLOOR"

def test_rounding_unknown_zero_and_indian_formatting():
    assert line_amount("3","0.335")==Decimal("1.01")
    assert fmt_money("200000")=="₹2,00,000"
    missing=demo_data()
    assert "Confirm current freight, including an evidenced zero when none applies." in completeness(missing)
    with pytest.raises(CalculationBlocked): calculate(missing)
    included=demo_data(freight_known=True); included["current_freight_status"]="included"; included["current_freight"]="0"
    assert calculate(included)["current_freight"]=="0"

def test_zero_revenue_negative_quantity_expiry_and_noncomparable_block():
    zero=demo_data(freight_known=True)
    for line in zero["lines"]: line["sell_unit"]="0"
    result=calculate(zero)
    assert result["current_pct"] is None and result["financial_status"]=="BELOW_FLOOR"
    negative=demo_data(freight_known=True); negative["lines"][0]["qty"]="-1"
    with pytest.raises(CalculationBlocked): calculate(negative)
    for key,value in [("evidence_expired",True),("baseline_comparable",False),("matching_confirmed",False),("tax_basis_confirmed",False)]:
        data=demo_data(freight_known=True); data[key]=value
        with pytest.raises(CalculationBlocked): calculate(data)

def test_no_adverse_change_finishes_normally():
    data=demo_data(freight_known=True)
    data["lines"]=[{**line,"current_buy_unit":line["original_buy_unit"]} for line in data["lines"]]
    data["current_freight_status"]="included"; data["current_freight"]="0"
    result=calculate(data)
    assert result["erosion_rupees"]=="0.00"
    assert result["current_contribution"]=="30000.00"
    assert result["financial_status"]=="WITHIN_THRESHOLDS"
