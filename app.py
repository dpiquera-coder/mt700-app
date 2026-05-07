import streamlit as st
import requests

st.title("MT700 Generator")

files = st.file_uploader("Sube documentos", accept_multiple_files=True)

GEN_PROMPT = "Genera un MT700 completo en formato SWIFT sin explicaciones"
VAL_PROMPT = "Valida el MT700 detectando errores y di OK o ERROR"


def call_llm(prompt, text):
    API_URL = "https://api-inference.huggingface.co/models/mistralai/Mistral-7B-Instruct-v0.2"

    try:
        response = requests.post(
            API_URL,
            json={"inputs": prompt + "\n\n" + text},
            timeout=30
        )

        if response.status_code != 200:
            return f"Error API: {response.status_code} - {response.text}"

        result = response.json()

        if isinstance(result, list):
            return result[0].get("generated_text", "Sin respuesta")
        else:
            return str(result)

    except Exception as e:
        return f"Error: {str(e)}"


# ✅ BOTÓN
if st.button("🚀 Generar MT700"):

    st.write("✅ Botón pulsado")   # 👈 DEBUG visual

    if not files:
        st.warning("Sube archivos")
    else:
        text = ""

        for f in files:
            content = f.read().decode(errors="ignore")
            content = content[:3000]
            text += content + "\n\n"

        st.write("📄 Texto procesado")  # 👈 DEBUG

        mt700 = call_llm(GEN_PROMPT, text)
        validation = call_llm(VAL_PROMPT, mt700)

        st.session_state["mt700"] = mt700
        st.session_state["validation"] = validation

        st.success("✅ Generado correctamente")


# ✅ RESULTADOS
if "mt700" in st.session_state:
    st.subheader("Resultado")

