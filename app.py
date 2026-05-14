import re
from datetime import datetime

ORIGIN_INFERRED = "INFERRED_FROM_CONTEXT"
ORIGIN_SYSTEM_DEFAULT = "SYSTEM_DEFAULT"

def normalize_amount_for_32B(amount_text):
    a = amount_text.strip().replace(" ", "")
    if "," in a and "." in a:
        if a.rfind(",") > a.rfind("."):
            a = a.replace(".", "").replace(",", ".")
        else:
            a = a.replace(",", "")
    elif "," in a:
        a = a.replace(".", "").replace(",", ".")
    return a

def normalize_to_yymmdd(raw):
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 6:
        return digits
    if len(digits) == 8:
        return digits[2:]
    return ""

def infer_field_20_from_text(source_text):
    t = source_text.upper()
    patterns = [
        r"(?:ORDER NO|ORDER NUMBER|REFERENCE|REFERENCIA|OPERACION|OPERACIÓN)\s*[:\-]?\s*([A-Z0-9\-\/]{3,16})"
    ]
    for p in patterns:
        m = re.search(p, t)
        if m:
            candidate = m.group(1).strip()
            if not candidate.startswith("/") and not candidate.endswith("/") and "//" not in candidate:
                return candidate
    return ""

def infer_field_31D_from_text(source_text):
    t = source_text.upper()
    patterns = [
        r"(?:LUGAR Y FECHA DE VENCIMIENTO|EXPIRY(?: PLACE)?(?: AND DATE)?)\s*[:\-]?\s*([0-9]{6,8})\s*[,/\- ]+\s*([A-Z][A-Z ,\-.]{2,40})"
    ]
    for p in patterns:
        m = re.search(p, t)
        if m:
            yymmdd = normalize_to_yymmdd(m.group(1))
            place = re.sub(r"\s{2,}", " ", m.group(2)).strip(" ,.-")
            if yymmdd and place:
                return f"{yymmdd}{place}"
    return ""

def infer_field_32B_from_text(source_text):
    t = source_text.upper()

    anchored = [
        r"(?:DIVISA E IMPORTE|CURRENCY AND AMOUNT|AMOUNT)\s*[:\-]?\s*([A-Z]{3})\s*([0-9][0-9\.,]+)",
        r"(?:DIVISA E IMPORTE|CURRENCY AND AMOUNT|AMOUNT)\s*[:\-]?\s*([0-9][0-9\.,]+)\s*([A-Z]{3})"
    ]
    for p in anchored:
        m = re.search(p, t)
        if m:
            g1, g2 = m.group(1), m.group(2)
            if re.fullmatch(r"[A-Z]{3}", g1):
                ccy, amt = g1, g2
            else:
                amt, ccy = g1, g2
            return f"{ccy}{normalize_amount_for_32B(amt)}"

    return ""

def infer_mt700_defaults(source_text, verified_map):
    t = source_text.upper()
    inferred = {}

    has_lc_context = any(x in t for x in [
        "LETTER OF CREDIT", "DOCUMENTARY CREDIT", "CREDITO DOCUMENTARIO", "CRÉDITO DOCUMENTARIO", "MT700"
    ])

    if not verified_map["field_20"]["accepted"]:
        value = infer_field_20_from_text(source_text)
        if value:
            inferred["field_20"] = {
                "value": value,
                "reason": "Recovered from source reference/order number",
                "origin": ORIGIN_INFERRED
            }

    if not verified_map["field_40A"]["accepted"] and has_lc_context:
        inferred["field_40A"] = {
            "value": "IRREVOCABLE",
            "reason": "Inferred from LC context",
            "origin": ORIGIN_INFERRED
        }

    if not verified_map["field_40E"]["accepted"] and has_lc_context:
        if "EUCP" in t:
            value = "EUCP LATEST VERSION"
        elif "ISP98" in t or "STANDBY" in t:
            value = "ISP LATEST VERSION"
        else:
            value = "UCP LATEST VERSION"
        inferred["field_40E"] = {
            "value": value,
            "reason": "Inferred from applicable rules context",
            "origin": ORIGIN_INFERRED
        }

    if not verified_map["field_31C"]["accepted"]:
        inferred["field_31C"] = {
            "value": datetime.now().strftime("%y%m%d"),
            "reason": "System fallback issue date when absent",
            "origin": ORIGIN_SYSTEM_DEFAULT
        }

    if not verified_map["field_31D"]["accepted"]:
        value = infer_field_31D_from_text(source_text)
        if value:
            inferred["field_31D"] = {
                "value": value,
                "reason": "Recovered from source expiry date/place",
                "origin": ORIGIN_INFERRED
            }

    if not verified_map["field_32B"]["accepted"]:
        value = infer_field_32B_from_text(source_text)
        if value:
            inferred["field_32B"] = {
                "value": value,
                "reason": "Recovered from source currency/amount",
                "origin": ORIGIN_INFERRED
            }

    if not verified_map["field_49"]["accepted"]:
        if any(x in t for x in [
            "WITHOUT CONFIRMATION",
            "WITHOUT ADDING CONFIRMATION",
            "SIN AÑADIR SU CONFIRMACION",
            "SIN AÑADIR SU CONFIRMACIÓN"
        ]):
            inferred["field_49"] = {
                "value": "WITHOUT",
                "reason": "Inferred from no-confirmation wording",
                "origin": ORIGIN_INFERRED
            }

    if not verified_map["field_48"]["accepted"] and has_lc_context:
        inferred["field_48"] = {
            "value": "21",
            "reason": "Default presentation period when absent",
            "origin": ORIGIN_SYSTEM_DEFAULT
        }

    return inferred
