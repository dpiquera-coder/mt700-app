import streamlit as st
from groq import Groq
import re

# ==============================
# CONFIG
# ==============================
client = Groq(api_key=st.secrets["GROQ_API_KEY"])

st.set_page_config(page_title="MT700 Generator", layout="wide")
st.title("📡 MT700 Generator (Smart Extraction Mode ✅)")

files = st.file_uploader("Sube documentos", accept_multiple_files=True)

# ==============================
# EXTRACCIÓN INTELIGENTE (CLAVE)
# ==============================
def extract_text(file):

    text = ""

    try:
        raw = file.read().decode("utf-8", errors="ignore")

        # ✅ limpiar caracteres basura
        clean = "".join(c for c in raw if c.isprintable())

        # ✅ eliminar ruido raro
        clean = re.sub(r"[^\w\s.,:/-]", " ", clean)

        # ✅ normalizar espacios
        clean = re.sub(r"\s+", " ", clean)

        # ✅ FILTRADO INTELIGENTE
        keywords = [
            "USD", "EUR", "SA", "SL", "LTD", "CO",
            "INVOICE", "DATE", "PORT", "SHIP",
            "BARCELONA", "CHINA", "EXPORT", "IMPORT",
            "TOTAL", "AMOUNT", "GOODS"
        ]

        filtered = []

        for sentence in clean.split("."):
            if any(k in sentence.upper() for k in keywords):
                filtered.append(sentence.strip())

        text = "\n".join(filtered)

    except:
        return ""

    return text


# ==============================
# PROMPTS
# ==============================
EXTRACT_PROMPT = """
Extract trade finance data.

Return JSON:

{
"applicant": "",
"beneficiary": "",
"amount": "",
"currency": "",
"goods": "",
"date": ""
}

Do NOT invent data.
"""

GEN_PROMPT = """
Generate SWIFT MT700.

Rules:
- Use only provided data
- Missing = NOT PROVIDED

Format:

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

:78:UPON RECEIPT OF COMPLYING DOCUMENTS

:72Z:WITHOUT CONFIRMATION
-}
"""

VAL_PROMPT = """
Validate MT700.

Return:

RISK LEVEL: LOW / MEDIUM / HIGH

ISSUES:
- missing
- inconsistent
"""

# ==============================
# LLM
# ==============================
def call_llm(prompt, text):

    try:
        r = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": text}
            ],
            max_tokens=1200
        )

        return r.choices[0].message.content

    except Exception as e:
        return f"ERROR: {str(e)}"


# ==============================
# SCORE
# ==============================
def score(validation):
    s = 100
    v = validation.lower()

    if "high" in v:
        s -= 50
    elif "medium" in v:
        s -= 25

    return max(s, 0)


# ==============================
# BOTÓN
# ==============================
if st.button("🚀 Generar MT700"):

    if not files:
        st.warning("Sube documentos")

    else:
        full_text = ""

        for f in files:
            extracted = extract_text(f)
            full_text += extracted + "\n\n"

        full_text = full_text[:5000]

        st.subheader("📄 TEXTO FILTRADO (CLAVE)")
        st.text_area("Preview", full_text, height=200)

        if len(full_text.strip()) < 20:
            st.error("❌ No se pudo extraer información útil")
            st.stop()

        # STEP 1 JSON
        json_data = call_llm(EXTRACT_PROMPT, full_text)

        st.subheader("📊 DATOS EXTRAÍDOS")
        st.text_area("JSON", json_data, height=200)

        # STEP 2 MT700
        mt700 = call_llm(GEN_PROMPT, json_data)

        # STEP 3 VALIDACIÓN
        validation = call_llm(VAL_PROMPT, mt700)

        sc = score(validation)

        st.session_state["mt700"] = mt700
        st.session_state["validation"] = validation
        st.session_state["score"] = sc

        st.success("✅ MT700 generado correctamente")


# ==============================
# RESULTADO
# ==============================
if "mt700" in st.session_state:

    col1, col2 = st.columns([2, 1])

    with col1:
        mt = st.text_area("📡 MT700", st.session_state["mt700"], height=400)

    with col2:
        st.metric("Confianza", f"{st.session_state['score']}%")

        if st.session_state["score"] >= 90:
            st.success("✅ Bajo riesgo")
        elif st.session_state["score"] >= 70:
            st.warning("⚠️ Riesgo medio")
        else:
            st.error("❌ Alto riesgo")

        st.text_area("Validación", st.session_state["validation"], height=200)

    st.download_button("⬇️ Descargar MT700", mt, "MT700.txt")
