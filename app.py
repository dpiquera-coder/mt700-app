import streamlit as st
from groq import Groq

# ✅ IMPORTANTE: primero imports, luego cliente
client = Groq(api_key=st.secrets["GROQ_API_KEY"])

st.title("MT700 Generator")

files = st.file_uploader("Sube documentos", accept_multiple_files=True)

# ✅ PROMPTS MEJORADOS (CRÍTICO)
GEN_PROMPT = """
You are a senior trade finance expert.

You MUST generate a SWIFT MT700.

Even if data is incomplete, ALWAYS generate the message.

Format:

:20: REF123
:50: APPLICANT
:59: BENEFICIARY
:32B: USD1000
:45A: GOODS

NEVER return empty.
"""

VAL_PROMPT = "Check if MT700 has fields. Return OK or ERROR."



def call_llm(prompt, text):
    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",   # ✅ MODELO ACTUAL
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": text}
            ],
            max_tokens=800
        )

        content = response.choices[0].message.content

        if not content or content.strip() == "":
            return "⚠️ El modelo no devolvió contenido"

        return content

    except Exception as e:
        return f"Error: {str(e)}"



# ✅ BOTÓN
if st.button("🚀 Generar MT700"):

    st.write("✅ Botón pulsado")

    if not files:
        st.warning("Sube archivos")
    else:
        text = ""

        for f in files:
            content = f.read().decode(errors="ignore")
            content = content[:4000]  # ✅ límite mejorado
            text += content + "\n\n"

        st.write("📄 Texto procesado")

        # ✅ GENERACIÓN
        mt700 = call_llm(GEN_PROMPT, text)
        validation = call_llm(VAL_PROMPT, mt700)

        # ✅ DEBUG CLAVE (VER QUÉ DEVUELVE)
        st.write("DEBUG MT700:", mt700)
        st.write("DEBUG VALIDATION:", validation)

        # ✅ FALLBACKS
        if not mt700 or mt700.strip() == "":
            mt700 = "⚠️ No se pudo generar MT700"

        if not validation:
            validation = "Sin validación"

        st.session_state["mt700"] = mt700
        st.session_state["validation"] = validation

        st.success("✅ Generado correctamente")


# ✅ RESULTADOS (CORREGIDO)
if "mt700" in st.session_state:

    st.subheader("📡 Resultado")

    edited_mt700 = st.text_area(
        "MT700 generado",
        value=st.session_state["mt700"],
        height=350
    )

    st.subheader("🔍 Validación")

    st.text_area(
        "Resultado validación",
        value=st.session_state["validation"],
        height=150
    )

    if st.button("✅ Aprobar"):
        st.success("MT700 aprobado ✅")

    st.download_button(
        "⬇️ Descargar MT700",
        edited_mt700,
        file_name="MT700.txt"
    )
