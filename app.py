import streamlit as st
from groq import Groq
from io import BytesIO
import json
import re
import subprocess
import tempfile
from typing import Dict, Optional, List

try:
    import pdfplumber
except Exception:
    pdfplumber = None

try:
    from PyPDF2 import PdfReader
except Exception:
    PdfReader = None

try:
    import docx
except Exception:
    docx = None

st.set_page_config(page_title="MT700 Generator v3.1", layout="wide")
st.title("📡 MT700 Generator - Trade Finance v3.1")

client = Groq(api_key=st.secrets["GROQ_API_KEY"])
files = st.file_uploader("Sube documentos", accept_multiple_files=True)

GEN_PROMPT = """
You are a senior Trade Finance officer specialized in documentary credits and SWIFT MT700.
Return ONLY one final MT700 in SWIFT format, no commentary.

Mandatory fields:
:27: :20: :40A: :40E: :31C: :31D: :50: :59: :32B: :39A: :41A: :42C: :43P: :43T:
:44E: :44F: :44C: :45A: :46A: :47A: :48: :49: :57A: :71D: :78: :72Z:

Critical rules:
- :41A: is the bank with which the credit is available.
- :57A: is the advising/routed bank. Never swap :41A: and :57A:.
- :31D: must include expiry date and expiry place.
- :44C: latest shipment date.
- :45A: goods + incoterm + HS code + order reference if available.
- :46A: exact documentary requirements in banking wording.
- :78: must contain operational reimbursement/presentation instructions.
- No placeholders. No explanations. No empty mandatory fields.
"""

CORRECTION_PROMPT = """
You are a senior Trade Finance SWIFT MT700 repair specialist.
Repair the MT700 draft using the extracted documents and the validation findings.
Return ONLY the corrected MT700.

Fix strictly:
- :31D: date + place
- :41A: / :57A: routing logic
- :45A: completeness
- :46A: documentary wording
- :78: reimbursement/presentation instructions
- remove placeholders
- preserve correct content
"""

FIELD_FIX_PROMPT = """
You are a senior Trade Finance SWIFT MT700 field repair specialist.
You will receive:
1. extracted documents
2. current MT700
3. specific defective fields
Correct ONLY the defective fields while preserving the rest of the MT700.
Return ONLY the full corrected MT700 in SWIFT format.
"""

EXTRACTION_PROMPT = """
You are a Trade Finance document extraction engine.
Extract only factual data from the documents. Use null if missing.
Return JSON only.
"""

VAL_PROMPT = """
You are a senior Trade Finance MT700 validator.
Validate strictly against format and banking logic.
Return JSON only.
"""

EXTRACTION_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "trade_extraction",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "applicant": {"type": ["string", "null"]},
                "beneficiary": {"type": ["string", "null"]},
                "currency": {"type": ["string", "null"]},
                "amount": {"type": ["string", "null"]},
                "issue_date": {"type": ["string", "null"]},
                "expiry_date": {"type": ["string", "null"]},
                "expiry_place": {"type": ["string", "null"]},
                "available_with_bank": {"type": ["string", "null"]},
                "advising_bank": {"type": ["string", "null"]},
                "latest_shipment_date": {"type": ["string", "null"]},
                "port_of_loading": {"type": ["string", "null"]},
                "port_of_destination": {"type": ["string", "null"]},
                "incoterm": {"type": ["string", "null"]},
                "goods_description": {"type": ["string", "null"]},
                "hs_code": {"type": ["string", "null"]},
                "order_reference": {"type": ["string", "null"]},
                "documents_required": {"type": "array", "items": {"type": "string"}},
                "special_conditions": {"type": "array", "items": {"type": "string"}},
                "charges": {"type": ["string", "null"]},
                "reimbursement_instructions": {"type": ["string", "null"]}
            },
            "required": [
                "applicant", "beneficiary", "currency", "amount", "issue_date", "expiry_date",
                "expiry_place", "available_with_bank", "advising_bank", "latest_shipment_date",
                "port_of_loading", "port_of_destination", "incoterm", "goods_description",
                "hs_code", "order_reference", "documents_required", "special_conditions",
                "charges", "reimbursement_instructions"
            ],
            "additionalProperties": False
        }
    }
}

VALIDATION_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "mt700_validation",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "is_valid": {"type": "boolean"},
                "score": {"type": "integer"},
                "issues": {"type": "array", "items": {"type": "string"}},
                "warnings": {"type": "array", "items": {"type": "string"}},
                "field_checks": {
                    "type": "object",
                    "properties": {
                        "swift_structure": {"type": "boolean"},
                        "field_31d_date_place": {"type": "boolean"},
                        "field_41a_valid": {"type": "boolean"},
                        "field_57a_valid": {"type": "boolean"},
                        "field_41a_57a_not_swapped": {"type": "boolean"},
                        "field_45a_complete": {"type": "boolean"},
                        "field_46a_complete": {"type": "boolean"},
                        "field_78_complete": {"type": "boolean"},
                        "field_71d_consistent": {"type": "boolean"},
                        "no_placeholders": {"type": "boolean"}
                    },
                    "required": [
                        "swift_structure", "field_31d_date_place", "field_41a_valid", "field_57a_valid",
                        "field_41a_57a_not_swapped", "field_45a_complete", "field_46a_complete",
                        "field_78_complete", "field_71d_consistent", "no_placeholders"
                    ],
                    "additionalProperties": False
                }
            },
            "required": ["is_valid", "score", "issues", "warnings", "field_checks"],
            "additionalProperties": False
        }
    }
}

MANDATORY_FIELDS = [
    "27", "20", "40A", "40E", "31C", "31D", "50", "59", "32B", "39A", "41A", "42C",
    "43P", "43T", "44E", "44F", "44C", "45A", "46A", "47A", "48", "49", "57A", "71D", "78", "72Z"
]

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

def call_llm_text(system_prompt: str, user_text: str, max_tokens: int = 1800) -> str:
    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text}
        ],
        max_tokens=max_tokens,
        temperature=0.1
    )
    return response.choices[0].message.content or ""

def call_llm_json(system_prompt: str, user_text: str, schema: Dict = None, max_tokens: int = 1200) -> Dict:
    try:
        if schema:
            response = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_text}
                ],
                response_format=schema,
                max_tokens=max_tokens,
                temperature=0.1
            )
            return safe_json_load(response.choices[0].message.content or "{}")
    except Exception:
        pass

    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": system_prompt + "\nReturn ONLY valid JSON."},
                {"role": "user", "content": user_text}
            ],
            response_format={"type": "json_object"},
            max_tokens=max_tokens,
            temperature=0.1
        )
        return safe_json_load(response.choices[0].message.content or "{}")
    except Exception:
        pass

    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": system_prompt + "\nReturn ONLY valid JSON. No markdown. No explanation."},
            {"role": "user", "content": user_text}
        ],
        max_tokens=max_tokens,
        temperature=0.1
    )
    return safe_json_load(response.choices[0].message.content or "{}")

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

def extract_text(uploaded_file):
    name = uploaded_file.name.lower()
    data = uploaded_file.getvalue()

    if name.endswith(".pdf"):
        text = ""
        if pdfplumber:
            try:
                with pdfplumber.open(BytesIO(data)) as pdf:
                    text = "\n".join(page.extract_text() or "" for page in pdf.pages)
            except Exception:
                text = ""
        if not text and PdfReader:
            try:
                reader = PdfReader(BytesIO(data))
                text = "\n".join(page.extract_text() or "" for page in reader.pages)
            except Exception:
                text = ""
        return text

    if name.endswith(".docx"):
        if docx:
            try:
                d = docx.Document(BytesIO(data))
                return "\n".join(p.text for p in d.paragraphs)
            except Exception:
                return ""
        return ""

    if name.endswith(".doc"):
        return extract_doc_legacy(data)

    try:
        return data.decode("utf-8", errors="ignore")
    except Exception:
        return ""

def clean_text(text: str) -> str:
    text = "".join(c for c in text if c.isprintable() or c in "\n\t")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text[:22000]

def parse_mt700_fields(mt700: str) -> Dict[str, str]:
    if not mt700:
        return {}
    pattern = re.compile(r"(?ms)^:([0-9]{2}[A-Z]?):(.*?)(?=^:[0-9]{2}[A-Z]?:|^-}\s*$|\Z)")
    return {tag: value.strip() for tag, value in pattern.findall(mt700)}

def has_swift_blocks(mt700: str) -> bool:
    return ("{1:" in mt700) and ("{2:" in mt700) and ("{4:" in mt700) and ("-}" in mt700)

def looks_like_bic(value: str) -> bool:
    value = (value or "").strip().replace(" ", "")
    return bool(re.fullmatch(r"[A-Z0-9]{8}([A-Z0-9]{3})?", value))

def local_validate(mt700: str) -> Dict:
    fields = parse_mt700_fields(mt700)
    issues: List[str] = []
    warnings: List[str] = []

    for f in MANDATORY_FIELDS:
        if f not in fields or not fields[f].strip():
            issues.append(f"Missing or empty field :{f}:")

    if not has_swift_blocks(mt700):
        issues.append("Invalid SWIFT block structure")

    d31d = fields.get("31D", "")
    if not re.search(r"\d{6}", d31d) or len(d31d.strip()) <= 6:
        issues.append(":31D: must include date and place")

    if fields.get("41A") and not looks_like_bic(fields.get("41A", "").splitlines()[0]):
        issues.append(":41A: does not appear to contain a valid BIC")

    if fields.get("57A") and not looks_like_bic(fields.get("57A", "").splitlines()[0]):
        warnings.append(":57A: first line does not appear to be a pure BIC")

    if fields.get("41A", "").splitlines()[:1] == fields.get("57A", "").splitlines()[:1] and fields.get("41A") and fields.get("57A"):
        warnings.append(":41A: and :57A: are identical, review routing logic")

    if any(x in mt700.upper() for x in ["REFERENCE", "DOCUMENTS REQUIRED", "DATE PLACE", "BANKXXXX"]):
        issues.append("Placeholders detected in MT700")

    f78 = fields.get("78", "").upper()
    if f78 and not any(x in f78 for x in ["REIMBURSE", "PRESENT", "DOCUMENT", "COURIER", "CLAIM"]):
        issues.append(":78: does not look operationally complete")

    f45 = fields.get("45A", "").upper()
    if f45 and "HS" not in f45:
        warnings.append(":45A: does not clearly include HS code")
    if f45 and "INCOTERM" not in f45 and not any(x in f45 for x in ["CIF", "FOB", "CFR", "EXW", "FCA", "DAP", "DDP", "CIP", "CPT"]):
        warnings.append(":45A: does not clearly include incoterm")

    f46 = fields.get("46A", "").upper()
    if f46 and not any(x in f46 for x in ["INVOICE", "BILL OF LADING", "PACKING", "INSURANCE", "CERTIFICATE"]):
        issues.append(":46A: does not look like a banking documentary list")

    defective_fields = []
    if ":31D: must include date and place" in issues:
        defective_fields.append("31D")
    if ":41A: does not appear to contain a valid BIC" in issues or ":41A: and :57A: are identical, review routing logic" in warnings:
        defective_fields.extend(["41A", "57A"])
    if any(":45A:" in x for x in warnings + issues):
        defective_fields.append("45A")
    if any(":46A:" in x for x in warnings + issues):
        defective_fields.append("46A")
    if any(":78:" in x for x in warnings + issues):
        defective_fields.append("78")

    score = 100 - min(50, len(issues) * 8) - min(20, len(warnings) * 3)
    score = max(score, 0)

    return {
        "is_valid": len(issues) == 0,
        "score": score,
        "issues": issues,
        "warnings": warnings,
        "defective_fields": sorted(list(set(defective_fields))),
        "field_checks": {
            "swift_structure": has_swift_blocks(mt700),
            "field_31d_date_place": "31D" not in defective_fields,
            "field_41a_valid": looks_like_bic(fields.get("41A", "").splitlines()[0]) if fields.get("41A") else False,
            "field_57a_valid": bool(fields.get("57A", "").strip()),
            "field_41a_57a_not_swapped": not (fields.get("41A", "").splitlines()[:1] == fields.get("57A", "").splitlines()[:1] and fields.get("41A") and fields.get("57A")),
            "field_45a_complete": "45A" not in defective_fields,
            "field_46a_complete": "46A" not in defective_fields,
            "field_78_complete": "78" not in defective_fields,
            "field_71d_consistent": bool(fields.get("71D", "").strip()),
            "no_placeholders": not any(x in mt700.upper() for x in ["REFERENCE", "DOCUMENTS REQUIRED", "DATE PLACE", "BANKXXXX"])
        }
    }

def merge_validation(local_val: Dict, llm_val: Optional[Dict]) -> Dict:
    if not llm_val:
        return local_val
    issues = list(dict.fromkeys(local_val.get("issues", []) + llm_val.get("issues", [])))
    warnings = list(dict.fromkeys(local_val.get("warnings", []) + llm_val.get("warnings", [])))
    field_checks = local_val.get("field_checks", {}).copy()
    field_checks.update(llm_val.get("field_checks", {}))
    score = min(local_val.get("score", 0), llm_val.get("score", 0))
    defective_fields = list(local_val.get("defective_fields", []))
    for issue in issues + warnings:
        m = re.findall(r":([0-9]{2}[A-Z]?):", issue)
        defective_fields.extend(m)
    defective_fields = sorted(list(set(defective_fields)))
    return {
        "is_valid": local_val.get("is_valid", False) and llm_val.get("is_valid", False),
        "score": score,
        "issues": issues,
        "warnings": warnings,
        "defective_fields": defective_fields,
        "field_checks": field_checks
    }

def calculate_score(mt700: str, validation_obj: Dict) -> int:
    base = validation_obj.get("score", 0)
    text = (mt700 or "").upper()
    if not mt700.strip():
        return 0
    if ":78:" in text and "COURIER" in text:
        base += 3
    if ":31D:" in text and re.search(r":31D:\d{6}[A-Z ]+", text):
        base += 3
    return min(max(base, 0), 100)

def build_error_table(validation: Dict) -> List[Dict]:
    rows = []
    for issue in validation.get("issues", []):
        fields = re.findall(r":([0-9]{2}[A-Z]?):", issue)
        rows.append({"type": "ERROR", "field": ", ".join(fields) if fields else "-", "message": issue})
    for warning in validation.get("warnings", []):
        fields = re.findall(r":([0-9]{2}[A-Z]?):", warning)
        rows.append({"type": "WARNING", "field": ", ".join(fields) if fields else "-", "message": warning})
    return rows

def default_extraction() -> Dict:
    return {
        "applicant": None,
        "beneficiary": None,
        "currency": None,
        "amount": None,
        "issue_date": None,
        "expiry_date": None,
        "expiry_place": None,
        "available_with_bank": None,
        "advising_bank": None,
        "latest_shipment_date": None,
        "port_of_loading": None,
        "port_of_destination": None,
        "incoterm": None,
        "goods_description": None,
        "hs_code": None,
        "order_reference": None,
        "documents_required": [],
        "special_conditions": [],
        "charges": None,
        "reimbursement_instructions": None
    }

def render_extraction_summary(data: Dict):
    st.subheader("📌 Datos extraídos")
    col1, col2 = st.columns(2)
    with col1:
        st.write("**Applicant:**", data.get("applicant"))
        st.write("**Beneficiary:**", data.get("beneficiary"))
        st.write("**Currency / Amount:**", f"{data.get('currency')} {data.get('amount')}")
        st.write("**Issue date:**", data.get("issue_date"))
        st.write("**Expiry:**", f"{data.get('expiry_date')} / {data.get('expiry_place')}")
        st.write("**Available with bank:**", data.get("available_with_bank"))
        st.write("**Advising bank:**", data.get("advising_bank"))
    with col2:
        st.write("**Latest shipment date:**", data.get("latest_shipment_date"))
        st.write("**Port of loading:**", data.get("port_of_loading"))
        st.write("**Port of destination:**", data.get("port_of_destination"))
        st.write("**Incoterm:**", data.get("incoterm"))
        st.write("**HS code:**", data.get("hs_code"))
        st.write("**Order ref:**", data.get("order_reference"))

if st.button("🚀 Generar MT700"):
    if not files:
        st.warning("Sube documentos")
    else:
        extracted_docs = []
        for f in files:
            try:
                txt = clean_text(extract_text(f))
                extracted_docs.append(f"### {f.name}\n{txt}")
            except Exception as e:
                st.warning(f"Error leyendo {f.name}: {str(e)}")

        full_text = "\n\n".join(extracted_docs)
        st.write("📄 DEBUG TEXTO:", full_text[:1200])

        try:
            extraction = call_llm_json(EXTRACTION_PROMPT, full_text, EXTRACTION_SCHEMA, max_tokens=1200)
            if not extraction:
                extraction = default_extraction()
        except Exception as e:
            extraction = default_extraction()
            st.warning(f"Fallo en extracción estructurada: {str(e)}")

        try:
            mt700 = call_llm_text(GEN_PROMPT, full_text, max_tokens=1800)
        except Exception as e:
            mt700 = ""
            st.error(f"Fallo generando MT700: {str(e)}")

        local_val = local_validate(mt700)

        llm_val = None
        try:
            llm_val = call_llm_json(VAL_PROMPT, mt700, VALIDATION_SCHEMA, max_tokens=1000)
            if not llm_val:
                llm_val = None
        except Exception as e:
            st.warning(f"Fallo en validación LLM, se usa solo validación local: {str(e)}")

        validation = merge_validation(local_val, llm_val)

        if mt700 and (not validation.get("is_valid", False) or validation.get("score", 0) < 85):
            try:
                repair_input = (
                    "EXTRACTED DOCUMENTS:\n" + full_text[:14000] +
                    "\n\nMT700 DRAFT:\n" + mt700 +
                    "\n\nVALIDATION FINDINGS:\n" + json.dumps(validation, indent=2)
                )
                repaired = call_llm_text(CORRECTION_PROMPT, repair_input, max_tokens=1800)
                local_val_2 = local_validate(repaired)

                llm_val_2 = None
                try:
                    llm_val_2 = call_llm_json(VAL_PROMPT, repaired, VALIDATION_SCHEMA, max_tokens=1000)
                    if not llm_val_2:
                        llm_val_2 = None
                except Exception:
                    llm_val_2 = None

                validation_2 = merge_validation(local_val_2, llm_val_2)
                if validation_2.get("score", 0) >= validation.get("score", 0):
                    mt700 = repaired
                    validation = validation_2
            except Exception as e:
                st.warning(f"No se pudo reparar automáticamente el MT700: {str(e)}")

        st.session_state["source_text"] = full_text
        st.session_state["extraction"] = extraction
        st.session_state["mt700"] = mt700
        st.session_state["validation"] = validation
        st.session_state["score"] = calculate_score(mt700, validation)
        st.success("✅ Generado")

if "mt700" in st.session_state:
    render_extraction_summary(st.session_state["extraction"])
    st.divider()

    col1, col2 = st.columns([2, 1])
    with col1:
        edited_mt700 = st.text_area("📡 MT700", st.session_state["mt700"], height=520)
    with col2:
        st.metric("Confianza", f"{st.session_state['score']}%")
        if st.session_state["score"] >= 90:
            st.success("✅ Alto nivel")
        elif st.session_state["score"] >= 70:
            st.warning("⚠️ Revisar")
        else:
            st.error("❌ No emitir")
        st.json(st.session_state["validation"])

    parsed = parse_mt700_fields(edited_mt700)
    st.divider()
    st.subheader("🧩 Campos parseados")
    st.json(parsed)

    st.divider()
    st.subheader("📋 Errores por campo")
    rows = build_error_table(st.session_state["validation"])
    if rows:
        st.dataframe(rows, use_container_width=True)
    else:
        st.success("Sin errores ni warnings detectados")

    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("🛠️ Regenerar solo campos defectuosos"):
            defective = st.session_state["validation"].get("defective_fields", [])
            if not defective:
                st.info("No hay campos defectuosos detectados")
            else:
                try:
                    repair_input = (
                        "EXTRACTED DOCUMENTS:\n" + st.session_state["source_text"][:14000] +
                        "\n\nCURRENT MT700:\n" + edited_mt700 +
                        "\n\nDEFECTIVE FIELDS:\n" + ", ".join(defective)
                    )
                    fixed = call_llm_text(FIELD_FIX_PROMPT, repair_input, max_tokens=1800)
                    local_val_3 = local_validate(fixed)

                    llm_val_3 = None
                    try:
                        llm_val_3 = call_llm_json(VAL_PROMPT, fixed, VALIDATION_SCHEMA, max_tokens=1000)
                        if not llm_val_3:
                            llm_val_3 = None
                    except Exception:
                        llm_val_3 = None

                    validation_3 = merge_validation(local_val_3, llm_val_3)
                    st.session_state["mt700"] = fixed
                    st.session_state["validation"] = validation_3
                    st.session_state["score"] = calculate_score(fixed, validation_3)
                    st.rerun()
                except Exception as e:
                    st.error(f"Fallo regenerando campos defectuosos: {str(e)}")

    with col_b:
        if st.button("✅ Aprobar"):
            st.success("MT700 aprobado ✅")

    txt_data = edited_mt700.encode("utf-8")
    json_data = json.dumps({
        "extraction": st.session_state["extraction"],
        "validation": st.session_state["validation"],
        "parsed_fields": parsed,
        "score": st.session_state["score"]
    }, ensure_ascii=False, indent=2).encode("utf-8")

    d1, d2 = st.columns(2)
    with d1:
        st.download_button("⬇️ Descargar MT700 TXT", txt_data, file_name="MT700.txt", mime="text/plain")
    with d2:
        st.download_button("⬇️ Descargar validación JSON", json_data, file_name="MT700_validation.json", mime="application/json")
