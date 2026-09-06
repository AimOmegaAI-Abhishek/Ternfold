from __future__ import annotations
from copy import deepcopy
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext

PAISE=Decimal("0.01")

class CalculationBlocked(ValueError):
    def __init__(self,messages:list[str]): self.messages=messages; super().__init__("; ".join(messages))

def dec(value:object,places:int=6,nonnegative:bool=True)->Decimal:
    if value is None or str(value).strip()=="": raise ValueError("Value is unknown")
    try: result=Decimal(str(value))
    except (InvalidOperation,ValueError) as exc: raise ValueError("Enter a valid decimal number") from exc
    if not result.is_finite(): raise ValueError("Enter a finite decimal number")
    if nonnegative and result<0: raise ValueError("Value cannot be negative")
    if max(0,-result.as_tuple().exponent)>places: raise ValueError(f"Use at most {places} decimal places")
    return result

def line_amount(quantity:object,unit_price:object)->Decimal:
    q,p=dec(quantity),dec(unit_price)
    if q<=0: raise ValueError("Quantity must be positive")
    with localcontext() as ctx:
        ctx.prec=60
        return (q*p).quantize(PAISE,rounding=ROUND_HALF_UP)

def charge(data:dict,side:str,key:str)->Decimal|None:
    status=data.get(f"{side}_{key}_status","unknown")
    if status in {"included","confirmed_none"}: return Decimal("0.00")
    if status=="confirmed":
        try: return dec(data.get(f"{side}_{key}")).quantize(PAISE,rounding=ROUND_HALF_UP)
        except ValueError: return None
    return None

def completeness(data:dict)->list[str]:
    problems=[]; lines=data.get("lines") or []
    if not lines: problems.append("Add at least one order line.")
    if len(lines)>15: problems.append("This MVP supports up to 15 order lines.")
    for index,line in enumerate(lines,1):
        try:
            if dec(line.get("qty"))<=0: raise ValueError
            line_amount(line.get("qty"),line.get("sell_unit"))
            line_amount(line.get("qty"),line.get("original_buy_unit"))
            line_amount(line.get("qty"),line.get("current_buy_unit"))
        except ValueError: problems.append(f"Line {index} needs positive quantity and valid net unit amounts.")
        if not line.get("unit") or not line.get("spec"): problems.append(f"Line {index} needs a confirmed unit and specification.")
    checks=(("tax_basis_confirmed","Confirm a consistent net tax basis."),
            ("matching_confirmed","Confirm quantities, units and specifications are comparable."),
            ("applicability_confirmed","Confirm that the supplier evidence applies to this purchase."),
            ("baseline_comparable","Restate the original baseline for the current scope or mark it noncomparable."))
    for key,message in checks:
        if not data.get(key): problems.append(message)
    for side in ("original","current"):
        for key in ("freight","handling","other"):
            if charge(data,side,key) is None: problems.append(f"Confirm {side} {key}, including an evidenced zero when none applies.")
    if data.get("evidence_expired"): problems.append("The applicable supplier evidence is expired for the proposed purchase date.")
    return list(dict.fromkeys(problems))

def calculate(data:dict,min_pct:object="12",erosion_warning_pp:object="3")->dict:
    problems=completeness(data)
    if problems: raise CalculationBlocked(problems)
    with localcontext() as ctx:
        ctx.prec=60
        revenue=original_goods=current_goods=Decimal("0"); rows=[]
        for line in data["lines"]:
            sell=line_amount(line["qty"],line["sell_unit"]); original=line_amount(line["qty"],line["original_buy_unit"]); current=line_amount(line["qty"],line["current_buy_unit"])
            revenue+=sell; original_goods+=original; current_goods+=current
            rows.append({**deepcopy(line),"sell_amount":str(sell),"original_amount":str(original),"current_amount":str(current),"current_line_contribution":str(sell-current)})
        original_shared=sum((charge(data,"original",key) or Decimal("0")) for key in ("freight","handling","other"))
        current_shared=sum((charge(data,"current",key) or Decimal("0")) for key in ("freight","handling","other"))
        original_cost=original_goods+original_shared; current_cost=current_goods+current_shared
        original_contribution=revenue-original_cost; current_contribution=revenue-current_cost
        original_pct=original_contribution/revenue*100 if revenue>0 else None
        current_pct=current_contribution/revenue*100 if revenue>0 else None
        erosion_rupees=original_contribution-current_contribution
        erosion_pp=original_pct-current_pct if original_pct is not None and current_pct is not None else None
        floor=dec(min_pct,nonnegative=False); erosion_limit=dec(erosion_warning_pp,nonnegative=False)
        warnings=[]; below=current_pct is None or current_pct<floor
        if current_pct is None: warnings.append("Contribution percentage is unavailable because revenue is zero.")
        elif below: warnings.append(f"Current contribution is below the configured {fmt_pct(floor)} floor.")
        if erosion_pp is not None and erosion_pp>=erosion_limit: warnings.append(f"Contribution erosion is at least {erosion_limit.quantize(PAISE,rounding=ROUND_HALF_UP):.2f} percentage points.")
        if any(dec(row["current_line_contribution"],places=20,nonnegative=False)<0 for row in rows): warnings.append("At least one line has negative direct contribution before shared charges.")
        return {"lines":rows,"revenue":str(revenue.quantize(PAISE)),"original_goods":str(original_goods.quantize(PAISE)),
                "current_goods":str(current_goods.quantize(PAISE)),"original_freight":str(charge(data,"original","freight") or Decimal("0")),
                "current_freight":str(charge(data,"current","freight") or Decimal("0")),"original_cost":str(original_cost.quantize(PAISE)),
                "current_cost":str(current_cost.quantize(PAISE)),"original_contribution":str(original_contribution.quantize(PAISE)),
                "current_contribution":str(current_contribution.quantize(PAISE)),"original_pct":str(original_pct) if original_pct is not None else None,
                "current_pct":str(current_pct) if current_pct is not None else None,"erosion_rupees":str(erosion_rupees.quantize(PAISE)),
                "erosion_pp":str(erosion_pp) if erosion_pp is not None else None,"warnings":warnings,
                "financial_status":"BELOW_FLOOR" if below else ("WARNING" if warnings else "WITHIN_THRESHOLDS"),
                "min_pct":str(floor),"erosion_warning_pp":str(erosion_limit),"data":deepcopy(data)}

def fmt_money(value:object)->str:
    number=dec(value,places=20,nonnegative=False).quantize(PAISE,rounding=ROUND_HALF_UP); sign="−" if number<0 else ""
    whole,fraction=f"{abs(number):.2f}".split(".")
    if len(whole)>3:
        tail=whole[-3:]; head=whole[:-3]; groups=[]
        while head: groups.append(head[-2:]); head=head[:-2]
        whole=",".join(reversed(groups))+","+tail
    return f"{sign}₹{whole}" if fraction=="00" else f"{sign}₹{whole}.{fraction}"

def fmt_pct(value:object|None)->str:
    return "Unavailable" if value is None else f"{dec(value,places=20,nonnegative=False).quantize(PAISE,rounding=ROUND_HALF_UP):.2f}%"
