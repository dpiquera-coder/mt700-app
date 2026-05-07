import streamlit as st
import requests
import os



st.title("MT700 Generator")

files = st.file_uploader("Sube documentos", accept_multiple_files=True)

def call_llm(prompt, text):
    API_URL = "https://api-inference.huggingface.co/models/google/flan-t5-large"

    response = requests.post(
        API_URL,
        json={"inputs": prompt + "\n\n" + text}
    )

    result = response.json()

    if isinstance(result, list):
        return result[0]["generated_text"]
    else:
        return str(result)



GEN_PROMPT = "Genera un MT700 completo sin explicaciones"
VAL_PROMPT = "Valida el MT700, detecta errores y da OK o ERROR"

if st.button("Generar MT700"):
    if not files:
        st.warning("Sube archivos")
    else:
        text = ""
        for f in files:
            text += f.read().decode(errors="ignore")

        mt700 = call_llm(GEN_PROMPT, text)
        validation = call_llm(VAL_PROMPT, mt700)

        st.session_state.mt700 = mt700
        st.session_state.validation = validation

if "mt700" in st.session_state:
    mt = st.text_area("MT700", st.session_state.mt700, height=300)
    st.text_area("Validación", st.session_state.validation)

    if st.button("Aprobar"):
        st.success("Aprobado ✅")
