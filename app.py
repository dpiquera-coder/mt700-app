import streamlit as st
from groq import Groq
import pdfplumber
import io
import re

# ==============================
# CONFIG
# ==============================
client = Groq(api_key=st.secrets["GROQ_API_KEY"])

st.set_page_config(page_title="MT700 Generator", layout="wide")
st.title("📡 MT700 Generator (PDF Real + No Hallucinations)")

files = st.file_uploader("Sube documentos", accept_multiple_files=True)

# ==============================
# PROMPT EXTRACCIÓN
# ==============================
EXTRACT_PROMPT = """
Extract structured trade finance data from the text.

Return JSON ONLY:

{
  "applicant": "",
  "beneficiary": "",
  "amount": "",
  "currency": "",
  "issue_date": "",
  "expiry_date": "",
  "shipment_date": "",
  "goods": "",
  "incoterm": ""
}

RULES:
- DO NOT INVENT DATA
- If missing → null
- Only extract real values
"""

# ==============================
# PROMPT GENERACIÓN (FORMATO SWIFT)
# ==============================
GEN_PROMPT = """
You are a Trade Finance officer.

Generate a VALID SWIFT MT700.

RULES:
- DO NOT INVENT DATA
- If missing → NOT PROVIDED
- Each field MUST be on its own line

FORMAT:

{4:
:27:1/1
:20:
:40A:IRREVOCABLE
:31C:
:31D:

:50:
:59:

:32B:

:41A:
BY PAYMENT
:42C:AT SIGHT

:43P:ALLOWED
:43T:ALLOWED

:44E:
:44F:
:44C:

:45A:

:46A:

:47A:

:48:21 DAYS AFTER SHIPMENT DATE

:49:WITHOUT

:57A:

:71D:ALL CHARGES OUTSIDE COUNTRY FOR BENEFICIARY

:78:
UPON RECEIPT OF COMPLYING DOCUMENTS

:72Z:WITHOUT CONFIRMATION
-}

OUTPUT ONLY MT700.
"""

# ==============================
# VALIDACIÓN
# ==============================
VAL_PROMPT = """
You are a Trade Finance auditor.

Analyze MT700.

Return:

RISK LEVEL: LOW / MEDIUM / HIGH

ISSUES:
- missing fields
- inconsistencies
- suspicious data
"""

# ==============================
# LLM CALL
# ==============================
def call_llm(prompt, text):
    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": text}
            ],
            max_tokens=1200
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"ERROR: {str(e)}"

# ==============================
# SCORE
# ==============================
def calculate_score(validation):

    score = 100
    val = validation.lower()

    if "high" in val:
        score -= 50
    elif "medium" in val:
        score -= 25

    if "missing" in val:
        score -= 15

    if "suspicious" in val:
        score -= 40

    return max(score, 0)

# ==============================
# GENERACIÓN
# ==============================
if st.button("🚀 Generar MT700"):

    if not files:
        st.warning("Sube documentos")

    else:
        text = ""

        for f in files:
            try:
                if f.name.lower().endswith(".pdf"):
                    with pdfplumber.open(io.BytesIO(f.read())) as pdf:
                        for page in pdf.pages:
                            page_text = page.extract_text()
                            if page_text:
                                text += page_text + "\n\n"
                else:
                    content = f.read().decode("utf-8", errors="ignore")
                    text += content + "\n\n"

            except Exception as e:
                st.warning(f"Error leyendo {f.name}")

        # ✅ LIMPIAR TEXTO
        text = re.sub(r"\s+", " ", text)
        text = text[:8000]

        st.subheader("📄 Texto extraído del PDF")
        st.text_area("Preview", text[:1000], height=200)

        # ======================
        # STEP 1: EXTRACCIÓN
        # ======================
        extracted = call_llm(EXTRACT_PROMPT, text)

        st.subheader("📊 Datos extraídos (JSON)")
        st.text_area("JSON", extracted, height=200)

        # ======================
        # STEP 2: MT700
        # ======================
        mt700 = call_llm(GEN_PROMPT, extracted)

        # ======================
        # STEP 3: VALIDACIÓN
        # ======================
        validation = call_llm(VAL_PROMPT, mt700)

        score = calculate_score(validation)

        st.session_state["mt700"] = mt700
        st.session_state["validation"] = validation
        st.session_state["score"] = score

        st.success("✅ Proceso completo generado")

# ==============================
# RESULTADOS
# ==============================
if "mt700" in st.session_state:

    col1, col2 = st.columns([2, 1])

    with col1:
        edited_mt700 = st.text_area(
            "📡 MT700 generado",
            st.session_state["mt700"],
            height=400
        )

    with col2:
        st.metric("Confianza", f"{st.session_state['score']}%")

        if st.session_state["score"] >= 90:
            st.success("✅ Bajo riesgo")
        elif st.session_state["score"] >= 70:
            st.warning("⚠️ Riesgo medio")
        else:
            st.error("❌ Alto riesgo")

        st.text_area("🔍 Validación", st.session_state["validation"], height=200)

    st.divider()

    if st.button("✅ Aprobar"):
        st.success("MT700 aprobado ✅")

    st.download_button(
        "⬇️ Descargar MT700",
        edited_mt700,
        file_name="MT700.txt"
    )
