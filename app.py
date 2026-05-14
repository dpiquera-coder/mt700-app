from __future__ import annotations

import streamlit as st
from groq import Groq
from io import BytesIO
import json
import re
import subprocess
import tempfile
import shutil
from datetime import datetime
from math import hypot

try:
    import fitz
except Exception:
    fitz = None

try:
    import docx
except Exception:
    docx = None

try:
    from PIL import Image, ImageOps
except Exception:
    Image = None

try:
    import pytesseract
    from pytesseract import Output
except Exception:
    pytesseract = None
    Output = None


st.set_page_config(
    page_title="MT700 Generator Anti-Hallucination v7.0",
    layout="wide",
    page_icon="🏦"
)

client = Groq(api_key=st.secrets["GROQ_API_KEY"])
files = st.file_uploader("Sube documentos", accept_multiple_files=True)

ALLOWED_TAGS = [
    "27", "20", "40A", "40E", "31C", "31D", "50", "59", "32B", "39A",
    "41A", "42C", "43P", "43T", "44E", "44F", "44C",
    "45A", "46A", "47A", "48", "49", "57A", "71D", "78", "72Z"
]

MANDATORY_IN_SCOPE = ["27", "20", "40A", "31C", "40E", "31D", "50", "59", "32B", "41A", "49"]

FIELD_KEYS = [
    "field_27", "field_20", "field_40A", "field_40E", "field_31C", "field_31D",
    "field_50", "field_59", "field_32B", "field_39A", "field_41A", "field_42C",
    "field_43P", "field_43T", "field_44E", "field_44F", "field_44C",
    "field_45A", "field_46A", "field_47A", "field_48", "field_49",
    "field_57A", "field_71D", "field_78", "field_72Z"
]

FIELD_TO_TAG = {
    "field_27": "27", "field_20": "20", "field_40A": "40A", "field_40E": "40E",
    "field_31C": "31C", "field_31D": "31D", "field_50": "50", "field_59": "59",
    "field_32B": "32B", "field_39A": "39A", "field_41A": "41A", "field_42C": "42C",
    "field_43P": "43P", "field_43T": "43T", "field_44E": "44E", "field_44F": "44F",
    "field_44C": "44C", "field_45A": "45A", "field_46A": "46A", "field_47A": "47A",
    "field_48": "48", "field_49": "49", "field_57A": "57A", "field_71D": "71D",
    "field_78": "78", "field_72Z": "72Z"
}

TAG_TO_FIELD = {v: k for k, v in FIELD_TO_TAG.items()}

NARRATIVE_FIELDS = {"field_45A", "field_46A", "field_47A", "field_71D", "field_78", "field_72Z"}
PARTY_FIELDS = {"field_50", "field_59"}

VALID_40A_CODES = {
    "IRREVOCABLE",
    "IRREVOCABLE TRANSFERABLE",
    "IRREVOCABLE STANDBY",
    "IRREVOC TRANS STANDBY"
}

VALID_40E_CODES = {
    "UCP LATEST VERSION",
    "EUCP LATEST VERSION",
    "EUCPURR LATEST VERSION",
    "ISP LATEST VERSION",
    "OTHR"
}

VALID_49_CODES = {"CONFIRM", "MAY ADD", "WITHOUT"}
VALID_41A_CODES = {"BY ACCEPTANCE", "BY DEF PAYMENT", "BY MIXED PYMT", "BY NEGOTIATION", "BY PAYMENT"}
VALID_43_CODES = {"ALLOWED", "CONDITIONAL", "NOT ALLOWED"}

ORIGIN_EXTRACTED = "EXTRACTED"
ORIGIN_INFERRED = "INFERRED_FROM_CONTEXT"
ORIGIN_SYSTEM_DEFAULT = "SYSTEM_DEFAULT"
ORIGIN_OPERATIONAL_DEFAULT = "OPERATIONAL_DEFAULT"
ORIGIN_DIRECT_OCR_MT700 = "DIRECT_OCR_MT700"
ORIGIN_VISUAL_CHECKBOX = "VISUAL_CHECKBOX"

BANK_HINT_WORDS = {"BANK", "BRANCH", "SWIFT", "BIC", "ACCOUNT", "ACCNO", "A/C", "CONSTRUCTION BANK", "SANTANDER"}


def safe_str(v):
    if v is None:
        return ""
    return str(v).strip()


def to_upper(v):
    return safe_str(v).upper()


def clean_text(text):
    text = safe_str(text).replace("\xa0", " ")
    text = "".join(c for c in text if c.isprintable() or c in "\n\t")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text[:100000].strip()


def clean_value(text):
    t = to_upper(text)
    t = re.sub(r"[ ]{2,}", " ", t)
    t = re.sub(r" *\n *", "\n", t)
    return t.strip()


def safe_json_load(text):
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return {}
    return {}


def tesseract_available():
    return shutil.which("tesseract") is not None and pytesseract is not None and Image is not None and Output is not None


def extract_pdf_text_native(data):
    if not fitz:
        return ""
    try:
        doc = fitz.open(stream=data, filetype="pdf")
        pages = []
        for i in range(min(doc.page_count, 12)):
            pages.append(doc[i].get_text("text"))
        return "\n".join(pages)
    except Exception:
        return ""


def extract_pdf_ocr_all_pages(data, max_pages=6):
    if not fitz or not tesseract_available():
        return ""
    try:
        doc = fitz.open(stream=data, filetype="pdf")
        out = []
        for i in range(min(doc.page_count, max_pages)):
            page = doc[i]
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            txt = pytesseract.image_to_string(img, lang="spa+eng")
            out.append(f"==PAGE {i+1}==\n{txt}")
        return "\n\n".join(out)
    except Exception:
        return ""


def pdf_first_page_image(data, zoom=2.5):
    if not fitz or Image is None:
        return None
    try:
        doc = fitz.open(stream=data, filetype="pdf")
        page = doc[0]
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        return img
    except Exception:
        return None


def preprocess_for_ocr(img):
    if Image is None:
        return img
    gray = ImageOps.grayscale(img)
    return gray


def image_words_with_boxes(img):
    if not tesseract_available() or img is None:
        return []
    try:
        data = pytesseract.image_to_data(preprocess_for_ocr(img), lang="spa+eng", output_type=Output.DICT, config="--psm 6")
        words = []
        n = len(data["text"])
        for i in range(n):
            txt = safe_str(data["text"][i])
            conf = float(data["conf"][i]) if safe_str(data["conf"][i]) not in {"", "-1"} else -1
            if not txt:
                continue
            words.append({
                "text": to_upper(txt),
                "left": int(data["left"][i]),
                "top": int(data["top"][i]),
                "width": int(data["width"][i]),
                "height": int(data["height"][i]),
                "conf": conf,
                "cx": int(data["left"][i]) + int(data["width"][i]) / 2,
                "cy": int(data["top"][i]) + int(data["height"][i]) / 2
            })
        return words
    except Exception:
        return []


def semantic_field_check(field_key, value):
    v = to_upper(value)

    if field_key == "field_20":
        if len(v) > 16:
            return False, "20 exceeds 16 characters"
        if v.startswith("/") or v.endswith("/") or "//" in v:
            return False, "20 invalid slashes"

    elif field_key == "field_31C":
        if not re.fullmatch(r"\d{6}", v):
            return False, "31C invalid"

    elif field_key == "field_31D":
        m = re.match(r"^(\d{6})(.+)$", v)
        if not m:
            return False, "31D invalid"

    elif field_key == "field_32B":
        if not re.fullmatch(r"[A-Z]{3}[0-9][0-9,\.]*", v.replace(" ", "")):
            return False, "32B invalid"

    elif field_key == "field_39A":
        if not re.fullmatch(r"\d{1,2}/\d{1,2}", v):
            return False, "39A invalid"

    elif field_key == "field_40A":
        if v not in VALID_40A_CODES:
            return False, "40A invalid"

    elif field_key == "field_40E":
        if v not in VALID_40E_CODES and not v.startswith("OTHR"):
            return False, "40E invalid"

    elif field_key == "field_41A":
        if "BY " not in v or not any(code in v for code in VALID_41A_CODES):
            return False, "41A invalid"

    elif field_key in {"field_43P", "field_43T"}:
        if v not in VALID_43_CODES:
            return False, "43 invalid"

    elif field_key == "field_49":
        if v not in VALID_49_CODES:
            return False, "49 invalid"

    elif field_key == "field_50":
        if any(x in v for x in BANK_HINT_WORDS):
            return False, "50 looks like bank"

    elif field_key == "field_59":
        if any(x in v for x in BANK_HINT_WORDS):
            return False, "59 looks like bank"

    return True, ""


def call_llm_json(system_prompt, user_text, max_tokens=2200):
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": system_prompt + "\nReturn only valid JSON object."},
            {"role": "user", "content": user_text[:22000]}
        ],
        response_format={"type": "json_object"},
        temperature=0,
        max_tokens=max_tokens
    )
    return safe_json_load(response.choices[0].message.content or "{}")


SYSTEM_EXTRACTION_PROMPT = """
Extract MT700 candidate fields from source text.
Return only JSON.
Keys:
field_27, field_20, field_40A, field_40E, field_31C, field_31D,
field_50, field_59, field_32B, field_39A, field_41A, field_42C,
field_43P, field_43T, field_44E, field_44F, field_44C,
field_45A, field_46A, field_47A, field_48, field_49,
field_57A, field_71D, field_78, field_72Z

Each key:
{
  "value": string or null,
  "evidence": string or null,
  "found": boolean,
  "confidence": integer
}
No hallucinations. Evidence must be literal.
"""

SYSTEM_NARRATIVE_REWRITE_PROMPT = """
Rewrite only supported MT700 narrative values into concise professional uppercase banking English.
Return only JSON object with same keys and string values.
Do not add unsupported facts.
"""


def empty_extraction_map():
    out = {}
    for key in FIELD_KEYS:
        out[key] = {"value": None, "evidence": None, "found": False, "confidence": 0, "origin": ORIGIN_EXTRACTED}
    return out


def parse_extraction_object(data):
    out = empty_extraction_map()
    for key in FIELD_KEYS:
        raw = data.get(key, {}) if isinstance(data, dict) else {}
        if not isinstance(raw, dict):
            raw = {}
        out[key] = {
            "value": clean_value(raw.get("value")) if raw.get("value") is not None else None,
            "evidence": clean_text(raw.get("evidence")) if raw.get("evidence") is not None else None,
            "found": bool(raw.get("found", False)),
            "confidence": int(raw.get("confidence", 0) or 0),
            "origin": ORIGIN_EXTRACTED
        }
    return out


def normalize_amount_for_32B(amount_text):
    a = safe_str(amount_text).strip().replace(" ", "")
    if "," in a and "." in a:
        if a.rfind(",") > a.rfind("."):
            a = a.replace(".", "").replace(",", ".")
        else:
            a = a.replace(",", "")
    elif "," in a:
        a = a.replace(".", "").replace(",", ".")
    return a


def normalize_to_yymmdd(raw):
    digits = re.sub(r"\D", "", safe_str(raw))
    if len(digits) == 6:
        return digits
    if len(digits) == 8:
        return digits[2:]
    return ""


def infer_bic_from_text(source_text):
    t = to_upper(source_text)
    patterns = [
        r"SWIFT\.?\s*([A-Z0-9]{8,11})",
        r"\b([A-Z]{6}[A-Z0-9]{2}(?:[A-Z0-9]{3})?)\b"
    ]
    for p in patterns:
        for m in re.finditer(p, t):
            bic = m.group(1)
            if len(bic) in (8, 11):
                return bic
    return ""


def nearest_word(words, target_texts, anchor=None, y_tol=35, x_dir="any"):
    target_set = {to_upper(x) for x in target_texts}
    candidates = [w for w in words if w["text"] in target_set]
    if not candidates:
        return None
    if anchor is None:
        return candidates[0]

    best = None
    best_score = 10**9
    for w in candidates:
        if abs(w["cy"] - anchor["cy"]) > y_tol:
            continue
        if x_dir == "right" and w["cx"] < anchor["cx"]:
            continue
        if x_dir == "left" and w["cx"] > anchor["cx"]:
            continue
        score = hypot(w["cx"] - anchor["cx"], w["cy"] - anchor["cy"])
        if score < best_score:
            best_score = score
            best = w
    return best


def all_words_matching(words, pattern):
    rx = re.compile(pattern)
    return [w for w in words if rx.fullmatch(w["text"])]


def nearest_x_to_anchor(words, anchor_words, x_pattern=r"X", y_band=45, x_window=220):
    anchors = [w for w in words if w["text"] in {to_upper(a) for a in anchor_words}]
    xs = [w for w in words if re.fullmatch(x_pattern, w["text"])]
    best_pair = None
    best_score = 10**9
    for a in anchors:
        for x in xs:
            if abs(x["cy"] - a["cy"]) <= y_band and abs(x["cx"] - a["cx"]) <= x_window:
                score = hypot(x["cx"] - a["cx"], x["cy"] - a["cy"])
                if score < best_score:
                    best_score = score
                    best_pair = (a, x)
    return best_pair


def option_nearest_to_x(words, x_word, option_texts, y_tol=45, x_window=350):
    opts = []
    for w in words:
        if w["text"] in {to_upper(o) for o in option_texts}:
            if abs(w["cy"] - x_word["cy"]) <= y_tol and abs(w["cx"] - x_word["cx"]) <= x_window:
                opts.append(w)
    if not opts:
        return ""
    opts.sort(key=lambda w: hypot(w["cx"] - x_word["cx"], w["cy"] - x_word["cy"]))
    return opts[0]["text"]


def visual_checkbox_inference(words, source_text):
    out = {}

    # 41A
    pair = nearest_x_to_anchor(words, ["PAGO", "ACEPTACION", "NEGOCIACION", "DIFERIDO"], y_band=45, x_window=280)
    if pair:
        _, xw = pair
        choice = option_nearest_to_x(words, xw, ["PAGO", "ACEPTACION", "NEGOCIACION", "DIFERIDO"], y_tol=45, x_window=320)
        method_map = {
            "PAGO": "BY PAYMENT",
            "ACEPTACION": "BY ACCEPTANCE",
            "NEGOCIACION": "BY NEGOTIATION",
            "DIFERIDO": "BY DEF PAYMENT"
        }
        bic = infer_bic_from_text(source_text)
        if choice in method_map and bic:
            value = f"{bic} {method_map[choice]}"
            ok, _ = semantic_field_check("field_41A", value)
            if ok:
                out["field_41A"] = value

    # 39A
    perc_words = [w for w in words if re.fullmatch(r"10|5", w["text"])]
    x_words = [w for w in words if w["text"] == "X"]
    acceptable_words = [w for w in words if w["text"] in {"ACCEPTABLE", "QUANTITY", "AMOUNT"}]
    best_tol = ""
    best_score = 10**9
    for xw in x_words:
        for pw in perc_words:
            if abs(xw["cy"] - pw["cy"]) <= 50 and abs(xw["cx"] - pw["cx"]) <= 220:
                near_acc = any(abs(pw["cy"] - aw["cy"]) <= 60 and abs(pw["cx"] - aw["cx"]) <= 260 for aw in acceptable_words)
                if near_acc:
                    score = hypot(xw["cx"] - pw["cx"], xw["cy"] - pw["cy"])
                    if score < best_score:
                        best_score = score
                        best_tol = f"{pw['text']}/{pw['text']}"
    if best_tol:
        out["field_39A"] = best_tol

    # 43P
    pair_43p = nearest_x_to_anchor(words, ["AUTORIZADAS", "PROHIBIDAS"], y_band=45, x_window=280)
    if pair_43p:
        _, xw = pair_43p
        choice = option_nearest_to_x(words, xw, ["AUTORIZADAS", "PROHIBIDAS", "CONDICIONALES"], y_tol=45, x_window=320)
        if choice == "AUTORIZADAS":
            out["field_43P"] = "ALLOWED"
        elif choice == "PROHIBIDAS":
            out["field_43P"] = "NOT ALLOWED"
        elif choice == "CONDICIONALES":
            out["field_43P"] = "CONDITIONAL"

    # 43T
    pair_43t = nearest_x_to_anchor(words, ["PERMITIDOS", "PROHIBIDOS"], y_band=45, x_window=280)
    if pair_43t:
        _, xw = pair_43t
        choice = option_nearest_to_x(words, xw, ["PERMITIDOS", "PROHIBIDOS", "CONDICIONALES"], y_tol=45, x_window=320)
        if choice == "PERMITIDOS":
            out["field_43T"] = "ALLOWED"
        elif choice == "PROHIBIDOS":
            out["field_43T"] = "NOT ALLOWED"
        elif choice == "CONDICIONALES":
            out["field_43T"] = "CONDITIONAL"

    # 46A
    doc_map = {
        "FACTURA": "SIGNED COMMERCIAL INVOICE IN 3 COPIES",
        "BILL": "FULL SET CLEAN ON BOARD BILL OF LADING PLUS 3 NON NEGOTIABLE COPIES",
        "POLIZA": "INSURANCE POLICY OR CERTIFICATE",
        "PÓLIZA": "INSURANCE POLICY OR CERTIFICATE",
        "ORIGEN": "CERTIFICATE OF ORIGIN ISSUED BY COMPETENT AUTHORITIES",
        "LISTA": "PACKING LIST IN 3 COPIES",
        "PACKING": "PACKING LIST IN 3 COPIES",
        "FORM": 'FORM "A" AS PER ATTACHED SHEET',
        "CMR": "INTERNATIONAL ROAD WAYBILL (CMR)",
        "CIM": "RAIL WAYBILL (CIM)"
    }
    docs = []
    x_words = [w for w in words if w["text"] == "X"]
    for xw in x_words:
        nearby = [w for w in words if abs(w["cy"] - xw["cy"]) <= 35 and 0 <= (w["cx"] - xw["cx"]) <= 550]
        nearby_texts = {w["text"] for w in nearby}
        for token, doc_val in doc_map.items():
            if token in nearby_texts:
                docs.append(doc_val)
    docs = list(dict.fromkeys(docs))
    if docs:
        out["field_46A"] = "\n".join(f"+ {d}" for d in docs)

    # 71D
    pair_71d = nearest_x_to_anchor(words, ["BENEFICIARIO", "ORDENANTE"], y_band=45, x_window=280)
    if pair_71d:
        _, xw = pair_71d
        choice = option_nearest_to_x(words, xw, ["BENEFICIARIO", "ORDENANTE"], y_tol=45, x_window=280)
        if choice == "BENEFICIARIO":
            out["field_71D"] = "ALL BANKING CHARGES OUTSIDE SPAIN ARE FOR BENEFICIARY'S ACCOUNT"
        elif choice == "ORDENANTE":
            out["field_71D"] = "ALL BANKING CHARGES OUTSIDE SPAIN ARE FOR APPLICANT'S ACCOUNT"

    return out


def infer_field_20_from_text(source_text):
    t = to_upper(source_text)
    patterns = [
        r"ORDER\s*NO\.?\s*[:\-]?\s*([A-Z0-9\-\/]{3,16})",
        r"ORDER\s*NUMBER\.?\s*[:\-]?\s*([A-Z0-9\-\/]{3,16})",
        r"N[ÚU]MERO DE PROPUESTA ELECTR[ÓO]NICA\s*[:\-]?\s*([0-9 ]{8,25})",
        r"REFERENCIA\s*[:\-]?\s*([A-Z0-9\-\/]{3,16})"
    ]
    for p in patterns:
        m = re.search(p, t)
        if m:
            candidate = re.sub(r"\s+", "", m.group(1))[:16]
            ok, _ = semantic_field_check("field_20", candidate)
            if ok:
                return candidate
    return ""


def infer_field_31D_from_text(source_text):
    t = to_upper(source_text)
    m = re.search(r"LUGAR Y FECHA DE VENCIMIENTO\s*([0-9]{6,8})", t)
    if m:
        d = normalize_to_yymmdd(m.group(1))
        if d:
            for place in ["HONG KONG", "MADRID", "BARCELONA"]:
                if place in t:
                    return f"{d}{place}"
    return ""


def infer_field_32B_from_text(source_text):
    t = to_upper(source_text)
    pats = [
        r"DIVISA E IMPORTE\s*([0-9][0-9\.,]+)\s*([A-Z]{3})",
        r"DIVISA E IMPORTE\s*([A-Z]{3})\s*([0-9][0-9\.,]+)"
    ]
    for p in pats:
        m = re.search(p, t)
        if m:
            g1, g2 = m.group(1), m.group(2)
            if re.fullmatch(r"[A-Z]{3}", g1):
                ccy, amt = g1, g2
            else:
                amt, ccy = g1, g2
            value = f"{ccy}{normalize_amount_for_32B(amt)}"
            ok, _ = semantic_field_check("field_32B", value)
            if ok:
                return value
    return ""


def verify_map_defaults(source_text, verified_map, visual_map):
    t = to_upper(source_text)

    if not verified_map["field_27"]["accepted"]:
        verified_map["field_27"] = {"value": "1/1", "evidence": "", "found": True, "confidence": 100, "accepted": True, "reason": "Operational default", "origin": ORIGIN_OPERATIONAL_DEFAULT}

    if not verified_map["field_20"]["accepted"]:
        v = infer_field_20_from_text(source_text)
        if v:
            verified_map["field_20"] = {"value": v, "evidence": "", "found": True, "confidence": 85, "accepted": True, "reason": "Recovered from text", "origin": ORIGIN_INFERRED}

    if not verified_map["field_40A"]["accepted"] and any(x in t for x in ["CREDITO DOCUMENTARIO", "CRÉDITO DOCUMENTARIO", "IRREVOCABLE"]):
        verified_map["field_40A"] = {"value": "IRREVOCABLE", "evidence": "", "found": True, "confidence": 85, "accepted": True, "reason": "Recovered from text", "origin": ORIGIN_INFERRED}

    if not verified_map["field_40E"]["accepted"] and ("PUBLICACION N 600" in t or "PUBLICACIÓN N 600" in t or "UCP" in t):
        verified_map["field_40E"] = {"value": "UCP LATEST VERSION", "evidence": "", "found": True, "confidence": 85, "accepted": True, "reason": "Recovered from text", "origin": ORIGIN_INFERRED}

    if not verified_map["field_31C"]["accepted"]:
        verified_map["field_31C"] = {"value": datetime.now().strftime("%y%m%d"), "evidence": "", "found": True, "confidence": 100, "accepted": True, "reason": "System default", "origin": ORIGIN_SYSTEM_DEFAULT}

    if not verified_map["field_31D"]["accepted"]:
        v = infer_field_31D_from_text(source_text)
        if v:
            verified_map["field_31D"] = {"value": v, "evidence": "", "found": True, "confidence": 85, "accepted": True, "reason": "Recovered from text", "origin": ORIGIN_INFERRED}

    if not verified_map["field_32B"]["accepted"]:
        v = infer_field_32B_from_text(source_text)
        if v:
            verified_map["field_32B"] = {"value": v, "evidence": "", "found": True, "confidence": 85, "accepted": True, "reason": "Recovered from text", "origin": ORIGIN_INFERRED}

    for fk, val in visual_map.items():
        if not verified_map[fk]["accepted"]:
            ok, _ = semantic_field_check(fk, val)
            if ok or fk in {"field_46A", "field_71D"}:
                verified_map[fk] = {"value": val, "evidence": "", "found": True, "confidence": 90, "accepted": True, "reason": "Recovered from visual checkbox OCR", "origin": ORIGIN_VISUAL_CHECKBOX}

    if not verified_map["field_49"]["accepted"] and any(x in t for x in ["SIN AADIR SU CONFIRMACIN", "SIN AÑADIR SU CONFIRMACION", "WITHOUT CONFIRMATION"]):
        verified_map["field_49"] = {"value": "WITHOUT", "evidence": "", "found": True, "confidence": 85, "accepted": True, "reason": "Recovered from text", "origin": ORIGIN_INFERRED}

    if not verified_map["field_48"]["accepted"]:
        m = re.search(r"DENTRO DE LOS\s+(\d{1,3})\s+D[IÍ]AS", t)
        if m:
            verified_map["field_48"] = {"value": m.group(1), "evidence": "", "found": True, "confidence": 85, "accepted": True, "reason": "Recovered from text", "origin": ORIGIN_INFERRED}
        else:
            verified_map["field_48"] = {"value": "21", "evidence": "", "found": True, "confidence": 100, "accepted": True, "reason": "System default", "origin": ORIGIN_SYSTEM_DEFAULT}

    return verified_map


def verify_extraction(extracted):
    verified = {}
    for key in FIELD_KEYS:
        item = extracted.get(key, {"value": None, "evidence": None, "found": False, "confidence": 0, "origin": ORIGIN_EXTRACTED})
        value = item.get("value")
        evidence = item.get("evidence")
        found = bool(item.get("found"))
        accepted = False
        reason = "Rejected"

        if found and value:
            ok, msg = semantic_field_check(key, value)
            if ok or key in NARRATIVE_FIELDS or key in PARTY_FIELDS:
                accepted = True
                reason = "Accepted"
            else:
                reason = msg

        verified[key] = {
            "value": value if accepted else "",
            "evidence": evidence if accepted else "",
            "found": accepted,
            "confidence": item.get("confidence", 0) if accepted else 0,
            "accepted": accepted,
            "reason": reason,
            "origin": item.get("origin", "") if accepted else ""
        }
    return verified


def build_mt700_from_verified_map(verified_map):
    lines = ["{1:F01BSCHESMMXXXX0123000001}{2:I700BSCHHKHHXXXXN2020}{4:"]
    for field_key in FIELD_KEYS:
        item = verified_map.get(field_key, {})
        if item.get("accepted") and item.get("value"):
            lines.append(f":{FIELD_TO_TAG[field_key]}:{clean_value(item['value'])}")
    lines.append("-}")
    return "\n".join(lines).upper()


def validate_mt700(mt700, verified_map):
    issues = []
    warnings = []

    for mandatory_tag in MANDATORY_IN_SCOPE:
        key = TAG_TO_FIELD[mandatory_tag]
        if not verified_map.get(key, {}).get("accepted", False):
            warnings.append(f"Mandatory field omitted :{mandatory_tag}:")

    score = max(0, 100 - len(issues) * 10 - len(warnings) * 3)
    return {"is_valid": len(issues) == 0, "score": score, "issues": issues, "warnings": warnings}


if st.button("🚀 Generar MT700"):
    if not files:
        st.warning("Sube documentos")
    else:
        source_parts = []
        pdf_first_image = None
        debug = []

        for f in files:
            data = f.getvalue()
            name = f.name.lower()
            txt = ""

            if name.endswith(".pdf"):
                native = extract_pdf_text_native(data)
                ocr = extract_pdf_ocr_all_pages(data, max_pages=6)
                txt = clean_text((native or "") + "\n\n" + (ocr or ""))
                if pdf_first_image is None:
                    pdf_first_image = pdf_first_page_image(data, zoom=2.8)
            elif name.endswith(".docx") and docx is not None:
                try:
                    d = docx.Document(BytesIO(data))
                    txt = "\n".join(p.text for p in d.paragraphs)
                except Exception:
                    txt = ""
            elif name.endswith(".doc"):
                try:
                    with tempfile.NamedTemporaryFile(delete=True, suffix=".doc") as tmp:
                        tmp.write(data)
                        tmp.flush()
                        result = subprocess.run(["antiword", tmp.name], capture_output=True, text=True, timeout=20)
                        if result.returncode == 0:
                            txt = result.stdout
                except Exception:
                    txt = ""
            else:
                try:
                    txt = data.decode("utf-8", errors="ignore")
                except Exception:
                    txt = ""

            txt = clean_text(txt)
            source_parts.append(f"### {f.name}\n{txt}")
            debug.append({"file": f.name, "chars": len(txt), "preview": txt[:800]})

        source_text = "\n\n".join(source_parts)

        st.expander("Debug texto", expanded=False).write(source_text[:12000])

        raw_extraction = call_llm_json(SYSTEM_EXTRACTION_PROMPT, source_text[:22000], max_tokens=2600)
        extracted = parse_extraction_object(raw_extraction)
        verified_map = verify_extraction(extracted)

        visual_map = {}
        words = image_words_with_boxes(pdf_first_image) if pdf_first_image is not None else []
        if words:
            visual_map = visual_checkbox_inference(words, source_text)

        verified_map = verify_map_defaults(source_text, verified_map, visual_map)

        rewrite_payload = {}
        for key in NARRATIVE_FIELDS:
            if verified_map.get(key, {}).get("accepted") and verified_map[key].get("value"):
                rewrite_payload[key] = verified_map[key]["value"]

        if rewrite_payload:
            rewritten = call_llm_json(SYSTEM_NARRATIVE_REWRITE_PROMPT, json.dumps(rewrite_payload, ensure_ascii=False), max_tokens=1400)
            for key, val in rewritten.items():
                if key in rewrite_payload and safe_str(val):
                    verified_map[key]["value"] = clean_value(val)

        mt700 = build_mt700_from_verified_map(verified_map)
        validation = validate_mt700(mt700, verified_map)

        st.session_state["source_text"] = source_text
        st.session_state["debug"] = debug
        st.session_state["visual_map"] = visual_map
        st.session_state["verified_map"] = verified_map
        st.session_state["mt700"] = mt700
        st.session_state["validation"] = validation
        st.success("Proceso completado")

if "mt700" in st.session_state:
    st.text_area("MT700", st.session_state["mt700"], height=650)
    st.json(st.session_state["validation"])

    with st.expander("Debug extracción", expanded=False):
        st.json(st.session_state["debug"])
        st.json(st.session_state["visual_map"])
        st.json(st.session_state["verified_map"])
        st.text_area("Texto fuente", st.session_state["source_text"][:12000], height=300)

    st.download_button(
        "Descargar MT700 TXT",
        st.session_state["mt700"].encode("utf-8"),
        file_name="MT700_ANTI_HALLUCINATION_V70.txt",
        mime="text/plain"
    )
