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
    page_title="MT700 Generator Anti-Hallucination v6.9",
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
  <p class="mt700-subtitle">OCR MT700 + narrativa + auditoría explicativa + interpretación reforzada de checkboxes</p>
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

FIELD_METADATA = {
    "field_27": {"name": "Sequence of Total", "description": "Número de mensaje dentro de la serie total del crédito, por ejemplo 1/1."},
    "field_20": {"name": "Documentary Credit Number", "description": "Referencia única del crédito documentario asignada por el emisor."},
    "field_40A": {"name": "Form of Documentary Credit", "description": "Indica la forma del crédito, por ejemplo si es irrevocable."},
    "field_40E": {"name": "Applicable Rules", "description": "Reglas aplicables al crédito, por ejemplo UCP o eUCP."},
    "field_31C": {"name": "Date of Issue", "description": "Fecha en la que el crédito es emitido por el banco emisor."},
    "field_31D": {"name": "Date and Place of Expiry", "description": "Fecha y lugar donde expira el crédito documentario."},
    "field_50": {"name": "Applicant", "description": "Ordenante o solicitante del crédito, normalmente nombre y dirección."},
    "field_59": {"name": "Beneficiary", "description": "Beneficiario del crédito, normalmente nombre y dirección."},
    "field_32B": {"name": "Currency Code, Amount", "description": "Divisa e importe del crédito."},
    "field_39A": {"name": "Percentage Credit Amount Tolerance", "description": "Tolerancia permitida sobre el importe del crédito, por ejemplo 10/10."},
    "field_41A": {"name": "Available With... By...", "description": "Banco con el que está disponible el crédito y forma de utilización, por ejemplo BY PAYMENT."},
    "field_42C": {"name": "Drafts at", "description": "Condición o tenor de la letra, si aplica."},
    "field_43P": {"name": "Partial Shipments", "description": "Indica si se permiten expediciones parciales."},
    "field_43T": {"name": "Transhipment", "description": "Indica si se permite transbordo."},
    "field_44E": {"name": "Port of Loading / Airport of Departure", "description": "Puerto de carga o aeropuerto de salida."},
    "field_44F": {"name": "Port of Discharge / Airport of Destination", "description": "Puerto de descarga o aeropuerto de destino."},
    "field_44C": {"name": "Latest Date of Shipment", "description": "Última fecha permitida de embarque."},
    "field_45A": {"name": "Description of Goods and/or Services", "description": "Descripción de la mercancía o servicios cubiertos por el crédito."},
    "field_46A": {"name": "Documents Required", "description": "Documentos que deben presentarse bajo el crédito."},
    "field_47A": {"name": "Additional Conditions", "description": "Condiciones adicionales aplicables al crédito."},
    "field_48": {"name": "Period for Presentation", "description": "Número de días dentro de los cuales deben presentarse los documentos."},
    "field_49": {"name": "Confirmation Instructions", "description": "Instrucciones de confirmación para el banco receptor."},
    "field_57A": {"name": "Advise Through Bank / Second Advising Bank", "description": "Banco a través del cual se avisa el crédito o segundo banco avisador."},
    "field_71D": {"name": "Charges", "description": "Quién asume los gastos y comisiones bancarias."},
    "field_78": {"name": "Instructions to the Paying/Accepting/Negotiating Bank", "description": "Instrucciones al banco pagador, aceptante o negociador."},
    "field_72Z": {"name": "Sender to Receiver Information", "description": "Información adicional del emisor al receptor."}
}

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

VALID_41A_CODES = {
    "BY ACCEPTANCE",
    "BY DEF PAYMENT",
    "BY MIXED PYMT",
    "BY NEGOTIATION",
    "BY PAYMENT"
}

VALID_43_CODES = {"ALLOWED", "CONDITIONAL", "NOT ALLOWED"}

EXAMPLE_LIKE_VALUES = {
    "field_27": {"1/1"},
    "field_40A": VALID_40A_CODES,
    "field_40E": VALID_40E_CODES,
    "field_39A": {"10/10", "5/5"},
    "field_43P": VALID_43_CODES,
    "field_43T": VALID_43_CODES,
    "field_48": {"21", "21/AFTER SHIPMENT DATE"},
    "field_49": VALID_49_CODES
}

BANK_HINT_WORDS = {
    "BANK", "BRANCH", "SWIFT", "BIC", "ACCOUNT", "ACCNO", "A/C", "CONSTRUCTION BANK", "SANTANDER"
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
    "A CARGO DEL ORDENANTE": "FOR APPLICANT'S ACCOUNT",
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
- Field 59 is not a bank field unless explicitly the beneficiary.
- Field 20 format: 16x and must not start or end with '/' and must not contain '//'.
- Field 31C format: YYMMDD.
- Field 31D format: YYMMDD plus expiry place.
- Field 32B format: currency code plus amount.
- Field 39A format: tolerance xx/yy.
- Field 40A valid code values are restricted.
- Field 40E valid rules code values are restricted.
- Field 41A includes a BIC or bank identifier plus one valid BY code.
- Field 43P valid codes are ALLOWED, CONDITIONAL, NOT ALLOWED.
- Field 43T valid codes are ALLOWED, CONDITIONAL, NOT ALLOWED.
- Field 48 is period for presentation in days.
- Field 46A is narrative documents required.
- Field 71D is narrative charges clause.
- The absence of field 48 means the presentation period is 21 days, where applicable.
- Field 49 contains confirmation instructions and only valid codes are CONFIRM, MAY ADD, WITHOUT.

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
- For 43P and 43T, output only ALLOWED, CONDITIONAL, or NOT ALLOWED if supported.
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
ORIGIN_DIRECT_OCR_MT700 = "DIRECT_OCR_MT700"
ORIGIN_CHECKBOX_INFERRED = "CHECKBOX_INFERRED"


def tesseract_available():
    return shutil.which("tesseract") is not None and pytesseract is not None and Image is not None


def safe_json_load(text):
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


def safe_str(value):
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def to_upper(text):
    return safe_str(text).upper()


def clean_text(text):
    text = safe_str(text).replace("\xa0", " ")
    text = "".join(c for c in text if c.isprintable() or c in "\n\t")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text[:100000].strip()


def clean_value(text):
    result = to_upper(text)
    for es, en in sorted(SPANISH_TO_ENGLISH_REPLACEMENTS.items(), key=lambda x: len(x[0]), reverse=True):
        result = re.sub(rf"\b{re.escape(es)}\b", en, result)
    result = re.sub(r"[ ]{2,}", " ", result)
    result = re.sub(r" *\n *", "\n", result)
    return result.strip()


def normalize_ocr_separators(text):
    t = to_upper(text)
    t = t.replace("☒", " X ").replace("☑", " X ").replace("[X]", " X ").replace("(X)", " X ")
    t = re.sub(r"[|]+", " ", t)
    t = re.sub(r"[/]{2,}", " ", t)
    t = re.sub(r"\s*:\s*", " : ", t)
    t = re.sub(r"\s*-\s*", " - ", t)
    t = re.sub(r"\s{2,}", " ", t)
    return t.strip()


def normalize_checkbox_line(text):
    return normalize_ocr_separators(text)


def collect_lines(text):
    return [normalize_checkbox_line(ln) for ln in text.splitlines() if ln.strip()]


def line_has_marker_near_label(line, label, max_distance=18):
    l = normalize_checkbox_line(line)
    if label not in l:
        return False
    label_pos = l.find(label)
    x_positions = [m.start() for m in re.finditer(r"\bX\b", l)]
    if not x_positions:
        return False
    return any(abs(x - label_pos) <= max_distance for x in x_positions)


def nearest_marked_option(line, labels):
    l = normalize_checkbox_line(line)
    x_positions = [m.start() for m in re.finditer(r"\bX\b", l)]
    if not x_positions:
        return ""

    best_label = ""
    best_dist = 10**9

    for label in labels:
        start = 0
        while True:
            idx = l.find(label, start)
            if idx == -1:
                break
            dist = min(abs(idx - x) for x in x_positions)
            if dist < best_dist:
                best_dist = dist
                best_label = label
            start = idx + len(label)

    return best_label if best_dist <= 24 else ""


def normalize_checkbox_text(text):
    t = to_upper(text)
    t = t.replace("☒", " X ").replace("☑", " X ").replace("[X]", " X ").replace("(X)", " X ")
    t = re.sub(r"[|]+", " ", t)
    t = re.sub(r"\s*:\s*", " : ", t)
    t = re.sub(r"\s*-\s*", " - ", t)
    t = re.sub(r"\s{2,}", " ", t)
    return t.strip()


def extract_context_window(text, anchor_pattern, window=220):
    t = normalize_checkbox_text(text)
    m = re.search(anchor_pattern, t, re.I)
    if not m:
        return ""
    start = max(0, m.start() - 30)
    end = min(len(t), m.end() + window)
    return t[start:end]


def nearest_marked_option_in_window(window_text, labels, max_distance=42):
    w = normalize_checkbox_text(window_text)
    x_positions = [m.start() for m in re.finditer(r"\bX\b", w)]
    if not x_positions:
        return ""

    best_label = ""
    best_dist = 10**9

    for label in labels:
        label_u = to_upper(label)
        start = 0
        while True:
            idx = w.find(label_u, start)
            if idx == -1:
                break
            dist = min(abs(idx - x) for x in x_positions)
            if dist < best_dist:
                best_dist = dist
                best_label = label_u
            start = idx + len(label_u)

    return best_label if best_label and best_dist <= max_distance else ""


def extract_doc_legacy(data):
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


def empty_extraction_map():
    out = {}
    for key in FIELD_KEYS:
        out[key] = {
            "value": None,
            "evidence": None,
            "found": False,
            "confidence": 0,
            "origin": ORIGIN_EXTRACTED
        }
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


def normalized_for_match(s):
    s = to_upper(s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def normalize_party_block(text):
    t = clean_value(text)
    t = re.sub(r"\s*,\s*", ", ", t)
    t = re.sub(r"\s{2,}", " ", t)
    return t.strip(" .:-")


def extract_party_from_evidence(evidence):
    if not evidence:
        return ""
    e = normalize_party_block(evidence)
    e = re.sub(r"^(BENEFICIARY|APPLICANT|ORDENANTE|SOLICITANTE|FIELD 50|FIELD 59|50|59)\s*", "", e).strip(" .:-")
    return e


def evidence_supports_party_value(value, evidence):
    v = normalize_party_block(value)
    e = normalize_party_block(evidence)
    if not v or not e:
        return False
    v_tokens = [t for t in re.split(r"[^A-Z0-9]+", v) if len(t) >= 3]
    e_tokens = set(t for t in re.split(r"[^A-Z0-9]+", e) if len(t) >= 3)
    overlap = sum(1 for t in v_tokens if t in e_tokens)
    return overlap >= max(2, len(v_tokens) // 2)


def looks_like_bank_text(value):
    v = normalized_for_match(value)
    return any(word in v for word in BANK_HINT_WORDS)


def evidence_supports_value(value, evidence, field_key):
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

    plain = re.sub(r"\s+", "", v)
    plain_e = re.sub(r"\s+", "", e)
    if plain and plain in plain_e:
        return True

    tokens = [t for t in re.split(r"[^A-Z0-9]+", v) if len(t) >= 3]
    overlap = sum(1 for t in tokens if t in e)
    return overlap >= max(1, len(tokens) - 1)


def looks_like_example_leak(field_key, value, evidence):
    if not value:
        return False
    v = normalized_for_match(value)
    example_set = EXAMPLE_LIKE_VALUES.get(field_key, set())
    if v not in example_set:
        return False
    e = normalized_for_match(evidence or "")
    return v not in e


def valid_yymmdd(value):
    if not re.fullmatch(r"\d{6}", value or ""):
        return False
    try:
        datetime.strptime(value, "%y%m%d")
        return True
    except Exception:
        return False


def semantic_field_check(field_key, value):
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

    elif field_key == "field_41A":
        if "BY " not in v:
            return False, "41A missing availability code"
        ok_code = any(code in v for code in VALID_41A_CODES)
        if not ok_code:
            return False, "41A invalid availability code"

    elif field_key in {"field_43P", "field_43T"}:
        if v not in VALID_43_CODES:
            return False, f"{FIELD_TO_TAG[field_key]} invalid code"

    elif field_key == "field_48":
        if "%" in v:
            return False, "48 cannot contain percentage"
        if not re.fullmatch(r"\d{1,3}(/.+)?", v):
            return False, "48 invalid format"

    elif field_key == "field_49":
        if v not in VALID_49_CODES:
            return False, "49 invalid code"

    elif field_key == "field_50":
        if looks_like_bank_text(v):
            return False, "50 should be applicant, not bank field"

    elif field_key == "field_59":
        if looks_like_bank_text(v):
            return False, "59 should be beneficiary, not bank field"

    return True, ""


def enrich_party_value_from_evidence(field_key, value, evidence):
    if field_key not in PARTY_FIELDS:
        return value
    rebuilt = extract_party_from_evidence(evidence)
    if rebuilt:
        return rebuilt
    return value


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


def fix_common_ocr_swift_noise(text):
    t = clean_text(text).upper()
    t = t.replace("{1:", "\n{1:")
    t = t.replace("{2:", "\n{2:")
    t = t.replace("{4:", "\n{4:")
    t = re.sub(r"\b4\s*\n\s*27", "\n27", t)
    t = re.sub(r"\b2711\b", "27 1/1", t)
    t = re.sub(r"\b39A1010\b", "39A 10/10", t)
    t = re.sub(r"\b4821AFTER SHIPMENT DATE\b", "48 21/AFTER SHIPMENT DATE", t)
    t = re.sub(r"\b49WITHOUT\b", "49 WITHOUT", t)
    t = re.sub(r"\b43PALLOWED\b", "43P ALLOWED", t)
    t = re.sub(r"\b43TALLOWED\b", "43T ALLOWED", t)
    t = re.sub(r"\b40AIRREVOCABLE\b", "40A IRREVOCABLE", t)
    t = re.sub(r"\b40EUCP LATEST VERSION\b", "40E UCP LATEST VERSION", t)
    t = re.sub(r"\b31C(\d{6})\b", r"31C \1", t)
    t = re.sub(r"\b31D(\d{6}[A-Z].+?)\b", r"31D \1", t)
    t = re.sub(r"\b32B([A-Z]{3}[0-9].+?)\b", r"32B \1", t)
    t = re.sub(r"\b44E([A-Z].+?)\b", r"44E \1", t)
    t = re.sub(r"\b44F([A-Z].+?)\b", r"44F \1", t)
    t = re.sub(r"\b44C(\d{6})\b", r"44C \1", t)
    t = re.sub(r"\b57A([A-Z0-9]{8,11})\b", r"57A \1", t)
    return t


def parse_ocr_mt700_blocks(source_text):
    t = fix_common_ocr_swift_noise(source_text)
    tags = ALLOWED_TAGS[:]
    tag_alt = "|".join(sorted(tags, key=len, reverse=True))
    results = {}

    for tag in tags:
        pattern = rf"(?ms)(?:^|\n)\s*:?\s*{re.escape(tag)}\s+(.+?)(?=(?:\n\s*:?\s*(?:{tag_alt})\s)|\n\s*-\}}|\Z)"
        m = re.search(pattern, t)
        if m:
            value = clean_value(m.group(1).strip(" :\n\t"))
            if value:
                results[tag] = value

    if "41A" in results:
        val = results["41A"]
        val = re.sub(r"\b([A-Z0-9]{8,11})\s+(BY (?:ACCEPTANCE|DEF PAYMENT|MIXED PYMT|NEGOTIATION|PAYMENT))\b", r"\1 \2", val)
        results["41A"] = val

    return results


def merge_direct_ocr_into_extraction(extracted, source_text):
    direct = parse_ocr_mt700_blocks(source_text)
    for tag, value in direct.items():
        key = TAG_TO_FIELD.get(tag)
        if not key:
            continue

        ok, _ = semantic_field_check(key, value)
        if not ok and key not in NARRATIVE_FIELDS and key not in PARTY_FIELDS:
            continue

        extracted[key] = {
            "value": clean_value(value),
            "evidence": clean_text(f"{tag} {value}")[:1200],
            "found": True,
            "confidence": 98,
            "origin": ORIGIN_DIRECT_OCR_MT700
        }
    return extracted, direct


def infer_payment_method_from_checkboxes(source_text):
    windows = [
        extract_context_window(
            source_text,
            r"CR[EÉ]DITO UTILIZABLE EN LAS CAJAS DE.*?PARA",
            window=180
        ),
        extract_context_window(
            source_text,
            r"PARA\s+X\s+PAGO",
            window=120
        ),
        extract_context_window(
            source_text,
            r"PAGO\s+ACEPTACION\s+NEGOCIACION\s+PAGO DIFERIDO",
            window=120
        ),
    ]

    for window in windows:
        if not window:
            continue

        if re.search(r"\bPARA\s+X\s+PAGO\b", normalize_checkbox_text(window)):
            return "BY PAYMENT"

        chosen = nearest_marked_option_in_window(
            window,
            ["PAGO DIFERIDO", "NEGOCIACION", "ACEPTACION", "PAGO"],
            max_distance=26
        )

        if chosen == "PAGO":
            return "BY PAYMENT"
        if chosen == "ACEPTACION":
            return "BY ACCEPTANCE"
        if chosen == "NEGOCIACION":
            return "BY NEGOTIATION"
        if chosen == "PAGO DIFERIDO":
            return "BY DEF PAYMENT"

    return ""


def infer_tolerance_from_checkboxes(source_text):
    windows = [
        extract_context_window(
            source_text,
            r"TOTAL QUANTITY AND AMOUNT IS ACCEPTABLE",
            window=120
        ),
        extract_context_window(
            source_text,
            r"\b10\b.{0,40}TOTAL QUANTITY AND AMOUNT IS ACCEPTABLE",
            window=80
        ),
        extract_context_window(
            source_text,
            r"\b5\b.{0,40}TOTAL QUANTITY AND AMOUNT IS ACCEPTABLE",
            window=80
        ),
    ]

    for window in windows:
        if not window:
            continue

        w = normalize_checkbox_text(window)

        if re.search(r"\bX\s*-\s*10\b.{0,40}\bTOTAL QUANTITY AND AMOUNT IS ACCEPTABLE\b", w):
            return "10/10"
        if re.search(r"\b10\b.{0,12}\bX\b.{0,40}\bTOTAL QUANTITY AND AMOUNT IS ACCEPTABLE\b", w):
            return "10/10"
        if re.search(r"\bX\s*-\s*5\b.{0,40}\bTOTAL QUANTITY AND AMOUNT IS ACCEPTABLE\b", w):
            return "5/5"
        if re.search(r"\b5\b.{0,12}\bX\b.{0,40}\bTOTAL QUANTITY AND AMOUNT IS ACCEPTABLE\b", w):
            return "5/5"

    return ""


def infer_checkbox_selection_for_43p(text):
    t = normalize_checkbox_text(text)

    if re.search(r"\bEXPEDICIONES PARCIALES\s+X\s+AUTORIZADAS\b", t):
        return "ALLOWED"
    if re.search(r"\bEXPEDICIONES PARCIALES\s+X\s+PROHIBIDAS\b", t):
        return "NOT ALLOWED"

    window = extract_context_window(
        text,
        r"EXPEDICIONES PARCIALES",
        window=100
    )
    if not window:
        return ""

    chosen = nearest_marked_option_in_window(
        window,
        ["AUTORIZADAS", "PROHIBIDAS", "CONDICIONALES"],
        max_distance=24
    )

    if chosen == "AUTORIZADAS":
        return "ALLOWED"
    if chosen == "PROHIBIDAS":
        return "NOT ALLOWED"
    if chosen == "CONDICIONALES":
        return "CONDITIONAL"

    return ""


def infer_checkbox_selection_for_43t(text):
    lines = collect_lines(text)
    for line in lines:
        if "TRANSBORDOS" not in line and "TRANSHIPMENT" not in line and "TRANSHIPMENTS" not in line:
            continue

        chosen = nearest_marked_option(line, ["PERMITIDOS", "PROHIBIDOS", "CONDICIONALES"])
        if chosen == "PERMITIDOS":
            return "ALLOWED"
        if chosen == "PROHIBIDOS":
            return "NOT ALLOWED"
        if chosen == "CONDICIONALES":
            return "CONDITIONAL"
    return ""


def infer_checked_documents_for_46A(source_text):
    t = normalize_checkbox_text(source_text)
    docs = []

    patterns = [
        (r"\bX\s+FACTURA COMERCIAL\b", "SIGNED COMMERCIAL INVOICE IN 3 COPIES"),
        (r"\bX\s+FULL SET CLEAN ON BOARD BILL OF LADING\b", "FULL SET CLEAN ON BOARD BILL OF LADING PLUS 3 NON NEGOTIABLE COPIES"),
        (r"\bX\s+P[ÓO]LIZA O CERTIFICADO DE SEGURO\b", "INSURANCE POLICY OR CERTIFICATE"),
        (r"\bX\s+CERTIFICADO DE ORIGEN\b", "CERTIFICATE OF ORIGIN ISSUED BY COMPETENT AUTHORITIES"),
        (r"\bX\s+CERTIFICADO DE INSPECCI[ÓO]N\b", "INSPECTION CERTIFICATE"),
        (r"\bX\s+LISTA DE CONTENIDO\b", "PACKING LIST IN 3 COPIES"),
        (r'\bX\s+FORM\s+A\b', 'FORM "A" AS PER ATTACHED SHEET'),
        (r"\bX\s+CONOCIMIENTO A[ÉE]REO\b", "AIR WAYBILL"),
        (r"\bX\s+CMR\b", "INTERNATIONAL ROAD WAYBILL (CMR)"),
        (r"\bX\s+CIM\b", "RAIL WAYBILL (CIM)")
    ]

    for pattern, value in patterns:
        if re.search(pattern, t):
            docs.append(value)

    deduped = []
    seen = set()
    for d in docs:
        if d not in seen:
            deduped.append(d)
            seen.add(d)
    return deduped


def infer_field_71D_from_checkboxes(source_text):
    t = normalize_checkbox_text(source_text)

    if re.search(r"\bPOR CUENTA DE\s+X\s+BENEFICIARIO\b", t):
        return "ALL BANKING CHARGES OUTSIDE SPAIN ARE FOR BENEFICIARY'S ACCOUNT"
    if re.search(r"\bPOR CUENTA DE\s+X\s+ORDENANTE\b", t):
        return "ALL BANKING CHARGES OUTSIDE SPAIN ARE FOR APPLICANT'S ACCOUNT"

    window = extract_context_window(
        source_text,
        r"(POR CUENTA DE|GASTOS BANCARIOS FUERA DE ESPAÑA)",
        window=100
    )
    if not window:
        return ""

    chosen = nearest_marked_option_in_window(
        window,
        ["BENEFICIARIO", "ORDENANTE"],
        max_distance=24
    )

    if chosen == "BENEFICIARIO":
        return "ALL BANKING CHARGES OUTSIDE SPAIN ARE FOR BENEFICIARY'S ACCOUNT"
    if chosen == "ORDENANTE":
        return "ALL BANKING CHARGES OUTSIDE SPAIN ARE FOR APPLICANT'S ACCOUNT"

    return ""


def infer_field_20_from_text(source_text):
    t = to_upper(source_text)
    patterns_priority = [
        r"\b20\s*[: ]\s*([A-Z0-9\-\/]{3,16})",
        r"ORDER\s*NO\.?\s*[:\-]?\s*([A-Z0-9\-\/]{3,16})",
        r"ORDER\s*NUMBER\.?\s*[:\-]?\s*([A-Z0-9\-\/]{3,16})",
        r"N[ÚU]MERO DE PROPUESTA ELECTR[ÓO]NICA\s*[:\-]?\s*([0-9 ]{8,25})",
        r"ORDINAL(?: DE ENV[ÍI]O)?\s*[:\-]?\s*([A-Z0-9\-\/]{3,16})",
        r"REFERENCIA\s*[:\-]?\s*([A-Z0-9\-\/]{3,16})",
        r"REFERENCE\s*[:\-]?\s*([A-Z0-9\-\/]{3,16})",
        r"OPERACI[ÓO]N\s*[:\-]?\s*([A-Z0-9\-\/]{3,16})"
    ]
    for p in patterns_priority:
        m = re.search(p, t)
        if not m:
            continue
        candidate = re.sub(r"\s+", "", m.group(1)).strip()[:16]
        ok, _ = semantic_field_check("field_20", candidate)
        if ok:
            return candidate
    return ""


def infer_expiry_date_from_text(source_text):
    t = to_upper(source_text)
    patterns = [
        r"\b31D\s*[: ]\s*([0-9]{6})",
        r"LUGAR Y FECHA DE VENCIMIENTO\s*[:\-]?\s*([0-9]{6,8})",
        r"EXPIRY(?: PLACE)?(?: AND DATE)?\s*[:\-]?\s*([0-9]{6,8})"
    ]
    for p in patterns:
        m = re.search(p, t)
        if m:
            yymmdd = normalize_to_yymmdd(m.group(1))
            if yymmdd:
                return yymmdd
    return ""


def infer_expiry_place_from_text(source_text):
    t = to_upper(source_text)
    patterns = [
        r"\b31D\s*[: ]\s*[0-9]{6}\s*([A-Z][A-Z ,\-.]{2,40})",
        r"LUGAR Y FECHA DE VENCIMIENTO\s*[0-9]{6,8}\s*[-,:]?\s*([A-Z][A-Z ,\-.]{2,40})",
        r"EXPIRY(?: PLACE)?(?: AND DATE)?\s*[0-9]{6,8}\s*[-,:]?\s*([A-Z][A-Z ,\-.]{2,40})"
    ]
    for p in patterns:
        m = re.search(p, t)
        if m:
            place = re.sub(r"\s{2,}", " ", m.group(1)).strip(" ,.-")
            if place:
                return place

    if "HONG KONG" in t:
        return "HONG KONG"
    if "MADRID" in t:
        return "MADRID"
    if "BARCELONA" in t:
        return "BARCELONA"

    return ""


def infer_field_31D_from_text(source_text):
    yymmdd = infer_expiry_date_from_text(source_text)
    place = infer_expiry_place_from_text(source_text)
    if yymmdd and place:
        candidate = f"{yymmdd}{place}"
        ok, _ = semantic_field_check("field_31D", candidate)
        if ok:
            return candidate
    return ""


def infer_field_32B_from_text(source_text):
    t = to_upper(source_text)
    anchored_patterns = [
        r"\b32B\s*[: ]\s*([A-Z]{3})([0-9][0-9,\.]+)",
        r"DIVISA E IMPORTE\s*[:\-]?\s*([0-9][0-9\.,]+)\s*([A-Z]{3})",
        r"DIVISA E IMPORTE\s*[:\-]?\s*([A-Z]{3})\s*([0-9][0-9\.,]+)",
        r"DIVISA\s*([A-Z]{3}).{0,20}?IMPORTE\s*([0-9][0-9\.,]+)",
        r"IMPORTE\s*([0-9][0-9\.,]+).{0,20}?DIVISA\s*([A-Z]{3})"
    ]
    for p in anchored_patterns:
        m = re.search(p, t, re.S)
        if not m:
            continue
        g1, g2 = m.group(1), m.group(2)
        if re.fullmatch(r"[A-Z]{3}", g1):
            ccy, amt = g1, g2
        else:
            amt, ccy = g1, g2
        candidate = f"{ccy}{normalize_amount_for_32B(amt)}"
        ok, _ = semantic_field_check("field_32B", candidate)
        if ok:
            return candidate
    return ""


def infer_field_39A_from_text(source_text):
    t = to_upper(source_text)
    patterns = [
        r"\b39A\s*[: ]\s*(\d{1,2}/\d{1,2})",
        r"TOLERANCE\s*[-:]?\s*(\d{1,2})\s*PCT",
        r"ALLOWED TOLERANCE\s*[-:]?\s*(\d{1,2})\s*PCT"
    ]
    for p in patterns:
        m = re.search(p, t)
        if m:
            if "/" in m.group(1):
                candidate = m.group(1)
            else:
                candidate = f"{m.group(1)}/{m.group(1)}"
            ok, _ = semantic_field_check("field_39A", candidate)
            if ok:
                return candidate

    checkbox_candidate = infer_tolerance_from_checkboxes(source_text)
    if checkbox_candidate:
        return checkbox_candidate

    return ""


def infer_bic_from_text(source_text):
    t = to_upper(source_text)
    patterns = [
        r"\b([A-Z]{6}[A-Z0-9]{2}([A-Z0-9]{3})?)\b"
    ]
    for p in patterns:
        for m in re.finditer(p, t):
            bic = m.group(1)
            if len(bic) in (8, 11):
                return bic
    return ""


def infer_field_41A_from_text(source_text):
    t = to_upper(source_text)
    patterns = [
        r"\b41A\s*[: ]\s*([A-Z0-9]{8,11})\s*(BY (?:ACCEPTANCE|DEF PAYMENT|MIXED PYMT|NEGOTIATION|PAYMENT))",
        r"\b([A-Z0-9]{8,11})\s*(BY (?:ACCEPTANCE|DEF PAYMENT|MIXED PYMT|NEGOTIATION|PAYMENT))"
    ]
    for p in patterns:
        m = re.search(p, t)
        if m:
            candidate = f"{m.group(1)} {m.group(2)}"
            ok, _ = semantic_field_check("field_41A", candidate)
            if ok:
                return candidate

    checkbox_method = infer_payment_method_from_checkboxes(source_text)
    if checkbox_method:
        bic = infer_bic_from_text(source_text)
        if bic:
            candidate = f"{bic} {checkbox_method}"
            ok, _ = semantic_field_check("field_41A", candidate)
            if ok:
                return candidate

    if "A LA VISTA" in t or "AT SIGHT" in t:
        bic = infer_bic_from_text(source_text)
        if bic:
            candidate = f"{bic} BY PAYMENT"
            ok, _ = semantic_field_check("field_41A", candidate)
            if ok:
                return candidate
    return ""


def infer_field_43P_from_text(source_text):
    t = normalize_ocr_separators(source_text)

    allowed_patterns = [
        r"\b43P\s*[: ]\s*ALLOWED\b",
        r"\bPARTIAL\s+SHIPMENTS?\s*[:/\-|]?\s*ALLOWED\b",
        r"\bEXPEDICIONES?\s+PARCIALES?\s*[:/\-|]?\s*AUTORIZADAS?\b"
    ]
    not_allowed_patterns = [
        r"\b43P\s*[: ]\s*NOT ALLOWED\b",
        r"\bPARTIAL\s+SHIPMENTS?\s*[:/\-|]?\s*NOT ALLOWED\b",
        r"\bEXPEDICIONES?\s+PARCIALES?\s*[:/\-|]?\s*PROHIBIDAS?\b",
        r"\bEXPEDICIONES?\s+PARCIALES?\s*[:/\-|]?\s*NO\s+AUTORIZADAS?\b"
    ]
    conditional_patterns = [
        r"\b43P\s*[: ]\s*CONDITIONAL\b",
        r"\bPARTIAL\s+SHIPMENTS?\s*[:/\-|]?\s*CONDITIONAL\b",
        r"\bEXPEDICIONES?\s+PARCIALES?\s*[:/\-|]?\s*CONDICIONALES?\b"
    ]

    for p in allowed_patterns:
        if re.search(p, t):
            return "ALLOWED"
    for p in not_allowed_patterns:
        if re.search(p, t):
            return "NOT ALLOWED"
    for p in conditional_patterns:
        if re.search(p, t):
            return "CONDITIONAL"

    checkbox_value = infer_checkbox_selection_for_43p(t)
    if checkbox_value:
        return checkbox_value

    return ""


def infer_field_43T_from_text(source_text):
    t = normalize_ocr_separators(source_text)

    allowed_patterns = [
        r"\b43T\s*[: ]\s*ALLOWED\b",
        r"\bTRANSBORDOS?\s*[:/\-|]?\s*PERMITIDOS?\b",
        r"\bTRANSHIPMENTS?\s*[:/\-|]?\s*ALLOWED\b"
    ]
    not_allowed_patterns = [
        r"\b43T\s*[: ]\s*NOT ALLOWED\b",
        r"\bTRANSBORDOS?\s*[:/\-|]?\s*PROHIBIDOS?\b",
        r"\bTRANSBORDOS?\s*[:/\-|]?\s*NO\s+PERMITIDOS?\b",
        r"\bTRANSHIPMENTS?\s*[:/\-|]?\s*NOT ALLOWED\b"
    ]
    conditional_patterns = [
        r"\b43T\s*[: ]\s*CONDITIONAL\b",
        r"\bTRANSBORDOS?\s*[:/\-|]?\s*CONDICIONALES?\b",
        r"\bTRANSHIPMENTS?\s*[:/\-|]?\s*CONDITIONAL\b"
    ]

    for p in allowed_patterns:
        if re.search(p, t):
            return "ALLOWED"
    for p in not_allowed_patterns:
        if re.search(p, t):
            return "NOT ALLOWED"
    for p in conditional_patterns:
        if re.search(p, t):
            return "CONDITIONAL"

    checkbox_value = infer_checkbox_selection_for_43t(t)
    if checkbox_value:
        return checkbox_value

    return ""


def infer_field_44E_from_text(source_text):
    t = to_upper(source_text)
    patterns = [
        r"\b44E\s*[: ]\s*([A-Z].+)",
        r"EMBARQUE DESDE\s*([A-Z][A-Z ,]+)",
        r"FROM\s*([A-Z][A-Z ,]+)"
    ]
    for p in patterns:
        m = re.search(p, t)
        if m:
            value = clean_value(m.group(1)).split("\n")[0][:80]
            if value:
                return value
    return ""


def infer_field_44F_from_text(source_text):
    t = to_upper(source_text)
    patterns = [
        r"\b44F\s*[: ]\s*([A-Z].+)",
        r"CON DESTINO A\s*([A-Z][A-Z ,]+)",
        r"TO\s*([A-Z][A-Z ,]+)"
    ]
    for p in patterns:
        m = re.search(p, t)
        if m:
            value = clean_value(m.group(1)).split("\n")[0][:80]
            if value:
                return value
    return ""


def infer_field_44C_from_text(source_text):
    t = to_upper(source_text)
    patterns = [
        r"\b44C\s*[: ]\s*([0-9]{6})",
        r"NO M[ÁA]S TARDE DEL\s*([0-9]{6,8})",
        r"LATEST DATE OF SHIPMENT\s*[:\-]?\s*([0-9]{6,8})"
    ]
    for p in patterns:
        m = re.search(p, t)
        if m:
            value = normalize_to_yymmdd(m.group(1))
            if value:
                return value
    return ""


def infer_field_46A_from_checkboxes(source_text):
    docs = infer_checked_documents_for_46A(source_text)
    if not docs:
        return ""
    return "\n".join(f"+ {d}" for d in docs)


def infer_mt700_defaults(source_text, verified_map):
    t = to_upper(source_text)
    inferred = {}

    has_lc_context = any(x in t for x in [
        "LETTER OF CREDIT", "DOCUMENTARY CREDIT", "CREDITO DOCUMENTARIO", "CRÉDITO DOCUMENTARIO", "MT700"
    ])

    infer_map = {
        "field_20": infer_field_20_from_text,
        "field_31D": infer_field_31D_from_text,
        "field_32B": infer_field_32B_from_text,
        "field_39A": infer_field_39A_from_text,
        "field_41A": infer_field_41A_from_text,
        "field_43P": infer_field_43P_from_text,
        "field_43T": infer_field_43T_from_text,
        "field_44E": infer_field_44E_from_text,
        "field_44F": infer_field_44F_from_text,
        "field_44C": infer_field_44C_from_text,
        "field_46A": infer_field_46A_from_checkboxes,
        "field_71D": infer_field_71D_from_checkboxes,
    }

    for field_key, fn in infer_map.items():
        if not verified_map[field_key]["accepted"]:
            value = fn(source_text)
            if value:
                inferred[field_key] = {
                    "value": value,
                    "reason": f"Recovered from source text / checkbox logic for {field_key}",
                    "origin": ORIGIN_CHECKBOX_INFERRED if field_key in {"field_39A", "field_41A", "field_43P", "field_43T", "field_46A", "field_71D"} else ORIGIN_INFERRED
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
        elif "UCPURR" in t or ("URR" in t and "UCP" in t):
            value = "EUCPURR LATEST VERSION"
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
        date_candidates = [
            re.search(r"\b31C\s*[: ]\s*([0-9]{6})", t),
            re.search(r"\bFECHA\s*([0-9]{6,8})", t),
        ]
        picked = ""
        for m in date_candidates:
            if m:
                picked = normalize_to_yymmdd(m.group(1))
                if picked:
                    break
        inferred["field_31C"] = {
            "value": picked if picked else datetime.now().strftime("%y%m%d"),
            "reason": "System/source fallback issue date when absent",
            "origin": ORIGIN_SYSTEM_DEFAULT
        }

    if not verified_map["field_49"]["accepted"]:
        if any(x in t for x in [
            "WITHOUT CONFIRMATION",
            "WITHOUT ADDING CONFIRMATION",
            "SIN AÑADIR SU CONFIRMACIÓN",
            "SIN AÑADIR SU CONFIRMACION",
            "SIN AADIR SU CONFIRMACIN",
            "49 WITHOUT"
        ]):
            inferred["field_49"] = {
                "value": "WITHOUT",
                "reason": "Inferred from no-confirmation wording",
                "origin": ORIGIN_INFERRED
            }

    if not verified_map["field_48"]["accepted"] and has_lc_context:
        m = re.search(r"\b48\s*[: ]\s*(\d{1,3}(?:/[A-Z ].+)?)", t)
        if m:
            inferred["field_48"] = {
                "value": clean_value(m.group(1)),
                "reason": "Recovered from source presentation period",
                "origin": ORIGIN_INFERRED
            }
        else:
            m2 = re.search(r"DENTRO DE LOS\s+(\d{1,3})\s+D[IÍ]AS", t)
            if m2:
                inferred["field_48"] = {
                    "value": m2.group(1),
                    "reason": "Recovered from source presentation period wording",
                    "origin": ORIGIN_INFERRED
                }
            else:
                inferred["field_48"] = {
                    "value": "21",
                    "reason": "Default presentation period when absent",
                    "origin": ORIGIN_SYSTEM_DEFAULT
                }

    return inferred


def apply_inferred_defaults(verified_map, inferred):
    audit = []
    for key, meta in inferred.items():
        current = verified_map.get(key, {})
        if current.get("accepted"):
            continue

        value = meta["value"]
        ok, msg = semantic_field_check(key, value)
        if not ok and key not in {"field_46A", "field_71D"}:
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


def verify_extraction(extracted, source_text):
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
            elif origin != ORIGIN_DIRECT_OCR_MT700 and not evidence_supports_value(candidate_value, evidence, key):
                reason = "Rejected: evidence does not support extracted value"
            else:
                ok, msg = semantic_field_check(key, candidate_value)
                if not ok and key not in NARRATIVE_FIELDS and key not in PARTY_FIELDS:
                    reason = f"Rejected: {msg}"
                elif confidence < 55 and key not in NARRATIVE_FIELDS and key not in PARTY_FIELDS and origin != ORIGIN_DIRECT_OCR_MT700:
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


def rewrite_supported_narratives(verified_map):
    payload = {}
    for key in NARRATIVE_FIELDS:
        item = verified_map.get(key, {})
        if item.get("accepted") and item.get("value") and (item.get("evidence") or item.get("origin") in {ORIGIN_DIRECT_OCR_MT700, ORIGIN_CHECKBOX_INFERRED, ORIGIN_INFERRED, ORIGIN_SYSTEM_DEFAULT}):
            payload[key] = {
                "value": item["value"],
                "evidence": item.get("evidence", item["value"])
            }

    if not payload:
        return {}

    user_text = json.dumps(payload, ensure_ascii=False, indent=2)
    rewritten = call_llm_json(SYSTEM_NARRATIVE_REWRITE_PROMPT, user_text, max_tokens=1400)

    out = {}
    for key, original in payload.items():
        candidate = rewritten.get(key)
        if isinstance(candidate, str) and candidate.strip():
            out[key] = clean_value(candidate)
        else:
            out[key] = original["value"]
    return out


def build_mt700_from_verified_map(verified_map):
    lines = ["{1:F01BSCHESMMXXXX0123000001}{2:I700BSCHHKHHXXXXN2020}{4:"]
    for field_key in FIELD_KEYS:
        item = verified_map.get(field_key, {})
        if item.get("accepted") and item.get("value"):
            tag = FIELD_TO_TAG[field_key]
            lines.append(f":{tag}:{clean_value(item['value'])}")
    lines.append("-}")
    return "\n".join(lines).upper()


def parse_mt700_fields(mt700):
    pattern = re.compile(r"(?ms)^:([0-9]{2}[A-Z]?):(.*?)(?=^:[0-9]{2}[A-Z]?:|^-}\s*$|\Z)")
    return {tag: value.strip() for tag, value in pattern.findall(mt700 or "")}


def enrich_validation_messages(messages):
    enriched = []
    for msg in messages:
        m = re.search(r":([0-9]{2}[A-Z]?):", msg)
        if not m:
            enriched.append(msg)
            continue

        tag = m.group(1)
        field_key = TAG_TO_FIELD.get(tag)
        meta = FIELD_METADATA.get(field_key, {})
        name = meta.get("name", "")
        desc = meta.get("description", "")

        if name or desc:
            enriched.append(f"{msg} | {name} - {desc}")
        else:
            enriched.append(msg)
    return enriched


def validate_mt700(mt700, verified_map):
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

    if verified_map.get("field_48", {}).get("origin") == ORIGIN_SYSTEM_DEFAULT:
        warnings.append("48 inserted by default rule: absence implies 21 days where applicable")

    if verified_map.get("field_31C", {}).get("origin") == ORIGIN_SYSTEM_DEFAULT:
        warnings.append("31C inserted by system/source fallback issue date")

    issues = enrich_validation_messages(issues)
    warnings = enrich_validation_messages(warnings)

    score = max(0, 100 - len(issues) * 10 - len(warnings) * 3)
    return {
        "is_valid": len(issues) == 0,
        "score": score,
        "issues": issues,
        "warnings": warnings
    }


def extraction_table_rows(verified_map):
    rows = []
    for key in FIELD_KEYS:
        item = verified_map.get(key, {})
        meta = FIELD_METADATA.get(key, {})
        rows.append({
            "field": key,
            "tag": FIELD_TO_TAG[key],
            "field_name": meta.get("name", ""),
            "description": meta.get("description", ""),
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
    '<p class="small-note">Versión v6.9: parser OCR-MT700, auditoría explicativa y checkbox parsing reforzado para 41A/39A/43P/43T/46A/71D.</p>',
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
                    mode = "unknown"

                    if name.endswith(".pdf"):
                        native = extract_pdf_text_native(data)
                        ocr = extract_pdf_ocr_all_pages(data, max_pages=6)
                        txt = clean_text((native or "") + "\n\n" + (ocr or ""))
                        mode = "pdf-native+ocr"
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
                        "preview": txt[:1200]
                    })

                source_text = "\n\n".join(full_parts)

            with st.expander("🧪 Debug extracción", expanded=False):
                st.json(debug)
                st.text_area("Texto fuente", source_text[:12000], height=360)

            with st.spinner("Extrayendo candidatos con evidencia y OCR directo MT700..."):
                extraction_prompt = EXPECTED_GUIDE + "\n\nSOURCE DOCUMENTS:\n" + source_text[:22000]
                raw_extraction = call_llm_json(SYSTEM_EXTRACTION_PROMPT, extraction_prompt, max_tokens=2600)
                extracted = parse_extraction_object(raw_extraction)
                extracted, direct_ocr_map = merge_direct_ocr_into_extraction(extracted, source_text)

            with st.expander("🧩 Extracción cruda con evidencia", expanded=False):
                st.json(extracted)

            with st.expander("🔎 OCR directo tipo MT700", expanded=False):
                st.json(direct_ocr_map)

            verified_map, audit = verify_extraction(extracted, source_text)

            with st.expander("🛡️ Auditoría anti-alucinación", expanded=False):
                st.json(extraction_table_rows(verified_map))
                st.text("\n".join(audit))

            with st.spinner("Reescribiendo narrativas soportadas..."):
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
            st.session_state["direct_ocr_map"] = direct_ocr_map

            st.success("✅ Generado con parser OCR-MT700, control anti-alucinación y checkbox parsing reforzado")

        except Exception as e:
            st.error(f"Error durante la ejecución: {e}")

if "mt700" in st.session_state:
    with st.expander("🧪 Debug persistido", expanded=False):
        st.json(st.session_state.get("raw_extraction", {}))
        st.json(st.session_state.get("direct_ocr_map", {}))
        st.json(st.session_state.get("verified_map", {}))
        st.text_area("Texto fuente persistido", st.session_state.get("source_text", "")[:12000], height=320)

    col1, col2 = st.columns([2, 1])

    with col1:
        st.text_area("📡 MT700", st.session_state["mt700"], height=700)

    with col2:
        st.metric("Confianza", f"{st.session_state['validation']['score']}%")
        st.json(st.session_state["validation"])

    with st.expander("🧾 Evidencia por campo", expanded=False):
        st.json(extraction_table_rows(st.session_state["verified_map"]))

    txt_data = st.session_state["mt700"].encode("utf-8")
    json_data = json.dumps({
        "raw_extraction": st.session_state["raw_extraction"],
        "direct_ocr_map": st.session_state.get("direct_ocr_map", {}),
        "verified_map": st.session_state["verified_map"],
        "audit": st.session_state["audit"],
        "validation": st.session_state["validation"]
    }, ensure_ascii=False, indent=2).encode("utf-8")

    c1, c2 = st.columns(2)
    with c1:
        st.download_button(
            "⬇️ Descargar MT700 TXT",
            txt_data,
            file_name="MT700_ANTI_HALLUCINATION_V69.txt",
            mime="text/plain"
        )
    with c2:
        st.download_button(
            "⬇️ Descargar auditoría JSON",
            json_data,
            file_name="MT700_AUDIT_V69.json",
            mime="application/json"
        )
