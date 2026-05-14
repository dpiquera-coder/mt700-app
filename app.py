import streamlit as st
from groq import Groq
from io import BytesIO
import json
import re
import subprocess
import tempfile
import shutil
from typing import Dict, List

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
    page_title="MT700 Generator v5.6",
    layout="wide",
    page_icon="🏦"
)

SANTANDER_RED = "#EC0000"
SANTANDER_DARK_RED = "#C00000"
SANTANDER_LIGHT = "#FFF5F5"
SANTANDER_BORDER = "#F3C7C7"

st.markdown(f"""
<style>
:root {{
    --santander-red: {SANTANDER_RED};
    --santander-dark-red: {SANTANDER_DARK_RED};
    --santander-light: {SANTANDER_LIGHT};
    --santander-border: {SANTANDER_BORDER};
}}
.block-container {{
    padding-top: 1.5rem;
    padding-bottom: 2rem;
}}
.main {{
    background: linear-gradient(180deg, #fff 0%, #fff7f7 100%);
}}
[data-testid="stMetric"] {{
    background: white;
    border: 1px solid var(--santander-border);
    border-radius: 14px;
    padding: 14px 18px;
    box-shadow: 0 4px 18px rgba(236, 0, 0, 0.06);
}}
.stButton > button,
.stDownloadButton > button {{
    background: var(--santander-red);
    color: white;
    border: none;
    border-radius: 10px;
    padding: 0.6rem 1rem;
    font-weight: 600;
}}
.stButton > button:hover,
.stDownloadButton > button:hover {{
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
.mt700-hero-row {{
    display: flex;
    align-items: center;
    gap: 16px;
}}
.mt700-logo {{
    width: 52px;
    height: 52px;
    border-radius: 14px;
    background: rgba(255,255,255,0.14);
    display: flex;
    align-items: center;
    justify-content: center;
}}
.mt700-logo svg {{
    width: 34px;
    height: 34px;
    fill: white;
}}
.mt700-title {{
    font-size: 1.7rem;
    font-weight: 700;
    margin: 0;
    line-height: 1.1;
}}
.mt700-subtitle {{
    margin: 0.25rem 0 0 0;
    opacity: 0.92;
    font-size: 0.98rem;
}}
.section-title {{
    color: {SANTANDER_DARK_RED};
    font-weight: 700;
    margin-top: 0.5rem;
    margin-bottom: 0.35rem;
}}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="mt700-hero">
  <div class="mt700-hero-row">
    <div class="mt700-logo" aria-hidden="true">
      <svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
        <path d="M34.7 8.5c3.5 5.7 4.7 11.2 3.4 16.1-1 3.8-3.6 6.9-7.1 9.4 1.3-4.7-.2-8.4-3.2-12.4-2.1-2.8-3.6-6-3.1-9.9.6-4.4 3.8-8 10-3.2z"/>
        <path d="M22.2 37.4c2.8-3.4 6.4-5.8 11-7.1-1.6 2.7-1.2 5.8.2 8.4 1.8 3.3 4.7 6.1 5.8 10.1 1.4 5.1-1.2 8.9-7.5 8.9-8.7 0-14.1-7.5-9.5-20.3z"/>
        <ellipse cx="31.5" cy="54.5" rx="14.5" ry="4.5"/>
      </svg>
    </div>
    <div>
      <p class="mt700-title">MT700 GENERATOR</p>
      <p class="mt700-subtitle">STRICT SWIFT MAPPING, ENGLISH NARRATIVE REPAIR AND DOCUMENT-GROUNDED EXTRACTION</p>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

client = Groq(api_key=st.secrets["GROQ_API_KEY"])
files = st.file_uploader("SUBE DOCUMENTOS", accept_multiple_files=True)

ALLOWED_TAGS = [
    "27", "20", "40A", "40E", "31C", "31D", "50", "59", "32B", "39A", "41A", "42C",
    "43P", "43T", "44E", "44F", "44C", "45A", "46A", "47A", "48", "49", "57A", "71D", "78", "72Z"
]

FIELD_KEYS = [
    "field_27", "field_20", "field_40A", "field_40E", "field_31C", "field_31D",
    "field_50", "field_59", "field_32B", "field_39A", "field_41A", "field_42C",
    "field_43P", "field_43T", "field_44E", "field_44F", "field_44C", "field_45A",
    "field_46A", "field_47A", "field_48", "field_49", "field_57A", "field_71D",
    "field_78", "field_72Z"
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

NARRATIVE_TAGS = ["45A", "46A", "47A", "71D", "78", "72Z"]

SPANISH_HINT_WORDS = [
    "FACTURA", "CONOCIMIENTO", "CARTA DE PORTE", "POLIZA", "PÓLIZA",
    "CERTIFICADO", "SEGUN", "SEGÚN", "MERCANCIA", "MERCANCÍA",
    "BENEFICIARIO", "SOLICITANTE", "VENCIMIENTO", "EJEMPLARES",
    "HOJA ADJUNTA", "CARGADOR", "CONSIGNATARIO",
    "POR CORREO", "ENVIAR DOCUMENTOS", "GASTOS BANCARIOS",
    "FUERA DE ESPAÑA", "A CARGO DEL BENEFICIARIO",
    "EMITIDO POR", "A FAVOR DE", "SI HUBIERA"
]

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
    "SI HUBIERA": "IF ANY"
}

EXPECTED_GUIDE = """
EXPECTED MT700 STYLE GUIDE:
- USE ONLY DOCUMENT-SUPPORTED VALUES.
- NEVER INVENT DATA.
- NEVER COPY EXAMPLE VALUES FROM THE PROMPT.
- IF A FIELD IS NOT SUPPORTED BY THE DOCUMENT, RETURN IT EMPTY/NULL IN EXTRACTION.
- FINAL MT700 MUST BE UPPERCASE.
"""

STRUCTURED_EXTRACTION_PROMPT = """
YOU ARE A SENIOR TRADE FINANCE DATA EXTRACTION ENGINE.

EXTRACT FACTUAL VALUES FROM THE PROVIDED DOCUMENTS INTO THE TARGET MT700 FIELD MAP.
RETURN JSON ONLY.

STRICT GROUNDING RULES:
- USE ONLY THE DOCUMENT TEXT PROVIDED.
- DO NOT USE PRIOR KNOWLEDGE.
- DO NOT USE EXAMPLES FROM THE PROMPT AS REAL VALUES.
- DO NOT GUESS.
- DO NOT INFER UNSUPPORTED FACTS.
- IF A VALUE IS NOT EXPLICITLY SUPPORTED BY THE DOCUMENT, RETURN NULL.
- FOR EACH FIELD, RETURN:
  - VALUE
  - EVIDENCE (EXACT DOCUMENT SNIPPET SUPPORTING THE VALUE)
  - CONFIDENCE (0 TO 1)

EVIDENCE MUST COME FROM THE DOCUMENT TEXT.
IF THERE IS NO SUPPORTING EVIDENCE, VALUE MUST BE NULL.
"""

GENERATION_PROMPT = """
YOU ARE A SENIOR TRADE FINANCE OFFICER SPECIALIZED IN SWIFT MT700.

GENERATE ONE FINAL MT700 IN SWIFT FORMAT FROM THE STRUCTURED FIELD MAP.
RETURN ONLY THE MT700. NO COMMENTARY. NO MARKDOWN.

RULES:
- USE ONLY VALUES PRESENT IN THE PROVIDED STRUCTURED FIELD MAP.
- DO NOT INVENT OR COMPLETE MISSING VALUES.
- DO NOT USE EXAMPLES AS CONTENT.
- IF A FIELD IS EMPTY, LEAVE IT OUT OF THE GENERATED DRAFT; DO NOT GUESS.
- FINAL OUTPUT MUST BE FULLY UPPERCASE.
- NARRATIVE FIELDS MUST BE IN ENGLISH.
"""

NARRATIVE_TRANSLATION_PROMPT = """
YOU ARE A SENIOR TRADE FINANCE BANKING TRANSLATOR.

TRANSLATE ONLY THE PROVIDED MT700 NARRATIVE FIELD VALUES INTO PROFESSIONAL BANKING ENGLISH.
RETURN JSON ONLY.

RULES:
- INPUT FIELDS ARE MT700 NARRATIVE TAGS AND THEIR CURRENT VALUES.
- PRESERVE FACTUAL CONTENT: AMOUNTS, PERCENTAGES, REFERENCES, ADDRESSES, BANK NAMES, BICS, DATES, PHONE NUMBERS, COMPANY NAMES.
- TRANSLATE WORDING ONLY.
- DO NOT ADD NEW FACTS.
- DO NOT OMIT FACTS.
- KEEP SWIFT-STYLE CONCISE BANKING LANGUAGE.
- RETURN EXACTLY THE SAME KEYS YOU RECEIVED.
- RETURN VALUES IN UPPERCASE.
"""

SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "mt700_field_map",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                k: {
                    "type": "object",
                    "properties": {
                        "value": {"type": ["string", "null"]},
                        "evidence": {"type": "string"},
                        "confidence": {"type": ["number", "null"]}
                    },
                    "required": ["value", "evidence", "confidence"],
                    "additionalProperties": False
                }
                for k in FIELD_KEYS
            },
            "required": FIELD_KEYS,
            "additionalProperties": False
        }
    }
}

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

def safe_str_value(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value).strip()
    if isinstance(value, list):
        parts = []
        for item in value:
            if item is None:
                continue
            item = safe_str_value(item)
            if item:
                parts.append(item)
        return "\n".join(parts).strip()
    if isinstance(value, dict):
        try:
            return json.dumps(value, ensure_ascii=False).strip()
        except Exception:
            return str(value).strip()
    return str(value).strip()

def force_uppercase_mt700(text: str) -> str:
    return safe_str_value(text).upper()

def clean_spanish_artifacts(text: str) -> str:
    result = safe_str_value(text).upper()
    for es, en in sorted(SPANISH_TO_ENGLISH_REPLACEMENTS.items(), key=lambda x: len(x[0]), reverse=True):
        result = re.sub(rf"\b{re.escape(es)}\b", en, result)
    result = re.sub(r"\s{2,}", " ", result)
    result = re.sub(r" *\n *", "\n", result)
    return result.strip()

def normalize_for_match(text: str) -> str:
    text = safe_str_value(text).upper()
    text = re.sub(r"[^A-Z0-9\s,./:%()-]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()

def evidence_supports_value(value: str, evidence: str, source_text: str) -> bool:
    value_n = normalize_for_match(value)
    evidence_n = normalize_for_match(evidence)
    source_n = normalize_for_match(source_text)

    if not value_n or not evidence_n:
        return False
    if evidence_n not in source_n:
        return False

    tokens = [t for t in re.split(r"\s+", value_n) if t]
    if not tokens:
        return False

    matched = sum(1 for t in tokens if t in evidence_n)
    return (matched / len(tokens)) >= 0.6

def call_llm_json(system_prompt: str, user_text: str, schema: Dict, max_tokens: int = 1800) -> Dict:
    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text}
            ],
            response_format=schema,
            max_tokens=max_tokens,
            temperature=0.0
        )
        return safe_json_load(response.choices[0].message.content or "{}")
    except Exception:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": system_prompt + "\nRETURN ONLY VALID JSON."},
                {"role": "user", "content": user_text}
            ],
            response_format={"type": "json_object"},
            max_tokens=max_tokens,
            temperature=0.0
        )
        return safe_json_load(response.choices[0].message.content or "{}")

def call_llm_text(system_prompt: str, user_text: str, max_tokens: int = 2200) -> str:
    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text}
        ],
        max_tokens=max_tokens,
        temperature=0.05
    )
    return response.choices[0].message.content or ""

def clean_text(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = "".join(c for c in text if c.isprintable() or c in "\n\t")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text[:70000].strip()

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

def extract_pdf_ocr_all_pages(data: bytes) -> str:
    if not fitz or not tesseract_available():
        return ""
    try:
        doc = fitz.open(stream=data, filetype="pdf")
        out = []
        for i in range(doc.page_count):
            page = doc[i]
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            txt = pytesseract.image_to_string(img, lang="spa+eng")
            out.append(f"==PAGE {i+1}==\n{txt}")
        return "\n\n".join(out)
    except Exception:
        return ""

def ground_field_map(field_map_raw: Dict, source_text: str) -> Dict:
    grounded = {}
    for key in FIELD_KEYS:
        item = field_map_raw.get(key, {}) if isinstance(field_map_raw, dict) else {}
        value = safe_str_value(item.get("value")) if isinstance(item, dict) else ""
        evidence = safe_str_value(item.get("evidence")) if isinstance(item, dict) else ""
        confidence = item.get("confidence", 0) if isinstance(item, dict) else 0

        try:
            confidence = float(confidence) if confidence is not None else 0.0
        except Exception:
            confidence = 0.0

        is_grounded = False
        if value and evidence:
            is_grounded = evidence_supports_value(value, evidence, source_text)

        grounded[key] = {
            "value": value if is_grounded else "",
            "evidence": evidence,
            "confidence": round(confidence, 3) if is_grounded else 0.0,
            "grounded": is_grounded
        }
    return grounded

def normalize_field_map(grounded_map: Dict) -> Dict:
    if not isinstance(grounded_map, dict):
        return {k: "" for k in FIELD_KEYS}

    normalized = {}
    for key in FIELD_KEYS:
        item = grounded_map.get(key, {})
        value = safe_str_value(item.get("value")) if isinstance(item, dict) and item.get("grounded") else ""
        normalized[key] = clean_spanish_artifacts(value)

    if not normalized.get("field_27"):
        normalized["field_27"] = "1/1"

    if normalized.get("field_40A"):
        val = normalized["field_40A"].upper()
        if "IRREV" in val:
            normalized["field_40A"] = "IRREVOCABLE"
        elif "REVOC" in val:
            normalized["field_40A"] = "REVOCABLE"

    if normalized.get("field_40E") and "UCP" in normalized["field_40E"].upper():
        normalized["field_40E"] = "UCP LATEST VERSION"

    if normalized.get("field_32B"):
        v = normalized["field_32B"].replace(" ", "")
        v = re.sub(r"^(USD|EUR|GBP)\s*([0-9].*)$", r"\1\2", v)
        normalized["field_32B"] = v

    if normalized.get("field_43P"):
        v = normalized["field_43P"].upper()
        if "ALLOW" in v:
            normalized["field_43P"] = "ALLOWED"
        elif "NOT" in v:
            normalized["field_43P"] = "NOT ALLOWED"

    if normalized.get("field_43T"):
        v = normalized["field_43T"].upper()
        if "ALLOW" in v:
            normalized["field_43T"] = "ALLOWED"
        elif "NOT" in v:
            normalized["field_43T"] = "NOT ALLOWED"

    return normalized

def build_mt700_from_map(m: Dict) -> str:
    lines = [
        "{1:F01BSCHESMMXXXX0123000001}{2:I700BSCHHKHHXXXXN2020}{4:"
    ]
    mapping = {
        "27": "field_27", "20": "field_20", "40A": "field_40A", "40E": "field_40E",
        "31C": "field_31C", "31D": "field_31D", "50": "field_50", "59": "field_59",
        "32B": "field_32B", "39A": "field_39A", "41A": "field_41A", "42C": "field_42C",
        "43P": "field_43P", "43T": "field_43T", "44E": "field_44E", "44F": "field_44F",
        "44C": "field_44C", "45A": "field_45A", "46A": "field_46A", "47A": "field_47A",
        "48": "field_48", "49": "field_49", "57A": "field_57A", "71D": "field_71D",
        "78": "field_78", "72Z": "field_72Z"
    }

    for tag in ALLOWED_TAGS:
        key = mapping[tag]
        value = clean_spanish_artifacts(safe_str_value(m.get(key)))
        if value:
            lines.append(f":{tag}:{value}")

    lines.append("-}")
    return force_uppercase_mt700("\n".join(lines))

def parse_mt700_fields(mt700: str) -> Dict[str, str]:
    pattern = re.compile(r"(?ms)^:([0-9]{2}[A-Z]?):(.*?)(?=^:[0-9]{2}[A-Z]?:|^-}\s*$|\Z)")
    return {tag: value.strip() for tag, value in pattern.findall(mt700 or "")}

def contains_spanish_narrative(text: str) -> bool:
    t = safe_str_value(text).upper()
    return any(word in t for word in SPANISH_HINT_WORDS)

def validate_mt700(mt700: str) -> Dict:
    fields = parse_mt700_fields(mt700)
    issues, warnings = [], []

    for tag in ALLOWED_TAGS:
        if tag not in fields or not fields[tag].strip():
            issues.append(f"MISSING OR EMPTY FIELD :{tag}:")

    forbidden = re.findall(r"^:([0-9]{2}[A-Z]?):", mt700 or "", re.M)
    for tag in forbidden:
        if tag not in ALLOWED_TAGS:
            issues.append(f"FORBIDDEN TAG DETECTED :{tag}:")

    for tag in NARRATIVE_TAGS:
        if tag in fields and contains_spanish_narrative(fields[tag]):
            warnings.append(f":{tag}: CONTAINS NON-ENGLISH WORDING")

    score = 100 - min(70, len(issues) * 8) - min(20, len(warnings) * 3)
    score = max(score, 0)

    defective_fields = []
    for x in issues + warnings:
        defective_fields.extend(re.findall(r":([0-9]{2}[A-Z]?):", x))

    return {
        "is_valid": len(issues) == 0,
        "score": score,
        "issues": issues,
        "warnings": warnings,
        "defective_fields": sorted(set(defective_fields))
    }

def translate_narrative_fields(mt700: str, defective_fields: List[str], source_text: str) -> Dict[str, str]:
    parsed = parse_mt700_fields(mt700)
    payload = {}
    for tag in defective_fields:
        if tag in parsed and parsed[tag].strip():
            payload[tag] = parsed[tag]

    if not payload:
        return {}

    schema = {
        "type": "json_schema",
        "json_schema": {
            "name": "mt700_narrative_translation_dynamic",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {tag: {"type": "string"} for tag in payload.keys()},
                "required": list(payload.keys()),
                "additionalProperties": False
            }
        }
    }

    user_text = (
        "SOURCE DOCUMENTS:\n" + force_uppercase_mt700(source_text[:20000]) +
        "\n\nCURRENT NARRATIVE FIELD VALUES:\n" + json.dumps(payload, ensure_ascii=False, indent=2)
    )

    translated = call_llm_json(NARRATIVE_TRANSLATION_PROMPT, user_text, schema, max_tokens=1200)
    return {k: clean_spanish_artifacts(safe_str_value(v)) for k, v in translated.items() if k in payload}

def replace_mt700_fields(mt700: str, replacements: Dict[str, str]) -> str:
    if not replacements:
        return mt700

    pattern = re.compile(r"(?ms)^:([0-9]{2}[A-Z]?):(.*?)(?=^:[0-9]{2}[A-Z]?:|^-}\s*$|\Z)")

    def repl(match):
        tag = match.group(1)
        old_value = match.group(2)
        if tag in replacements and replacements[tag].strip():
            new_value = clean_spanish_artifacts(replacements[tag])
            return f":{tag}:{new_value}\n"
        return f":{tag}:{old_value}"

    result = pattern.sub(repl, mt700)
    result = re.sub(r"\n-}$", "\n-}", result)
    return force_uppercase_mt700(result)

def final_cleanup_mt700(mt700: str) -> str:
    parsed = parse_mt700_fields(mt700)
    rebuilt = []
    header_match = re.match(r"(?s)^(.*?\{4:\n)", mt700)
    header = header_match.group(1) if header_match else "{1:F01BSCHESMMXXXX0123000001}{2:I700BSCHHKHHXXXXN2020}{4:\n"
    rebuilt.append(header.rstrip("\n"))

    for tag in ALLOWED_TAGS:
        if tag in parsed and parsed[tag].strip():
            value = clean_spanish_artifacts(parsed[tag])
            rebuilt.append(f":{tag}:{value}")

    rebuilt.append("-}")
    return force_uppercase_mt700("\n".join(rebuilt))

def grounding_report(grounded_map: Dict) -> List[Dict]:
    rows = []
    for key in FIELD_KEYS:
        item = grounded_map.get(key, {})
        rows.append({
            "field": key,
            "tag": FIELD_TO_TAG[key],
            "grounded": item.get("grounded", False),
            "confidence": item.get("confidence", 0),
            "value": item.get("value", ""),
            "evidence": item.get("evidence", "")
        })
    return rows

if not tesseract_available():
    st.info("OCR NO DISPONIBLE EN ESTE ENTORNO. INSTALA TESSERACT-OCR Y TESSERACT-OCR-SPA PARA PDF ESCANEADOS.")

st.markdown('<p class="section-title">INPUT DOCUMENTS</p>', unsafe_allow_html=True)

if st.button("🚀 GENERAR MT700"):
    if not files:
        st.warning("SUBE DOCUMENTOS")
    else:
        full_parts = []
        debug = []

        for f in files:
            name = f.name.lower()
            data = f.getvalue()
            txt = ""

            if name.endswith(".pdf"):
                txt = extract_pdf_ocr_all_pages(data)
                mode = "ocr-all-pages"
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

        with st.expander("🧪 DEBUG EXTRACCIÓN", expanded=False):
            st.json(debug)
            st.text_area("TEXTO FUENTE", source_text[:5000], height=300)

        user_payload = EXPECTED_GUIDE + "\n\nSOURCE DOCUMENTS:\n" + source_text[:30000]

        field_map_raw = call_llm_json(STRUCTURED_EXTRACTION_PROMPT, user_payload, SCHEMA, max_tokens=1800)
        grounded_map = ground_field_map(field_map_raw, source_text)
        field_map = normalize_field_map(grounded_map)

        with st.expander("🧪 FIELD MAP RAW", expanded=False):
            st.json(field_map_raw)

        with st.expander("🛡️ GROUNDING REPORT", expanded=False):
            st.dataframe(grounding_report(grounded_map), use_container_width=True)

        with st.expander("🧩 FIELD MAP NORMALIZADO", expanded=False):
            st.json(field_map)

        seed_mt700 = build_mt700_from_map(field_map)

        mt700 = call_llm_text(
            GENERATION_PROMPT,
            EXPECTED_GUIDE
            + "\n\nSTRUCTURED FIELD MAP:\n"
            + json.dumps(field_map, ensure_ascii=False, indent=2)
            + "\n\nSEED MT700:\n"
            + seed_mt700,
            max_tokens=2200
        )

        mt700 = final_cleanup_mt700(mt700)
        validation = validate_mt700(mt700)

        narrative_problem_fields = [
            f for f in validation.get("defective_fields", [])
            if f in NARRATIVE_TAGS
        ]

        translated_fields = {}
        if narrative_problem_fields:
            translated_fields = translate_narrative_fields(mt700, narrative_problem_fields, source_text)
            mt700_repaired = replace_mt700_fields(mt700, translated_fields)
            mt700_repaired = final_cleanup_mt700(mt700_repaired)
            repaired_validation = validate_mt700(mt700_repaired)

            if repaired_validation["score"] >= validation["score"]:
                mt700 = mt700_repaired
                validation = repaired_validation

        mt700 = final_cleanup_mt700(mt700)
        validation = validate_mt700(mt700)

        st.session_state["source_text"] = source_text
        st.session_state["field_map_raw"] = field_map_raw
        st.session_state["grounded_map"] = grounded_map
        st.session_state["field_map"] = field_map
        st.session_state["translated_fields"] = translated_fields
        st.session_state["mt700"] = mt700
        st.session_state["validation"] = validation
        st.success("✅ GENERADO")

if "mt700" in st.session_state:
    st.markdown('<p class="section-title">RESULT</p>', unsafe_allow_html=True)

    col1, col2 = st.columns([2, 1])
    with col1:
        edited = st.text_area("📡 MT700", st.session_state["mt700"], height=650)
    with col2:
        st.metric("CONFIANZA", f"{st.session_state['validation']['score']}%")
        st.json(st.session_state["validation"])

    parsed = parse_mt700_fields(edited)

    with st.expander("🧪 DEBUG PERSISTIDO", expanded=False):
        st.json(st.session_state.get("field_map_raw", {}))
        st.json(st.session_state.get("grounded_map", {}))
        st.json(st.session_state.get("field_map", {}))
        st.json(st.session_state.get("translated_fields", {}))
        st.text_area("TEXTO FUENTE PERSISTIDO", st.session_state.get("source_text", "")[:5000], height=280)

    with st.expander("🧩 CAMPOS PARSEADOS", expanded=False):
        st.json(parsed)

    txt_data = force_uppercase_mt700(edited).encode("utf-8")
    json_data = json.dumps({
        "field_map_raw": st.session_state["field_map_raw"],
        "grounded_map": st.session_state["grounded_map"],
        "field_map": st.session_state["field_map"],
        "translated_fields": st.session_state.get("translated_fields", {}),
        "validation": st.session_state["validation"],
        "parsed_fields": parsed
    }, ensure_ascii=False, indent=2).encode("utf-8")

    c1, c2 = st.columns(2)
    with c1:
        st.download_button("⬇️ DESCARGAR MT700 TXT", txt_data, file_name="MT700.txt", mime="text/plain")
    with c2:
        st.download_button("⬇️ DESCARGAR VALIDACIÓN JSON", json_data, file_name="MT700_validation.json", mime="application/json")
