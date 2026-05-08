import streamlit as st
from groq import Groq

import pdfplumber
import io
import re
import requests
import base64
from PIL import Image
from docx import Document

# ==============================
# CONFIG
# ==============================
client = Groq(api_key=st.secrets["GROQ_API_KEY"])

st.set_page_config(page_title="MT700 Generator", layout="wide")
st.title("📡 MT700 Generator (PDF + OCR Cloud + Word)")

files = st.file_uploader("Sube documentos", accept_multiple_files=True)

# ==============================
# OCR CLOUD (Google Vision API)
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

    except Exception as e:
        return ""

# ==============================
# EXTRAER TEXTO (SMART)
# ==============================
def extract_text(file):

    text = ""
    filename = file.name.lower()

    try:
        # ======================
        # PDF
        # ======================
        if filename.endswith(".pdf"):

            pdf_bytes = file.read()

            pdf_text = ""

            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                for page in pdf.pages:
                    t = page.extract_text()
                    if t:
                        pdf_text += t + "\n"

            # 👉 si no hay texto → usar OCR cloud
            if len(pdf_text.strip()) < 50:

                st.warning(f"⚠️ OCR aplicado a {file.name}")

                with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                    for page in pdf.pages:
                        im = page.to_image().original

                        buf = io.BytesIO()
                        im.save(buf, format="PNG")

                        ocr_text = ocr_image(buf.getvalue())
                        pdf_text += ocr_text + "\n"

            text += pdf_text

        # ======================
        # DOCX
        # ======================
        elif filename.endswith(".docx"):

            doc = Document(file)
            for p in doc.paragraphs:
                text += p.text + "\n"

        # ======================
        # TEXTO
        # ======================
        else:
            content = file.read().decode("utf-8", errors="ignore")
            text += content

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

RULES:
- Do NOT invent data
- Missing → null
"""

GEN_PROMPT = """
Generate SWIFT MT700.

STRICT FORMAT:

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

RULES:
- No hallucinations
- Missing → NOT PROVIDED
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

    if "missing" in v:
        s -= 15

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

        # limpiar
        full_text = re.sub(r"\s+", " ", full_text)
        full_text = full_text[:12000]

        st.subheader("📄 Texto extraído")
        st.text_area("Preview", full_text[:1500], height=200)

        if len(full_text.strip()) < 50:
            st.error("❌ No se pudo extraer texto")
            st.stop()

        # STEP 1
        json_data = call_llm(EXTRACT_PROMPT, full_text)

        st.subheader("📊 JSON")
        st.text_area("Datos", json_data, height=200)

        # STEP 2
        mt700 = call_llm(GEN_PROMPT, json_data)

        # STEP 3
        validation = call_llm(VAL_PROMPT, mt700)

        sc = score(validation)

        st.session_state["mt700"] = mt700
        st.session_state["validation"] = validation
        st.session_state["score"] = sc

        st.success("✅ Generado")

# ==============================
# RESULTADO
# ==============================
if "mt700" in st.session_state:

    col1, col2 = st.columns([2, 1])

    with col1:
        mt = st.text_area("MT700", st.session_state["mt700"], height=400)

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
