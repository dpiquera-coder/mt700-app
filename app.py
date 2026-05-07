import streamlit as st
import requests

st.title("MT700 Generator")

files = st.file_uploader("Sube documentos", accept_multiple_files=True)

GEN_PROMPT = "Genera un MT700 completo en formato SWIFT sin explicaciones"
VAL_PROMPT = "Valida el MT700 detectando errores y di OK o ERROR"


def call_llm(prompt, text):
    API_URL = "https://api-inference.huggingface.co/models/google/flan-t5-large"

    try:
        response = requests.post(
            API_URL,
            json={"inputs": prompt + "\n\n" + text},
            timeout=30
        )

        if response.status_code != 200:
            return f"Error API: {response.status_code} - {response.text}"

        try:
            result = response.json()

            if isinstance(result, list):
                return result[0].get("generated_text", "Sin respuesta")
            else:
                return str(result)

        except:
            return "Error: respuesta no válida"

    except Exception as e:
        return f"Error conexión: {str(e)}"


# ✅ BOTÓN PRINCIPAL
if st.button("Generar MT700"):

    if not files:
        st.warning("Sube archivos")

    else:
        text = ""

        # ✅ LEER ARCHIVOS
