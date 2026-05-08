client = Groq(api_key=st.secrets["GROQ_API_KEY"])
import streamlit as st
from groq import Groq
st.title("MT700 Generator")

files = st.file_uploader("Sube documentos", accept_multiple_files=True)

GEN_PROMPT = "Genera un MT700 completo en formato SWIFT sin explicaciones"
VAL_PROMPT = "Valida el MT700 detectando errores y di OK o ERROR"


def call_llm(prompt, text):
    try:
        response = client.chat.completions.create(
            model="llama3-70b-8192",
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": text}
            ]
        )

        return response.choices[0].message.content

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

