import streamlit as st
from groq import Groq

import pdfplumber
import io
import re
import pytesseract
from PIL import Image
from docx import Document

# ==============================
# CONFIG
# ==============================
client = Groq(api_key=st.secrets["GROQ_API_KEY"])

st.set_page_config(page_title="MT700 Generator", layout="wide")
st.title("📡 MT700 Generator (PDF + OCR + Word)")

files = st.file_uploader("Sube documentos", accept_multiple_files=True)

# ==============================
# PROMPTS
# ==============================
EXTRACT_PROMPT = """
Extract structured trade finance data from text.

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

DO NOT INVENT DATA
"""

GEN_PROMPT = """
Generate SWIFT MT700.

RULES:
- No invent data
- Missing → NOT PROVIDED
- Strict SWIFT format

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
:71D:
:78:
:72Z:
-}
"""

VAL_PROMPT = """
Validate MT700.

Return:
RISK LEVEL: LOW / MEDIUM / HIGH

ISSUES:
- problems
"""

# ==============================
# LLM
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

    return max(score, 0)

# ==============================
# EXTRACT TEXT SMART
# ==============================
def extract_text_from_file(file):

    text = ""

    try:
        filename = file.name.lower()

        # ======================
        # PDF
        # ======================
        if filename.endswith(".pdf"):

            pdf_text = ""

            with pdfplumber.open(io.BytesIO(file.read())) as pdf:
                for page in pdf.pages:
                    t = page.extract_text()
                    if t:
                        pdf_text += t + "\n"

            # 👉 si no hay texto → OCR
            if len(pdf_text.strip()) < 50:

                st.warning(f"⚠️ OCR activado para {file.name}")

                file.seek(0)

                images = pdfplumber.open(io.BytesIO(file.read())).pages

                for page in images:
                    im = page.to_image().original
                    ocr_text = pytesseract.image_to_string(im)
                    pdf_text += ocr_text + "\n"

            text += pdf_text

        # ======================
        # WORD
        # ======================
        elif filename.endswith(".docx"):

            doc = Document(file)
            for para in doc.paragraphs:
                text += para.text + "\n"

        # ======================
        # TEXT / OTROS
        # ======================
        else:
            text += file.read().decode("utf-8", errors="ignore")

    except Exception as e:
        st.warning(f"Error leyendo {file.name}: {e}")

    return text


# ==============================
# BOTÓN
# ==============================
if st.button("🚀 Generar MT700"):

    if not files:
        st.warning("Sube documentos")

    else:
        text = ""

        for f in files:
            extracted = extract_text_from_file(f)
            text += extracted + "\n\n"

        # limpiar texto
        text = re.sub(r"\s+", " ", text)
        text = text[:10000]

        st.subheader("📄 Texto limpio")
        st.text_area("Preview", text[:1500], height=200)

        if len(text.strip()) < 50:
            st.error("❌ No se pudo extraer texto utilizable")
            st.stop()

        # ======================
        # EXTRACCION
        # ======================
        json_data = call_llm(EXTRACT_PROMPT, text)

        st.subheader("📊 JSON")
        st.text_area("Datos", json_data, height=200)

        # ======================
        # MT700
        # ======================
        mt700 = call_llm(GEN_PROMPT, json_data)

        # ======================
        # VALIDACION
        # ======================
        validation = call_llm(VAL_PROMPT, mt700)

        score = calculate_score(validation)

        st.session_state["mt700"] = mt700
        st.session_state["validation"] = validation
        st.session_state["score"] = score

        st.success("✅ Generado")

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
            st.success("✔ Bajo riesgo")
        elif st.session_state["score"] >= 70:
            st.warning("⚠ Riesgo medio")
        else:
            st.error("❌ Alto riesgo")

        st.text_area("🔍 Validación", st.session_state["validation"], height=200)

    st.download_button("⬇️ Descargar", mt, "MT700.txt")
