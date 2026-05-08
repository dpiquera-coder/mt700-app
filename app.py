import streamlit as st
from groq import Groq
import json

# ==============================
# CONFIG
# ==============================
client = Groq(api_key=st.secrets["GROQ_API_KEY"])

st.set_page_config(page_title="MT700 Generator", layout="wide")
st.title("📡 MT700 Generator - Structured Trade Finance")

files = st.file_uploader("Sube documentos", accept_multiple_files=True)

# ==============================
# PROMPT 1: EXTRACCIÓN
# ==============================
EXTRACT_PROMPT = """
Extract structured trade finance data from the text.

Return JSON format ONLY:

{
  "applicant": "",
  "beneficiary": "",
  "amount": "",
  "currency": "",
  "issue_date": "",
  "expiry_date": "",
  "shipment_date": "",
  "goods": "",
  "incoterm": "",
  "ports": ""
}

RULES:
- Do NOT invent data
- If missing → null
- Extract only what is explicitly present
"""

# ==============================
# PROMPT 2: GENERACIÓN
# ==============================
GEN_PROMPT = """
You are a Trade Finance officer.

Generate a SWIFT MT700 from the provided JSON.

RULES:
- Do NOT invent data
- If missing → write NOT PROVIDED
- Keep consistency

FORMAT STRICT:

{4:
:20:
:40A:IRREVOCABLE
:31C:
:31D:
:50:
:59:
:32B:
:41A:
:42C:AT SIGHT
:43P:
:43T:
:44E:
:44F:
:44C:
:45A:
:46A:
:47A:
:48:
:49:
:57A:
:71D:
:78:
:72Z:
-}

OUTPUT ONLY MT700.
"""

# ==============================
# VALIDACIÓN
# ==============================
VAL_PROMPT = """
You are a Trade Finance auditor.

Analyze the MT700.

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
            max_tokens=1000
        )

        return response.choices[0].message.content

    except Exception as e:
        return f"Error: {str(e)}"

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
        score -= 20

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
                content = f.read().decode("utf-8", errors="ignore")

                # limpiar basura
                content = "".join(c for c in content if c.isprintable())

                content = content[:4000]

                text += content + "\n\n"

            except:
                st.warning(f"No se pudo leer {f.name}")

        st.write("📄 DEBUG INPUT:", text[:500])

        # ======================
        # STEP 1 - EXTRACCIÓN
        # ======================
        extracted = call_llm(EXTRACT_PROMPT, text)

        st.subheader("📊 Datos extraídos (JSON)")
        st.write(extracted)

        # ======================
        # STEP 2 - GENERACIÓN
        # ======================
        mt700 = call_llm(GEN_PROMPT, extracted)

        # ======================
        # STEP 3 - VALIDACIÓN
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
        st.metric("Confianza", str(st.session_state["score"]) + "%")

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
``
