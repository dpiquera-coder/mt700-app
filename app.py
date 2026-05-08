import streamlit as st
from groq import Groq

import pdfplumber
import fitz  # ✅ PyMuPDF (CLAVE!!)
import io
import re
import requests
import base64
from PIL import Image, ImageEnhance
from docx import Document

# ==============================
# CONFIG
# ==============================
client = Groq(api_key=st.secrets["GROQ_API_KEY"])

st.set_page_config(page_title="MT700 Generator", layout="wide")
st.title("📡 MT700 Generator (OCR REAL + Word + Bank Mode)")

files = st.file_uploader("Sube documentos", accept_multiple_files=True)

# ==============================
# OCR CLOUD
# ==============================
def ocr_image(image_bytes):
    try:
        api_key = st.secrets["OCR_API_KEY"]

        img_base64 = base64.b64encode(image_bytes).decode()

        url = f"https://vision.googleapis.com/v1/images:annotate?key={api_key}"

        body = {
            "requests": [{
                "image": {"content": img_base64},
                "features": [{"type": "TEXT_DETECTION"}]
            }]
        }

        response = requests.post(url, json=body).json()

        text = response["responses"][0].get("fullTextAnnotation", {}).get("text", "")

        return text

    except:
        return ""

# ==============================
# NUEVO OCR CON PYMuPDF (CLAVE)
# ==============================
def extract_pdf_with_ocr(file):

    text = ""

    try:
        pdf_bytes = file.read()

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")

        for page in doc:

            # ✅ render alta calidad (CLAVE)
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))

            img_bytes = pix.tobytes("png")

            ocr_text = ocr_image(img_bytes)

            # ✅ limpiar basura OCR
            ocr_text = re.sub(r"[^\x20-\x7E]+", " ", ocr_text)

            text += ocr_text + "\n"

    except Exception as e:
        return ""

    return text


# ==============================
# EXTRACT TEXT SMART
# ==============================
def extract_text(file):

    text = ""
    filename = file.name.lower()

    try:
        if filename.endswith(".pdf"):

            pdf_bytes = file.read()

            pdf_text = ""

            # ✅ intento texto estructurado
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                for page in pdf.pages:
                    t = page.extract_text()
                    if t:
                        pdf_text += t + "\n"

            # ✅ fallback OCR REAL
            if len(pdf_text.strip()) < 50:

                st.warning(f"⚠️ OCR AVANZADO activado para {file.name}")

                file.seek(0)
                pdf_text = extract_pdf_with_ocr(file)

            text += pdf_text

        elif filename.endswith(".docx"):

            doc = Document(file)
            for p in doc.paragraphs:
                text += p.text + "\n"

        else:
            text += file.read().decode("utf-8", errors="ignore")

    except Exception as e:
        st.warning(f"Error leyendo {file.name}")

    return text


# ==============================
# PROMPTS
# ==============================
EXTRACT_PROMPT = """
Extract structured trade finance data.

Return JSON:

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
Generate VALID SWIFT MT700.

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

:78:UPON RECEIPT OF COMPLYING DOCUMENTS

:72Z:WITHOUT CONFIRMATION
-}

RULES:
- DO NOT INVENT DATA
- Missing → NOT PROVIDED
- Each field one line
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
            t = extract_text(f)
            full_text += t + "\n\n"

        # limpieza final
        full_text = re.sub(r"\s+", " ", full_text)
        full_text = full_text[:12000]

        st.subheader("📄 TEXTO EXTRAÍDO (REAL)")
        st.text_area("Preview", full_text[:1500], height=200)

        if len(full_text.strip()) < 50:
            st.error("❌ No se pudo extraer texto válido")
            st.stop()

        # STEP 1 JSON
        json_data = call_llm(EXTRACT_PROMPT, full_text)

        st.subheader("📊 JSON")
        st.text_area("Datos", json_data, height=200)

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

    st.download_button("⬇️ Descargar", mt, "MT700.txt")
