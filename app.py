def infer_mt700_defaults(source_text: str, verified_map: Dict) -> Dict[str, Dict]:
    t = to_upper(source_text)
    inferred = {}

    has_lc_context = any(x in t for x in [
        "LETTER OF CREDIT", "DOCUMENTARY CREDIT", "CREDITO DOCUMENTARIO", "CRÉDITO DOCUMENTARIO", "MT700"
    ])

    if not verified_map["field_20"]["accepted"]:
        inferred20 = infer_field_20_from_text(source_text)
        if inferred20:
            inferred["field_20"] = {
                "value": inferred20,
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
            inferred["field_40E"] = {
                "value": "EUCP LATEST VERSION",
                "reason": "Inferred from eUCP context",
                "origin": ORIGIN_INFERRED
            }
        elif "UCPURR" in t or ("URR" in t and "UCP" in t):
            inferred["field_40E"] = {
                "value": "UCPURR LATEST VERSION",
                "reason": "Inferred from UCP+URR context",
                "origin": ORIGIN_INFERRED
            }
        elif "ISP98" in t or "STANDBY" in t:
            inferred["field_40E"] = {
                "value": "ISP LATEST VERSION",
                "reason": "Inferred from standby/ISP context",
                "origin": ORIGIN_INFERRED
            }
        else:
            inferred["field_40E"] = {
                "value": "UCP LATEST VERSION",
                "reason": "Inferred from standard LC context",
                "origin": ORIGIN_INFERRED
            }

    if not verified_map["field_31C"]["accepted"]:
        inferred["field_31C"] = {
            "value": datetime.now().strftime("%y%m%d"),
            "reason": "System fallback issue date when absent",
            "origin": ORIGIN_SYSTEM_DEFAULT
        }

    if not verified_map["field_31D"]["accepted"]:
        inferred31d = infer_field_31D_from_text(source_text)
        if inferred31d:
            inferred["field_31D"] = {
                "value": inferred31d,
                "reason": "Recovered from source expiry date/place",
                "origin": ORIGIN_INFERRED
            }

    if not verified_map["field_32B"]["accepted"]:
        inferred32b = infer_field_32B_from_text(source_text)
        if inferred32b:
            inferred["field_32B"] = {
                "value": inferred32b,
                "reason": "Recovered from source currency/amount",
                "origin": ORIGIN_INFERRED
            }

    if not verified_map["field_49"]["accepted"]:
        if any(x in t for x in [
            "WITHOUT CONFIRMATION",
            "WITHOUT ADDING CONFIRMATION",
            "SIN AÑADIR SU CONFIRMACIÓN",
            "SIN AÑADIR SU CONFIRMACION",
            "SIN AADIR SU CONFIRMACIN"
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
