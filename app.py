import streamlit as st
from groq import Groq
from io import BytesIO
import json
import re
import subprocess
import tempfile
import shutil
from typing import Dict, List, Tuple
from datetime import datetime

try:
    import fitz
except Exception:
    fitz = None

try:
    import docx
except Exception:
    docx = None

try:
    from PIL import Image
except Exception:
    Image = None

try:
    import pytesseract
except Exception:
    pytesseract = None

st.set_page_config(
    page_title="MT700 Generator Anti-Hallucination v6.3",
    layout="wide",
    page_icon="🏦"
)

SANTANDER_RED = "#EC0000"
SANTANDER_DARK_RED = "#C00000"
SANTANDER_BORDER = "#F3C7C7"

st.markdown(f"""
<style>
:root {{
    --santander-red: {SANTANDER_RED};
    --santander-dark-red: {SANTANDER_DARK_RED};
    --santander-border: {SANTANDER_BORDER};
}}
.block-container {{ padding-top: 1.5rem; padding-bottom: 2rem; }}
.main {{ background: linear-gradient(180deg, #fff 0%, #fff7f7 100%); }}
[data-testid="stMetric"] {{
    background: white;
    border: 1px solid var(--santander-border);
    border-radius: 14px;
    padding: 14px 18px;
    box-shadow: 0 4px 18px rgba(236, 0, 0, 0.06);
}}
.stButton > button, .stDownloadButton > button {{
    background: var(--santander-red);
    color: white;
    border: none;
    border-radius: 10px;
    padding: 0.6rem 1rem;
    font-weight: 600;
}}
.stButton > button:hover, .stDownloadButton > button:hover {{
    background: var(--santander-dark-red);
    color: white;
}}
div[data-testid="stExpander"] {{
    border: 1px solid #f0d6d6;
    border-radius: 12px;
    background: #fffdfd;
    box-shadow: 0 2px 10px rgba(236, 0, 0, 0.04);
}}
div[data-testid="stExpander"] details summary {{
    font-weight: 600;
    color: #5c1111;
}}
textarea, .stTextArea textarea {{
    border-radius: 10px !important;
}}
.mt700-hero {{
    background: linear-gradient(135deg, {SANTANDER_RED} 0%, #ff3b30 100%);
    color: white;
    border-radius: 18px;
    padding: 22px 24px;
    margin-bottom: 1rem;
    box-shadow: 0 12px 30px rgba(236, 0, 0, 0.18);
}}
.mt700-title {{
    font-size: 1.7rem;
    font-weight: 700;
    margin: 0;
}}
.mt700-subtitle {{
    margin: 0.25rem 0 0 0;
    opacity: 0.92;
    font-size: 0.98rem;
}}
.small-note {{
    font-size: 0.9rem;
    color: #6f1b1b;
}}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="mt700-hero">
  <p class="mt700-title">MT700 Generator</p>
  <p class="mt700-subtitle">Anti-hallucination extraction with party recovery and MT700 fallback rules</p>
</div>
""", unsafe_allow_html=True)

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

EXAMPLE_LIKE_VALUES = {
    "field_27": {"1/1"},
    "field_40A": VALID_40A_CODES,
    "field_40E": VALID_40E_CODES,
    "field_39A": {"10/10"},
    "field_43P": {"ALLOWED", "NOT ALLOWED"},
    "field_43T": {"ALLOWED", "NOT ALLOWED"},
    "field_48": {"21", "21/AFTER SHIPMENT DATE"},
    "field_49": VALID_49_CODES
}

BANK_HINT_WORDS = {
    "BANK", "BRANCH", "SWIFT", "BIC", "ACCOUNT", "ACCNO", "A/C", "CONSTRUCTION BANK"
}

SPANISH_TO_ENGLISH_REPLACEMENTS = {
    "SEGUN": "AS PER",
    "SEGÚN": "AS PER",
    "MERCANCIA": "GOODS",
    "MERCANCÍA": "GOODS",
    "FACTURA COMERCIAL": "COMMERCIAL INVOICE",
    "FACTURA": "INVOICE",
    "POLIZA": "POLICY",
    "PÓLIZA": "POLICY",
    "CERTIFICADO DE ORIGEN": "CERTIFICATE OF ORIGIN",
    "CERTIFICADO": "CERTIFICATE",
    "CONOCIMIENTO DE EMBARQUE": "BILL OF LADING",
    "CARTA DE PORTE": "WAYBILL",
    "BENEFICIARIO": "BENEFICIARY",
    "SOLICITANTE": "APPLICANT",
    "VENCIMIENTO": "EXPIRY",
    "EJEMPLARES": "COPIES",
    "HOJA ADJUNTA": "ATTACHED SHEET",
    "CARGADOR": "SHIPPER",
    "CONSIGNATARIO": "CONSIGNEE",
    "POR CORREO": "BY COURIER",
    "ENVIAR DOCUMENTOS": "SEND DOCUMENTS",
    "GASTOS BANCARIOS": "BANKING CHARGES",
    "FUERA DE ESPAÑA": "OUTSIDE SPAIN",
    "A CARGO DEL BENEFICIARIO": "FOR BENEFICIARY'S ACCOUNT",
    "EMITIDO POR": "ISSUED BY",
    "A FAVOR DE": "IN FAVOUR OF",
    "SI HUBIERA": "IF ANY",
    "SIN AÑADIR SU CONFIRMACIÓN": "WITHOUT CONFIRMATION",
    "SIN AADIR SU CONFIRMACIN": "WITHOUT CONFIRMATION",
    "SIN AÑADIR SU CONFIRMACION": "WITHOUT CONFIRMATION",
}

SWIFT_MT700_CONTEXT = """
You are extracting data for SWIFT MT700 Issue of a Documentary Credit.

Authoritative MT700 structural context:
- Field 50 Applicant format is Name and Address.
- Field 59 Beneficiary format is Name and Address.
- Field 57A is Advise Through Bank.
- Field 41A is Available With... By...
- Field 50 is not a bank field.
- Field 59 is not the advising bank or available-with bank.
- Field 20 format: 16x and must not start or end with '/' and must not contain '//'.
- Field 31C format: YYMMDD.
- Field 31D format: YYMMDD plus expiry place.
- Field 32B format: currency code plus amount.
- Field 40A valid code values are restricted.
- Field 40E valid rules code values are restricted.
- Field 48 is period for presentation in days.
- The absence of field 48 means the presentation period is 21 days, where applicable.
- Field 49 contains confirmation instructions and only valid codes are CONFIRM, MAY ADD, WITHOUT.
- If field 31C is absent in MT700, the date of issue is the date on which the MT700 was sent.

Anti-hallucination policy:
- Extract only if supported by source text.
- If unsupported, return null evidence and found=false.
- Do not use example values unless literally supported.
- Do not fill mandatory fields because they are mandatory.
"""

SYSTEM_EXTRACTION_PROMPT = SWIFT_MT700_CONTEXT + """
Task:
Extract MT700 field candidates from source documents.

Return ONLY one JSON object.
For every requested key, return an object with exactly:
- value: string or null
- evidence: string or null
- found: boolean
- confidence: integer from 0 to 100

Keys:
field_27, field_20, field_40A, field_40E, field_31C, field_31D,
field_50, field_59, field_32B, field_39A, field_41A, field_42C,
field_43P, field_43T, field_44E, field_44F, field_44C,
field_45A, field_46A, field_47A, field_48, field_49,
field_57A, field_71D, field_78, field_72Z

Strict rules:
- Evidence must be a literal short quote from source text.
- For field_50 and field_59, prefer full name+address block if available.
- For field_59, never return an advising bank or available-with bank unless source clearly identifies the bank itself as beneficiary.
- For field_57A and field_41A, prefer bank/BIC content.
- For 40A and 40E, output only valid SWIFT codes supported by evidence.
- For 49, output only CONFIRM, MAY ADD, or WITHOUT if supported.
- Never create values from examples or defaults.
"""

SYSTEM_NARRATIVE_REWRITE_PROMPT = """
You are a Trade Finance banking editor.

You will receive supported narrative MT700 fields with literal evidence already validated.
Rewrite ONLY the value into concise professional MT700 English.

Return ONLY one JSON object with the same keys.
Do not add facts.
Do not add lines not supported by the evidence.
Preserve amounts, dates, percentages, names, places, bank names, and references.
Use uppercase.
If current value is already acceptable, return it unchanged.
"""

EXPECTED_GUIDE = """
MT700 target guide:
- Use uppercase.
- Use only these tags: 27,20,40A,40E,31C,31D,50,59,32B,39A,41A,42C,43P,43T,44E,44F,44C,45A,46A,47A,48,49,57A,71D,78,72Z
- Do not create 41B/41C/41D.
- Do not use example values unless supported by source evidence.
"""

ORIGIN_EXTRACTED = "EXTRACTED"
ORIGIN_INFERRED = "INFERRED_FROM_CONTEXT"
ORIGIN_SYSTEM_DEFAULT = "SYSTEM_DEFAULT"
ORIGIN_OPERATIONAL_DEFAULT = "OPERATIONAL_DEFAULT"

def tesseract_available() -> bool:
    return shutil.which("tesseract") is not None and pytesseract is not None and Image is not None

def safe_json_load(text: str) -> Dict:
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
    return {}

def safe_str(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value).strip()
    return str(value).strip()

def to_upper(text: str) -> str:
    return safe_str(text).upper()

def clean_text(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = "".join(c for c in text if c.isprintable() or c in "\n\t")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text[:50000].strip()

def clean_value(text: str) -> str:
    result = to_upper(text)
    for es, en in sorted(SPANISH_TO_ENGLISH_REPLACEMENTS.items(), key=lambda x: len(x[0]), reverse=True):
        result = re.sub(rf"\b{re.escape(es)}\b", en, result)
    result = re.sub(r"[ ]{2,}", " ", result)
    result = re.sub(r" *\n *", "\n", result)
    return result.strip()

def extract_doc_legacy(data: bytes) -> str:
    try:
        with tempfile.NamedTemporaryFile(delete=True, suffix=".doc") as tmp:
            tmp.write(data)
            tmp.flush()
            result = subprocess.run(["antiword", tmp.name], capture_output=True, text=True, timeout=20)
            if result.returncode == 0:
                return result.stdout
    except Exception:
        pass
    return ""

def extract_pdf_ocr_all_pages(data: bytes, max_pages: int = 4) -> str:
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

def call_llm_json(system_prompt: str, user_text: str, max_tokens: int = 2200) -> Dict:
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

def parse_extraction_object(data: Dict) -> Dict:
    out = {}
    for key in FIELD_KEYS:
        raw = data.get(key, {}) if isinstance(data, dict) else {}
        if not isinstance(raw, dict):
            raw = {}
        value = raw.get("value", None)
        evidence = raw.get("evidence", None)
        found = bool(raw.get("found", False))
        confidence = raw.get("confidence", 0)
        try:
            confidence = int(confidence)
        except Exception:
            confidence = 0

        out[key] = {
            "value": clean_value(value) if value is not None else None,
            "evidence": clean_text(safe_str(evidence)) if evidence is not None else None,
            "found": found,
            "confidence": max(0, min(confidence, 100)),
            "origin": ORIGIN_EXTRACTED
        }
    return out

def normalized_for_match(s: str) -> str:
    s = to_upper(s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()

def normalize_party_block(text: str) -> str:
    t = clean_value(text)
    t = re.sub(r"\s*,\s*", ", ", t)
    t = re.sub(r"\s{2,}", " ", t)
    return t.strip(" .:-")

def extract_party_from_evidence(evidence: str) -> str:
    if not evidence:
        return ""
    e = normalize_party_block(evidence)
    e = re.sub(r"^(BENEFICIARY|APPLICANT|ORDENANTE|SOLICITANTE|FIELD 50|FIELD 59|50|59)\s*", "", e).strip(" .:-")
    return e

def evidence_supports_party_value(value: str, evidence: str) -> bool:
    v = normalize_party_block(value)
    e = normalize_party_block(evidence)

    if not v or not e:
        return False

    v_tokens = [t for t in re.split(r"[^A-Z0-9]+", v) if len(t) >= 3]
    e_tokens = set(t for t in re.split(r"[^A-Z0-9]+", e) if len(t) >= 3)

    if not v_tokens:
        return False

    overlap = sum(1 for t in v_tokens if t in e_tokens)
    has_address_hint = any(x in e for x in [
        "ROAD", "STREET", "BUILDING", "NO", "PORT", "SPAIN", "CHINA", "GUANGZHOU",
        "GIRONA", "MADRID", "ORDIS", "PANYU", "SOUTH", "CENTRAL", "CANTABRIA"
    ])

    return overlap >= max(2, len(v_tokens) // 2) or (overlap >= 2 and has_address_hint)

def looks_like_bank_text(value: str) -> bool:
    v = normalized_for_match(value)
    return any(word in v for word in BANK_HINT_WORDS)

def evidence_supports_value(value: str, evidence: str, field_key: str) -> bool:
    if not value or not evidence:
        return False

    if field_key in PARTY_FIELDS:
        return evidence_supports_party_value(value, evidence)

    v = normalized_for_match(value)
    e = normalized_for_match(evidence)

    if field_key in NARRATIVE_FIELDS:
        tokens = [t for t in re.split(r"[^A-Z0-9]+", v) if len(t) >= 4]
        if not tokens:
            return False
        overlap = sum(1 for t in tokens if t in e)
        return overlap >= max(1, min(3, len(tokens) // 3 or 1))

    if field_key == "field_41A":
        core = v.replace(" / BY PAYMENT", "").replace("/ BY PAYMENT", "").strip()
        return core in e or any(x in e for x in re.split(r"[^A-Z0-9]+", core) if len(x) >= 6)

    if field_key == "field_31D":
        m = re.match(r"^(\d{6})(.*)$", v)
        if m:
            d, place = m.groups()
            return d in e and (place.strip()[:4] in e if place.strip() else True)

    plain = re.sub(r"\s+", "", v)
    plain_e = re.sub(r"\s+", "", e)
    if plain and plain in plain_e:
        return True

    tokens = [t for t in re.split(r"[^A-Z0-9]+", v) if len(t) >= 3]
    if not tokens:
        return False
    overlap = sum(1 for t in tokens if t in e)
    return overlap >= max(1, len(tokens) - 1)

def looks_like_example_leak(field_key: str, value: str, evidence: str) -> bool:
    if not value:
        return False
    v = normalized_for_match(value)
    example_set = EXAMPLE_LIKE_VALUES.get(field_key, set())
    if v not in example_set:
        return False
    e = normalized_for_match(evidence or "")
    return v not in e

def valid_yymmdd(value: str) -> bool:
    if not re.fullmatch(r"\d{6}", value or ""):
        return False
    try:
        datetime.strptime(value, "%y%m%d")
        return True
    except Exception:
        return False

def semantic_field_check(field_key: str, value: str) -> Tuple[bool, str]:
    v = to_upper(value)

    if field_key == "field_20":
        if len(v) > 16:
            return False, "20 exceeds 16 characters"
        if v.startswith("/") or v.endswith("/") or "//" in v:
            return False, "20 cannot start/end with slash or contain double slash"
    elif field_key == "field_31C":
        if not valid_yymmdd(v):
            return False, "31C must be valid YYMMDD"
    elif field_key == "field_31D":
        m = re.match(r"^(\d{6})(.+)$", v)
        if not m:
            return False, "31D must be YYMMDD plus place"
        if not valid_yymmdd(m.group(1)):
            return False, "31D date invalid"
    elif field_key == "field_32B":
        if not re.fullmatch(r"[A-Z]{3}[0-9][0-9,\.]*", v.replace(" ", "")):
            return False, "32B must be currency+amount"
    elif field_key == "field_39A":
        if not re.fullmatch(r"\d{1,2}/\d{1,2}", v):
            return False, "39A must be tolerance format"
    elif field_key == "field_40A":
        if v not in VALID_40A_CODES:
            return False, "40A invalid code"
    elif field_key == "field_40E":
        if v not in VALID_40E_CODES and not v.startswith("OTHR"):
            return False, "40E invalid code"
    elif field_key == "field_43P":
        if v not in {"ALLOWED", "NOT ALLOWED"}:
            return False, "43P invalid"
    elif field_key == "field_43T":
        if v not in {"ALLOWED", "NOT ALLOWED"}:
            return False, "43T invalid"
    elif field_key == "field_48":
        if "%" in v:
            return False, "48 cannot contain percentage"
        if not re.fullmatch(r"\d{1,3}(/.+)?", v):
            return False, "48 invalid format"
    elif field_key == "field_49":
        if v not in VALID_49_CODES:
            return False, "49 invalid code"
    elif field_key == "field_71D":
        if re.fullmatch(r"[0-9,\.]+", v):
            return False, "71D cannot be numeric only"
    elif field_key == "field_50":
        if looks_like_bank_text(v):
            return False, "50 should be applicant, not bank field"
    elif field_key == "field_59":
        if looks_like_bank_text(v):
            return False, "59 should be beneficiary, not bank field"

    return True, ""

def enrich_party_value_from_evidence(field_key: str, value: str, evidence: str) -> str:
    if field_key not in PARTY_FIELDS:
        return value
    rebuilt = extract_party_from_evidence(evidence)
    if rebuilt:
        return rebuilt
    return value

def infer_mt700_defaults(source_text: str, verified_map: Dict) -> Dict[str, Dict]:
    t = to_upper(source_text)
    inferred = {}

    has_lc_context = any(x in t for x in [
        "LETTER OF CREDIT", "DOCUMENTARY CREDIT", "CREDITO DOCUMENTARIO", "CRÉDITO DOCUMENTARIO", "MT700"
    ])

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

    if not verified_map["field_31C"]["accepted"]:
        inferred["field_31C"] = {
            "value": datetime.now().strftime("%y%m%d"),
            "reason": "System fallback issue date when absent",
            "origin": ORIGIN_SYSTEM_DEFAULT
        }

    return inferred

def apply_inferred_defaults(verified_map: Dict, inferred: Dict) -> Tuple[Dict, List[str]]:
    audit = []
    for key, meta in inferred.items():
        current = verified_map.get(key, {})
        if current.get("accepted"):
            continue

        value = meta["value"]
        ok, msg = semantic_field_check(key, value)
        if not ok:
            audit.append(f"{key}: inferred/default value rejected: {msg}")
            continue

        verified_map[key] = {
            "value": value,
            "evidence": "",
            "found": True,
            "confidence": 100 if meta["origin"] == ORIGIN_SYSTEM_DEFAULT else 85,
            "accepted": True,
            "reason": meta["reason"],
            "origin": meta["origin"]
        }
        audit.append(f"{key}: accepted by {meta['origin']} -> {value}")
    return verified_map, audit

def verify_extraction(extracted: Dict, source_text: str) -> Tuple[Dict, List[str]]:
    verified = {}
    audit = []

    for key in FIELD_KEYS:
        item = extracted.get(key, {"value": None, "evidence": None, "found": False, "confidence": 0, "origin": ORIGIN_EXTRACTED})
        value = item.get("value")
        evidence = item.get("evidence")
        found = bool(item.get("found"))
        confidence = int(item.get("confidence", 0) or 0)
        origin = item.get("origin", ORIGIN_EXTRACTED)

        accepted = False
        reason = ""

        if found and value and evidence:
            candidate_value = enrich_party_value_from_evidence(key, value, evidence)

            if looks_like_example_leak(key, candidate_value, evidence):
                reason = "Rejected: example-like value not present in evidence"
            elif not evidence_supports_value(candidate_value, evidence, key):
                reason = "Rejected: evidence does not support extracted value"
            else:
                ok, msg = semantic_field_check(key, candidate_value)
                if not ok:
                    reason = f"Rejected: {msg}"
                elif confidence < 55 and key not in NARRATIVE_FIELDS and key not in PARTY_FIELDS:
                    reason = "Rejected: confidence below threshold"
                else:
                    accepted = True
                    value = candidate_value
        else:
            reason = "Rejected: missing found/value/evidence"

        if key == "field_27" and not accepted:
            verified[key] = {
                "value": "1/1",
                "evidence": "",
                "found": True,
                "confidence": 100,
                "accepted": True,
                "reason": "Accepted by operational default",
                "origin": ORIGIN_OPERATIONAL_DEFAULT
            }
            audit.append(f"{key}: accepted by operational default 1/1")
            continue

        verified[key] = {
            "value": value if accepted else "",
            "evidence": evidence if accepted else "",
            "found": accepted,
            "confidence": confidence if accepted else 0,
            "accepted": accepted,
            "reason": "Accepted" if accepted else reason,
            "origin": origin if accepted else ""
        }
        audit.append(f"{key}: {'ACCEPTED' if accepted else reason}")

    inferred = infer_mt700_defaults(source_text, verified)
    verified, infer_audit = apply_inferred_defaults(verified, inferred)
    audit.extend(infer_audit)

    return verified, audit

def rewrite_supported_narratives(verified_map: Dict) -> Dict:
    payload = {}
    for key in NARRATIVE_FIELDS:
        item = verified_map.get(key, {})
        if item.get("accepted") and item.get("value") and item.get("evidence"):
            payload[key] = {
                "value": item["value"],
                "evidence": item["evidence"]
            }

    if not payload:
        return {}

    user_text = json.dumps(payload, ensure_ascii=False, indent=2)
    rewritten = call_llm_json(SYSTEM_NARRATIVE_REWRITE_PROMPT, user_text, max_tokens=1200)

    out = {}
    for key, original in payload.items():
        candidate = rewritten.get(key)
        if isinstance(candidate, str) and candidate.strip():
            new_val = clean_value(candidate)
            if evidence_supports_value(new_val, original["evidence"], key):
                out[key] = new_val
            else:
                out[key] = original["value"]
        else:
            out[key] = original["value"]
    return out

def build_mt700_from_verified_map(verified_map: Dict) -> str:
    lines = ["{1:F01BSCHESMMXXXX0123000001}{2:I700BSCHHKHHXXXXN2020}{4:"]
    for field_key in FIELD_KEYS:
        item = verified_map.get(field_key, {})
        if item.get("accepted") and item.get("value"):
            tag = FIELD_TO_TAG[field_key]
            lines.append(f":{tag}:{clean_value(item['value'])}")
    lines.append("-}")
    return "\n".join(lines).upper()

def parse_mt700_fields(mt700: str) -> Dict[str, str]:
    pattern = re.compile(r"(?ms)^:([0-9]{2}[A-Z]?):(.*?)(?=^:[0-9]{2}[A-Z]?:|^-}\s*$|\Z)")
    return {tag: value.strip() for tag, value in pattern.findall(mt700 or "")}

def validate_mt700(mt700: str, verified_map: Dict) -> Dict:
    fields = parse_mt700_fields(mt700)
    issues = []
    warnings = []

    for tag in fields:
        if tag not in ALLOWED_TAGS:
            issues.append(f"Forbidden tag detected :{tag}:")

    for key in FIELD_KEYS:
        tag = FIELD_TO_TAG[key]
        accepted = verified_map.get(key, {}).get("accepted", False)
        if accepted and tag not in fields:
            issues.append(f"Accepted field missing in final MT700 :{tag}:")
        if not accepted and tag in fields and key != "field_27":
            issues.append(f"Unverified field leaked into final MT700 :{tag}:")

    for mandatory_tag in MANDATORY_IN_SCOPE:
        key = TAG_TO_FIELD[mandatory_tag]
        if not verified_map.get(key, {}).get("accepted", False):
            warnings.append(f"Mandatory MT700 field not supported by source/default logic and therefore omitted :{mandatory_tag}:")

    if "42C" in fields:
        warnings.append("42C present: in full SWIFT logic related 42a should also exist")

    if verified_map.get("field_48", {}).get("origin") == ORIGIN_SYSTEM_DEFAULT:
        warnings.append("48 inserted by default rule: absence implies 21 days where applicable")

    if verified_map.get("field_31C", {}).get("origin") == ORIGIN_SYSTEM_DEFAULT:
        warnings.append("31C inserted by system fallback issue date")

    score = max(0, 100 - len(issues) * 10 - len(warnings) * 3)
    return {
        "is_valid": len(issues) == 0,
        "score": score,
        "issues": issues,
        "warnings": warnings
    }

def extraction_table_rows(verified_map: Dict) -> List[Dict]:
    rows = []
    for key in FIELD_KEYS:
        item = verified_map.get(key, {})
        rows.append({
            "field": key,
            "tag": FIELD_TO_TAG[key],
            "accepted": item.get("accepted", False),
            "origin": item.get("origin", ""),
            "confidence": item.get("confidence", 0),
            "value": item.get("value", ""),
            "evidence": item.get("evidence", ""),
            "reason": item.get("reason", "")
        })
    return rows

if not tesseract_available():
    st.info("OCR no disponible en este entorno. Instala tesseract-ocr y tesseract-ocr-spa para PDF escaneados.")

st.markdown(
    '<p class="small-note">Esta versión añade fallbacks auditados para 40A, 40E, 49, 48 y 31C, y mantiene la recuperación mejorada de 50/59.</p>',
    unsafe_allow_html=True
)

if st.button("🚀 Generar MT700"):
    if not files:
        st.warning("Sube documentos")
    else:
        try:
            with st.spinner("Extrayendo texto de documentos..."):
                full_parts = []
                debug = []

                for f in files:
                    name = f.name.lower()
                    data = f.getvalue()
                    txt = ""

                    if name.endswith(".pdf"):
                        txt = extract_pdf_ocr_all_pages(data, max_pages=4)
                        mode = "ocr-pdf"
                    elif name.endswith(".docx"):
                        try:
                            d = docx.Document(BytesIO(data))
                            txt = "\n".join(p.text for p in d.paragraphs)
                            mode = "docx"
                        except Exception:
                            txt = ""
                            mode = "docx-error"
                    elif name.endswith(".doc"):
                        txt = extract_doc_legacy(data)
                        mode = "doc"
                    else:
                        try:
                            txt = data.decode("utf-8", errors="ignore")
                            mode = "text"
                        except Exception:
                            txt = ""
                            mode = "unknown"

                    txt = clean_text(txt)
                    full_parts.append(f"### {f.name}\n{txt}")
                    debug.append({
                        "file": f.name,
                        "mode": mode,
                        "chars": len(txt),
                        "preview": txt[:800]
                    })

                source_text = "\n\n".join(full_parts)

            with st.expander("🧪 Debug extracción", expanded=False):
                st.json(debug)
                st.text_area("Texto fuente", source_text[:7000], height=300)

            with st.spinner("Extrayendo candidatos con evidencia usando contexto SWIFT..."):
                extraction_prompt = EXPECTED_GUIDE + "\n\nSOURCE DOCUMENTS:\n" + source_text[:22000]
                raw_extraction = call_llm_json(SYSTEM_EXTRACTION_PROMPT, extraction_prompt, max_tokens=2400)
                extracted = parse_extraction_object(raw_extraction)

            with st.expander("🧩 Extracción cruda con evidencia", expanded=False):
                st.json(extracted)

            verified_map, audit = verify_extraction(extracted, source_text)

            with st.expander("🛡️ Auditoría anti-alucinación", expanded=False):
                st.json(extraction_table_rows(verified_map))
                st.text("\n".join(audit))

            with st.spinner("Reescribiendo solo narrativas soportadas..."):
                narrative_updates = rewrite_supported_narratives(verified_map)
                for key, new_val in narrative_updates.items():
                    verified_map[key]["value"] = new_val

            mt700 = build_mt700_from_verified_map(verified_map)
            validation = validate_mt700(mt700, verified_map)

            st.session_state["source_text"] = source_text
            st.session_state["raw_extraction"] = extracted
            st.session_state["verified_map"] = verified_map
            st.session_state["audit"] = audit
            st.session_state["mt700"] = mt700
            st.session_state["validation"] = validation

            st.success("✅ Generado con control anti-alucinación, recovery de parties y fallback rules auditadas")

        except Exception as e:
            st.error(f"Error durante la ejecución: {e}")

if "mt700" in st.session_state:
    with st.expander("🧪 Debug persistido", expanded=False):
        st.json(st.session_state.get("raw_extraction", {}))
        st.json(st.session_state.get("verified_map", {}))
        st.text_area("Texto fuente persistido", st.session_state.get("source_text", "")[:7000], height=260)

    col1, col2 = st.columns([2, 1])

    with col1:
        st.text_area("📡 MT700", st.session_state["mt700"], height=650)

    with col2:
        st.metric("Confianza", f"{st.session_state['validation']['score']}%")
        st.json(st.session_state["validation"])

    with st.expander("🧾 Evidencia por campo", expanded=False):
        st.json(extraction_table_rows(st.session_state["verified_map"]))

    txt_data = st.session_state["mt700"].encode("utf-8")
    json_data = json.dumps({
        "raw_extraction": st.session_state["raw_extraction"],
        "verified_map": st.session_state["verified_map"],
        "audit": st.session_state["audit"],
        "validation": st.session_state["validation"]
    }, ensure_ascii=False, indent=2).encode("utf-8")

    c1, c2 = st.columns(2)
    with c1:
        st.download_button("⬇️ Descargar MT700 TXT", txt_data, file_name="MT700_ANTI_HALLUCINATION_V63.txt", mime="text/plain")
    with c2:
        st.download_button("⬇️ Descargar auditoría JSON", json_data, file_name="MT700_AUDIT_V63.json", mime="application/json")
