import streamlit as st
from groq import Groq

# ✅ CONFIGURACIÓN
client = Groq(api_key=st.secrets["GROQ_API_KEY"])

st.title("📡 MT700 Generator")

files = st.file_uploader("Sube documentos", accept_multiple_files=True)

# ✅ PROMPTS
GEN_PROMPT = """
You are a senior trade finance expert.

Generate a SWIFT MT700 message using the provided text.

Even if the data is incomplete, ALWAYS generate.

Use format:

:20: REFERENCE
:50: APPLICANT
:59: BENEFICIARY
:32B: AMOUNT
:31C: DATE
:31D: EXPIRY
:45A: GOODS

DO NOT RETURN EMPTY.
"""

VAL_PROMPT = """
Check if MT700 contains required fields:
:20, :50, :59, :32B, :45A

Return:
OK or ERROR with reason.
"""

# ✅ FUNCIÓN LLM
def call_llm(prompt, text):
    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
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


# ✅ BOTÓN PRINCIPAL
if st.button("🚀 Generar MT700"):

    st.write("✅ Botón pulsado")

    if not files:
        st.warning("Sube archivos")

    else:
        text = ""

        for f in files:
            try:
                content = f.read().decode("utf-8", errors="ignore")

                # limpiar basura
                content = "".join(c for c in content if c.isprintable())

                # limitar tamaño
                content = content[:4000]

                text += content + "\n\n"

            except Exception as e:
                st.warning(f"Error leyendo {f.name}: {str(e)}")

        # ✅ DEBUG TEXTO
        st.write("📄 DEBUG TEXTO:", text[:500])

        # ✅ GENERACIÓN
        mt700 = call_llm(GEN_PROMPT, text)
        validation = call_llm(VAL_PROMPT, mt700)

        # ✅ DEBUG RESULTADOS
        st.write("DEBUG MT700:", mt700)
        st.write("DEBUG VALIDATION:", validation)

        # ✅ FALLBACK
        if not mt700 or mt700.strip() == "":
            mt700 = "⚠️ No se pudo generar MT700"

        if not validation:
            validation = "Sin validación"

        # ✅ GUARDAR ESTADO
        st.session_state["mt700"] = mt700
        st.session_state["validation"] = validation

        st.success("✅ Generado correctamente")


# ✅ MOSTRAR RESULTADOS
if "mt700" in st.session_state:

    st.subheader("📡 MT700 generado")

    edited_mt700 = st.text_area(
        "Resultado",
        value=st.session_state["mt700"],
        height=350
    )

    st.subheader("🔍 Validación")

    st.text_area(
        "Resultado validación",
        value=st.session_state["validation"],
        height=150
    )

    # ✅ BOTÓN APROBAR
    if st.button("✅ Aprobar"):
        st.success("MT700 aprobado ✅")

    # ✅ DESCARGA
    st.download_button(
        "⬇️ Descargar MT700",
        edited_mt700,
        file_name="MT700.txt"
    )
