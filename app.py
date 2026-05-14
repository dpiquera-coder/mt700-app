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

st.set_page_config(page_title="MT700 Generator v5.2", layout="wide")
st.title("📡 MT700 Generator - Trade Finance v5.2 (strict mapping + narrative repair)")

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

SPANISH_HINT_WORDS = [
    "factura", "conocimiento", "carta de porte", "poliza", "póliza",
    "certificado", "segun", "según", "mercancia", "mercancía",
    "beneficiario", "solicitante", "vencimiento", "ejemplares",
    "hoja adjunta", "cargador", "consignatario"
]

EXPECTED_GUIDE = """
Expected MT700 style guide:

- :27: sequence, e.g. 1/1
- :20: documentary credit number / LC reference
- :40A: form of documentary credit, e.g. IRREVOCABLE
- :40E: applicable rules, e.g. UCP LATEST VERSION
- :31C: issue date in YYMMDD
- :31D: expiry date in YYMMDD immediately followed by expiry place, e.g. 260621HONG KONG
- :50: applicant name and address
- :59: beneficiary name and address
- :32B: currency + amount only, e.g. USD33998,64
- :39A: tolerance only, e.g. 10/10
- :41A: available with bank BIC + method, e.g. BSCHHKHHXXXX / BY PAYMENT
- :42C: drafts at...
- :43P: ALLOWED / NOT ALLOWED
- :43T: ALLOWED / NOT ALLOWED
- :44E: port of loading / place of receipt
- :44F: port of discharge / final destination
- :44C: latest shipment date in YYMMDD
- :45A: goods description in English
- :46A: documents required in English
- :47A: additional conditions in English
- :48: presentation period, e.g. 21/AFTER SHIPMENT DATE
- :49: confirmation instructions, e.g. WITHOUT
- :57A: advising / routed bank BIC
- :71D: charges clause in English
- :78: instructions to paying / negotiating bank in English
- :72Z: sender to receiver information in English

Hard prohibitions:
- Do NOT output :41B:, :41C:, :41D:
- Do NOT place names/addresses in :32B:
- Do NOT place amounts in :50:, :59:, :71D:, :72Z:, :48:, :49:
- Do NOT place beneficiary name in :40A:
- Do NOT place addresses in :40E:
"""

STRUCTURED_EXTRACTION_PROMPT = """
You are a senior Trade Finance data extraction engine.

Extract factual values from the provided documents into the target MT700 field map.
Return JSON only.

Rules:
- Use null if not found.
- Preserve factual values, references, bank names, BICs, addresses, dates, ports, amounts.
- Convert narrative wording to concise English where needed.
- Do not guess a value if unsupported.
- Do not invent SWIFT tags outside the requested schema.
- Use the expected MT700 style guide supplied by the user.

Field meaning constraints:
- field_20 = LC reference / documentary credit number
- field_40A = IRREVOCABLE / REVOCABLE style form only
- field_40E = applicable rules only
- field_32B = currency+amount only
- field_39A = tolerance only
- field_48 = presentation period only
- field_49 = confirmation instruction only
- field_71D = charges clause only
"""

GENERATION_PROMPT = """
You are a senior Trade Finance officer specialized in SWIFT MT700.

Generate one final MT700 in SWIFT format from the structured field map.
Return ONLY the MT700. No commentary. No markdown.

Use the style guide exactly.
Respect the semantic type of each field.
Do not output any disallowed tags.
Narrative fields must be in English.
"""

NARRATIVE_FIX_PROMPT = """
You are a senior Trade Finance SWIFT MT700 narrative repair specialist.

You will receive:
1. the full MT700
2. the defective narrative fields
3. the source document text

Return ONLY the full corrected MT700 in SWIFT format.

Rules:
- Correct only the specified narrative fields.
- Keep all other fields unchanged.
- Narrative fields must be in professional banking English.
- Preserve factual content, addresses, references, amounts, dates, bank names and BICs.
- Do not add or remove SWIFT tags.
"""

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
            if isinstance(item, str):
                item = item.strip()
                if item:
                    parts.append(item)
            else:
                item = str(item).strip()
                if item:
                    parts.append(item)
        return "\n".join(parts).strip()
    if isinstance(value, dict):
        try:
            return json.dumps(value, ensure_ascii=False).strip()
        except Exception:
            return str(value).strip()
    return str(value).strip()

def call_llm_json(system_prompt: str, user_text: str, schema: Dict, max_tokens: int = 1600) -> Dict:
    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text}
            ],
            response_format=schema,
            max_tokens=max_tokens,
            temperature=0.05
        )
        return safe_json_load(response.choices[0].message.content or "{}")
    except Exception:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": system_prompt + "\nReturn only valid JSON."},
                {"role": "user", "content": user_text}
            ],
            response_format={"type": "json_object"},
            max_tokens=max_tokens,
            temperature=0.05
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
    return text[:50000].strip()

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

def normalize_field_map(data: Dict) -> Dict:
    if not isinstance(data, dict):
        return {k: "" for k in FIELD_KEYS}

    normalized = {}
    for key in FIELD_KEYS:
        normalized[key] = safe_str_value(data.get(key))

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
        value = safe_str_value(m.get(key))
        if value:
            lines.append(f":{tag}:{value}")

    lines.append("-}")
    return "\n".join(lines)

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

    forbidden = re.findall(r"^:([0-9]{2}[A-Z]?):", mt700 or "", re.M)
    for tag in forbidden:
        if tag not in ALLOWED_TAGS:
            issues.append(f"Forbidden tag detected :{tag}:")

    if "32B" in fields and not re.match(r"^[A-Z]{3}[0-9,\.]+$", fields["32B"].replace(" ", "")):
        issues.append(":32B: must contain currency and amount only")

    if "40A" in fields and fields["40A"].upper() not in ["IRREVOCABLE", "REVOCABLE"]:
        issues.append(":40A: must be form of documentary credit only")

    if "40E" in fields and len(fields["40E"]) > 80 and "," in fields["40E"]:
        issues.append(":40E: appears to contain address-like content")

    if "48" in fields and "%" in fields["48"]:
        issues.append(":48: cannot contain percentage value")

    if "49" in fields and "%" in fields["49"]:
        issues.append(":49: cannot contain percentage value")

    if "71D" in fields and re.fullmatch(r"[0-9,\.]+", fields["71D"].strip()):
        issues.append(":71D: cannot be numeric only")

    if "50" in fields and re.fullmatch(r"[0-9,\.]+", fields["50"].strip()):
        issues.append(":50: cannot be numeric only")

    if "59" in fields and re.fullmatch(r"[0-9,\.]+", fields["59"].strip()):
        issues.append(":59: cannot be numeric only")

    for tag in ["45A", "46A", "47A", "71D", "78", "72Z"]:
        if tag in fields and contains_spanish_narrative(fields[tag]):
            warnings.append(f":{tag}: contains non-English wording")

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

def repair_narrative_fields(mt700: str, defective_fields: List[str], source_text: str) -> str:
    if not defective_fields:
        return mt700

    repair_input = (
        "SOURCE DOCUMENTS:\n" + source_text[:30000] +
        "\n\nCURRENT MT700:\n" + mt700 +
        "\n\nDEFECTIVE NARRATIVE FIELDS:\n" + ", ".join(defective_fields)
    )

    try:
        repaired = call_llm_text(NARRATIVE_FIX_PROMPT, repair_input, max_tokens=2200)
        return repaired.strip() if repaired.strip() else mt700
    except Exception:
        return mt700

if not tesseract_available():
    st.info("OCR no disponible en este entorno. Instala tesseract-ocr y tesseract-ocr-spa para PDF escaneados.")

if st.button("🚀 Generar MT700"):
    if not files:
        st.warning("Sube documentos")
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

        st.subheader("🧪 Debug extracción")
        st.json(debug)
        st.text_area("Texto fuente", source_text[:5000], height=300)

        user_payload = EXPECTED_GUIDE + "\n\nSOURCE DOCUMENTS:\n" + source_text[:30000]

        field_map_raw = call_llm_json(STRUCTURED_EXTRACTION_PROMPT, user_payload, SCHEMA, max_tokens=1600)
        field_map = normalize_field_map(field_map_raw)

        st.subheader("🧪 Tipos del field_map")
        type_debug = {k: str(type(v)) for k, v in field_map_raw.items()} if isinstance(field_map_raw, dict) else {}
        st.json(type_debug)

        st.subheader("🧩 Field map estructurado")
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

        validation = validate_mt700(mt700)

        narrative_problem_fields = [
            f for f in validation.get("defective_fields", [])
            if f in ["45A", "46A", "47A", "71D", "78", "72Z"]
        ]

        if narrative_problem_fields:
            repaired_mt700 = repair_narrative_fields(mt700, narrative_problem_fields, source_text)
            repaired_validation = validate_mt700(repaired_mt700)

            if repaired_validation["score"] >= validation["score"]:
                mt700 = repaired_mt700
                validation = repaired_validation

        st.session_state["source_text"] = source_text
        st.session_state["field_map"] = field_map
        st.session_state["field_map_raw"] = field_map_raw
        st.session_state["mt700"] = mt700
        st.session_state["validation"] = validation
        st.success("✅ Generado")

if "mt700" in st.session_state:
    with st.expander("🧪 Debug persistido", expanded=False):
        st.json(st.session_state.get("field_map_raw", {}))
        st.json(st.session_state.get("field_map", {}))
        st.text_area("Texto fuente persistido", st.session_state.get("source_text", "")[:5000], height=280)

    col1, col2 = st.columns([2, 1])
    with col1:
        edited = st.text_area("📡 MT700", st.session_state["mt700"], height=650)
    with col2:
        st.metric("Confianza", f"{st.session_state['validation']['score']}%")
        st.json(st.session_state["validation"])

    parsed = parse_mt700_fields(edited)
    st.subheader("🧩 Campos parseados")
    st.json(parsed)

    txt_data = edited.encode("utf-8")
    json_data = json.dumps({
        "field_map_raw": st.session_state["field_map_raw"],
        "field_map": st.session_state["field_map"],
        "validation": st.session_state["validation"],
        "parsed_fields": parsed
    }, ensure_ascii=False, indent=2).encode("utf-8")

    c1, c2 = st.columns(2)
    with c1:
        st.download_button("⬇️ Descargar MT700 TXT", txt_data, file_name="MT700.txt", mime="text/plain")
    with c2:
        st.download_button("⬇️ Descargar validación JSON", json_data, file_name="MT700_validation.json", mime="application/json")
