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

st.set_page_config(page_title="MT700 Generator v6", layout="wide", page_icon="🏦")
st.title("🏦 MT700 GENERATOR - GROUNDED EXTRACTION MODE")

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

FIELD_TAG_MAP = {
    "27": "field_27", "20": "field_20", "40A": "field_40A", "40E": "field_40E",
    "31C": "field_31C", "31D": "field_31D", "50": "field_50", "59": "field_59",
    "32B": "field_32B", "39A": "field_39A", "41A": "field_41A", "42C": "field_42C",
    "43P": "field_43P", "43T": "field_43T", "44E": "field_44E", "44F": "field_44F",
    "44C": "field_44C", "45A": "field_45A", "46A": "field_46A", "47A": "field_47A",
    "48": "field_48", "49": "field_49", "57A": "field_57A", "71D": "field_71D",
    "78": "field_78", "72Z": "field_72Z"
}

GROUNDED_EXTRACTION_PROMPT = """
YOU ARE A TRADE FINANCE DOCUMENT EXTRACTION ENGINE.

TASK:
EXTRACT MT700-RELEVANT FIELDS FROM THE PROVIDED DOCUMENTS.

STRICT GROUNDING RULES:
- USE ONLY THE DOCUMENT TEXT PROVIDED.
- DO NOT USE PRIOR KNOWLEDGE.
- DO NOT USE EXAMPLES FROM THE PROMPT AS FIELD VALUES.
- DO NOT GUESS.
- DO NOT INFER UNSUPPORTED FACTS.
- IF A VALUE IS NOT EXPLICITLY SUPPORTED BY THE DOCUMENT, RETURN:
  - "value": null
  - "evidence": ""
  - "confidence": 0

FOR EVERY FIELD:
- "value" = THE EXTRACTED VALUE
- "evidence" = EXACT DOCUMENT SNIPPET SUPPORTING THAT VALUE
- "confidence" = NUMBER BETWEEN 0 AND 1

IMPORTANT:
- EVIDENCE MUST BE COPIED FROM THE DOCUMENT TEXT, NOT PARAPHRASED.
- IF YOU CANNOT QUOTE SUPPORTING EVIDENCE, THE VALUE MUST BE NULL.
- NEVER FILL A FIELD JUST BECAUSE IT LOOKS STANDARD.
- NEVER COPY EXAMPLE VALUES FROM INSTRUCTIONS.
- NARRATIVE FIELDS MAY BE NORMALIZED INTO ENGLISH ONLY IF THE FACTUAL CONTENT IS SUPPORTED BY THE DOCUMENT.
- IF THE DOCUMENT IS IN SPANISH, YOU MAY TRANSLATE THE NARRATIVE TO ENGLISH, BUT THE EVIDENCE MUST STILL BE THE ORIGINAL DOCUMENT SNIPPET.

RETURN JSON ONLY.
"""

SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "mt700_grounded_field_map",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                key: {
                    "type": "object",
                    "properties": {
                        "value": {"type": ["string", "null"]},
                        "evidence": {"type": "string"},
                        "confidence": {"type": "number"}
                    },
                    "required": ["value", "evidence", "confidence"],
                    "additionalProperties": False
                }
                for key in FIELD_KEYS
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

def safe_str(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value).strip()
    if isinstance(value, list):
        return "\n".join(safe_str(x) for x in value if safe_str(x)).strip()
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False).strip()
    return str(value).strip()

def normalize_text(text: str) -> str:
    text = safe_str(text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

def normalize_for_match(text: str) -> str:
    text = normalize_text(text).upper()
    text = re.sub(r"[^A-Z0-9\s,./:%()-]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()

def evidence_supports_value(value: str, evidence: str, source_text: str) -> bool:
    value_n = normalize_for_match(value)
    evidence_n = normalize_for_match(evidence)
    source_n = normalize_for_match(source_text)

    if not value_n:
        return False
    if not evidence_n:
        return False
    if evidence_n not in source_n:
        return False

    value_tokens = [t for t in re.split(r"\s+", value_n) if t]
    if not value_tokens:
        return False

    matched = sum(1 for t in value_tokens if t in evidence_n)
    ratio = matched / len(value_tokens)

    return ratio >= 0.6

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

def call_llm_json(system_prompt: str, user_text: str, schema: Dict, max_tokens: int = 2400) -> Dict:
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
        return {}

def grounded_sanitize(field_map_raw: Dict, source_text: str) -> Dict:
    sanitized = {}
    for key in FIELD_KEYS:
        item = field_map_raw.get(key, {}) if isinstance(field_map_raw, dict) else {}
        value = safe_str(item.get("value")) if isinstance(item, dict) else ""
        evidence = safe_str(item.get("evidence")) if isinstance(item, dict) else ""
        confidence = item.get("confidence", 0) if isinstance(item, dict) else 0

        try:
            confidence = float(confidence)
        except Exception:
            confidence = 0.0

        supported = False
        if value and evidence:
            supported = evidence_supports_value(value, evidence, source_text)

        if not supported:
            sanitized[key] = {
                "value": None,
                "evidence": evidence,
                "confidence": 0.0,
                "grounded": False
            }
        else:
            sanitized[key] = {
                "value": value.upper(),
                "evidence": evidence,
                "confidence": round(confidence, 3),
                "grounded": True
            }

    return sanitized

def build_mt700_from_grounded_map(grounded_map: Dict) -> str:
    lines = ["{1:F01BSCHESMMXXXX0123000001}{2:I700BSCHHKHHXXXXN2020}{4:"]
    for tag in ALLOWED_TAGS:
        key = FIELD_TAG_MAP[tag]
        item = grounded_map.get(key, {})
        value = safe_str(item.get("value"))
        grounded = item.get("grounded", False)
        if value and grounded:
            lines.append(f":{tag}:{value.upper()}")
    lines.append("-}")
    return "\n".join(lines)

def grounded_report(grounded_map: Dict) -> List[Dict]:
    rows = []
    for tag, key in FIELD_TAG_MAP.items():
        item = grounded_map.get(key, {})
        rows.append({
            "tag": tag,
            "value": item.get("value"),
            "grounded": item.get("grounded", False),
            "confidence": item.get("confidence", 0),
            "evidence": item.get("evidence", "")
        })
    return rows

if not tesseract_available():
    st.info("OCR NO DISPONIBLE EN ESTE ENTORNO. INSTALA TESSERACT-OCR Y TESSERACT-OCR-SPA PARA PDF ESCANEADOS.")

if st.button("🚀 GENERAR MT700 GROUNDED"):
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
                "preview": txt[:1000]
            })

        source_text = "\n\n".join(full_parts)

        with st.expander("DEBUG EXTRACCIÓN", expanded=False):
            st.json(debug)
            st.text_area("TEXTO FUENTE", source_text[:8000], height=300)

        field_map_raw = call_llm_json(
            GROUNDED_EXTRACTION_PROMPT,
            "DOCUMENT TEXT:\n" + source_text[:40000],
            SCHEMA,
            max_tokens=2600
        )

        grounded_map = grounded_sanitize(field_map_raw, source_text)
        mt700 = build_mt700_from_grounded_map(grounded_map)

        st.session_state["source_text"] = source_text
        st.session_state["field_map_raw"] = field_map_raw
        st.session_state["grounded_map"] = grounded_map
        st.session_state["mt700"] = mt700

        st.success("✅ GENERADO EN MODO GROUNDED")

if "mt700" in st.session_state:
    st.text_area("📡 MT700", st.session_state["mt700"], height=500)

    with st.expander("GROUNDING REPORT", expanded=False):
        st.dataframe(grounded_report(st.session_state["grounded_map"]), use_container_width=True)

    with st.expander("RAW EXTRACTION", expanded=False):
        st.json(st.session_state["field_map_raw"])

    txt_data = st.session_state["mt700"].encode("utf-8")
    json_data = json.dumps({
        "field_map_raw": st.session_state["field_map_raw"],
        "grounded_map": st.session_state["grounded_map"]
    }, ensure_ascii=False, indent=2).encode("utf-8")

    c1, c2 = st.columns(2)
    with c1:
        st.download_button("⬇️ DESCARGAR MT700 TXT", txt_data, file_name="MT700.txt", mime="text/plain")
    with c2:
        st.download_button("⬇️ DESCARGAR GROUNDING JSON", json_data, file_name="MT700_grounding.json", mime="application/json")
