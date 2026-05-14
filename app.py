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
    page_title="MT700 Generator v5.4.1",
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
    background: white; border: 1px solid var(--santander-border); border-radius: 14px;
    padding: 14px 18px; box-shadow: 0 4px 18px rgba(236, 0, 0, 0.06);
}}
.stButton > button, .stDownloadButton > button {{
    background: var(--santander-red); color: white; border: none; border-radius: 10px;
    padding: 0.6rem 1rem; font-weight: 600;
}}
.stButton > button:hover, .stDownloadButton > button:hover {{
    background: var(--santander-dark-red); color: white;
}}
div[data-testid="stExpander"] {{
    border: 1px solid #f0d6d6; border-radius: 12px; background: #fffdfd;
    box-shadow: 0 2px 10px rgba(236, 0, 0, 0.04);
}}
.mt700-hero {{
    background: linear-gradient(135deg, {SANTANDER_RED} 0%, #ff3b30 100%);
    color: white; border-radius: 18px; padding: 22px 24px; margin-bottom: 1rem;
    box-shadow: 0 12px 30px rgba(236, 0, 0, 0.18);
}}
.mt700-title {{ font-size: 1.7rem; font-weight: 700; margin: 0; }}
.mt700-subtitle {{ margin: 0.25rem 0 0 0; opacity: 0.92; font-size: 0.98rem; }}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="mt700-hero">
  <p class="mt700-title">MT700 Generator</p>
  <p class="mt700-subtitle">Trade Finance assistant with strict SWIFT mapping, validation and English narrative repair</p>
</div>
""", unsafe_allow_html=True)

client = Groq(api_key=st.secrets["GROQ_API_KEY"])
files = st.file_uploader("Sube documentos", accept_multiple_files=True)

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

NARRATIVE_TAGS = ["45A", "46A", "47A", "71D", "78", "72Z"]

SPANISH_HINT_WORDS = [
    "factura", "conocimiento", "carta de porte", "poliza", "póliza",
    "certificado", "segun", "según", "mercancia", "mercancía",
    "beneficiario", "solicitante", "vencimiento", "ejemplares",
    "hoja adjunta", "cargador", "consignatario",
    "por correo", "enviar documentos", "gastos bancarios",
    "fuera de españa", "a cargo del beneficiario"
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
    "A CARGO DEL BENEFICIARIO": "FOR BENEFICIARY'S ACCOUNT"
}

EXPECTED_GUIDE = """
Expected MT700 style guide:
- Final output must be uppercase.
- Use only allowed MT700 tags.
- Narrative fields must be in English.
"""

STRUCTURED_EXTRACTION_PROMPT = """
You are a senior Trade Finance data extraction engine.
Extract factual values from the provided documents into the target MT700 field map.
Return JSON only.
Use null if not found.
Do not invent values.
"""

GENERATION_PROMPT = """
You are a senior Trade Finance officer specialized in SWIFT MT700.
Generate one final MT700 in SWIFT format from the structured field map.
Return ONLY the MT700. No commentary. No markdown.
Final output must be uppercase.
"""

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
        return "\n".join(safe_str_value(x) for x in value if safe_str_value(x)).strip()
    if isinstance(value, dict):
        try:
            return json.dumps(value, ensure_ascii=False).strip()
        except Exception:
            return str(value).strip()
    return str(value).strip()

def force_uppercase(text: str) -> str:
    return safe_str_value(text).upper()

def clean_spanish_artifacts(text: str) -> str:
    result = force_uppercase(text)
    for es, en in sorted(SPANISH_TO_ENGLISH_REPLACEMENTS.items(), key=lambda x: len(x[0]), reverse=True):
        result = re.sub(rf"\b{re.escape(es)}\b", en, result)
    result = re.sub(r"[ ]{2,}", " ", result)
    result = re.sub(r" *\n *", "\n", result)
    return result.strip()

def call_llm_json(system_prompt: str, user_text: str, schema: Dict, max_tokens: int = 1200) -> Dict:
    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text[:18000]}
        ],
        response_format=schema,
        max_tokens=max_tokens,
        temperature=0.05
    )
    return safe_json_load(response.choices[0].message.content or "{}")

def call_llm_text(system_prompt: str, user_text: str, max_tokens: int = 1800) -> str:
    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text[:18000]}
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
    return text[:30000].strip()

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

def extract_pdf_ocr_all_pages(data: bytes, max_pages: int = 3) -> str:
    if not fitz or not tesseract_available():
        return ""
    try:
        doc = fitz.open(stream=data, filetype="pdf")
        out = []
        pages = min(doc.page_count, max_pages)
        for i in range(pages):
            page = doc[i]
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            txt = pytesseract.image_to_string(img, lang="spa+eng")
            out.append(f"==PAGE {i+1}==\n{txt}")
        return "\n\n".join(out)
    except Exception:
        return ""

def normalize_field_map(data: Dict) -> Dict:
    if not isinstance(data, dict):
        return {k: "" for k in FIELD_KEYS}
    normalized = {k: clean_spanish_artifacts(safe_str_value(data.get(k))) for k in FIELD_KEYS}
    if not normalized.get("field_27"):
        normalized["field_27"] = "1/1"
    return normalized

def build_mt700_from_map(m: Dict) -> str:
    lines = ["{1:F01BSCHESMMXXXX0123000001}{2:I700BSCHHKHHXXXXN2020}{4:"]
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
        value = safe_str_value(m.get(mapping[tag]))
        if value:
            lines.append(f":{tag}:{value}")
    lines.append("-}")
    return "\n".join(lines).upper()

def parse_mt700_fields(mt700: str) -> Dict[str, str]:
    pattern = re.compile(r"(?ms)^:([0-9]{2}[A-Z]?):(.*?)(?=^:[0-9]{2}[A-Z]?:|^-}\s*$|\Z)")
    return {tag: value.strip() for tag, value in pattern.findall(mt700 or "")}

def contains_spanish_narrative(text: str) -> bool:
    t = (text or "").lower()
    return any(word in t for word in SPANISH_HINT_WORDS)

def validate_mt700(mt700: str) -> Dict:
    fields = parse_mt700_fields(mt700)
    issues, warnings = [], []
    for tag in ALLOWED_TAGS:
        if tag not in fields or not fields[tag].strip():
            issues.append(f"Missing or empty field :{tag}:")
    for tag in NARRATIVE_TAGS:
        if tag in fields and contains_spanish_narrative(fields[tag]):
            warnings.append(f":{tag}: contains non-English wording")
    score = 100 - min(70, len(issues) * 8) - min(20, len(warnings) * 3)
    return {
        "is_valid": len(issues) == 0,
        "score": max(score, 0),
        "issues": issues,
        "warnings": warnings,
        "defective_fields": sorted(set(re.findall(r":([0-9]{2}[A-Z]?):", " ".join(issues + warnings))))
    }

def final_cleanup_mt700(mt700: str, seed_mt700: str = "") -> str:
    parsed = parse_mt700_fields(mt700)
    if len(parsed) < 5 and seed_mt700:
        return seed_mt700.upper()
    rebuilt = ["{1:F01BSCHESMMXXXX0123000001}{2:I700BSCHHKHHXXXXN2020}{4:"]
    for tag in ALLOWED_TAGS:
        if tag in parsed and parsed[tag].strip():
            rebuilt.append(f":{tag}:{clean_spanish_artifacts(parsed[tag])}")
    rebuilt.append("-}")
    return "\n".join(rebuilt).upper()

SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "mt700_field_map",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {k: {"type": ["string", "null"]} for k in FIELD_KEYS},
            "required": FIELD_KEYS,
            "additionalProperties": False
        }
    }
}

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
                        txt = extract_pdf_ocr_all_pages(data, max_pages=3)
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
                    debug.append({"file": f.name, "mode": mode, "chars": len(txt), "preview": txt[:800]})

                source_text = "\n\n".join(full_parts)

            with st.expander("🧪 Debug extracción", expanded=False):
                st.json(debug)
                st.text_area("Texto fuente", source_text[:5000], height=300)

            with st.spinner("Extrayendo field map..."):
                user_payload = EXPECTED_GUIDE + "\n\nSOURCE DOCUMENTS:\n" + source_text[:18000]
                field_map_raw = call_llm_json(STRUCTURED_EXTRACTION_PROMPT, user_payload, SCHEMA, max_tokens=1200)
                field_map = normalize_field_map(field_map_raw)

            with st.expander("🧩 Field map estructurado", expanded=False):
                st.json(field_map)

            seed_mt700 = build_mt700_from_map(field_map)

            with st.expander("🧪 Seed MT700", expanded=False):
                st.text_area("Seed", seed_mt700, height=320)

            with st.spinner("Generando MT700..."):
                mt700 = call_llm_text(
                    GENERATION_PROMPT,
                    EXPECTED_GUIDE
                    + "\n\nSTRUCTURED FIELD MAP:\n"
                    + json.dumps(field_map, ensure_ascii=False, indent=2)
                    + "\n\nSEED MT700:\n"
                    + seed_mt700,
                    max_tokens=1800
                )

            with st.expander("🧪 Raw MT700 model output", expanded=False):
                st.text_area("Model output", mt700, height=320)

            mt700 = final_cleanup_mt700(mt700, seed_mt700=seed_mt700)
            validation = validate_mt700(mt700)

            st.session_state["source_text"] = source_text
            st.session_state["field_map"] = field_map
            st.session_state["field_map_raw"] = field_map_raw
            st.session_state["seed_mt700"] = seed_mt700
            st.session_state["mt700"] = mt700
            st.session_state["validation"] = validation
            st.success("✅ Generado")

        except Exception as e:
            st.error(f"Error durante la ejecución: {e}")

if "mt700" in st.session_state:
    with st.expander("🧪 Debug persistido", expanded=False):
        st.json(st.session_state.get("field_map_raw", {}))
        st.json(st.session_state.get("field_map", {}))
        st.text_area("Texto fuente persistido", st.session_state.get("source_text", "")[:5000], height=280)
        st.text_area("Seed persistido", st.session_state.get("seed_mt700", ""), height=220)

    col1, col2 = st.columns([2, 1])
    with col1:
        edited = st.text_area("📡 MT700", st.session_state["mt700"], height=650)
    with col2:
        st.metric("Confianza", f"{st.session_state['validation']['score']}%")
        st.json(st.session_state["validation"])

    with st.expander("🧩 Campos parseados", expanded=False):
        st.json(parse_mt700_fields(edited))

    txt_data = edited.upper().encode("utf-8")
    json_data = json.dumps({
        "field_map_raw": st.session_state["field_map_raw"],
        "field_map": st.session_state["field_map"],
        "validation": st.session_state["validation"]
    }, ensure_ascii=False, indent=2).encode("utf-8")

    c1, c2 = st.columns(2)
    with c1:
        st.download_button("⬇️ Descargar MT700 TXT", txt_data, file_name="MT700.txt", mime="text/plain")
    with c2:
        st.download_button("⬇️ Descargar validación JSON", json_data, file_name="MT700_validation.json", mime="application/json")
