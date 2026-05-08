import streamlit as st
from groq import Groq

# ==============================
# CONFIG
# ==============================
client = Groq(api_key=st.secrets["GROQ_API_KEY"])

st.set_page_config(page_title="MT700 Generator", layout="wide")
st.title("📡 MT700 Generator - Trade Finance (No Hallucinations Mode)")

files = st.file_uploader("Sube documentos", accept_multiple_files=True)

# ==============================
# PROMPT ANTI-ALUCINACIÓN
# ==============================
GEN_PROMPT = """
You are a Trade Finance officer.

Generate a SWIFT MT700 STRICTLY using ONLY the information present in the input text.

--------------------------------
CRITICAL RULES
--------------------------------
- DO NOT INVENT DATA
- DO NOT GUESS
- DO NOT ASSUME
- If data is missing → write: NOT PROVIDED
- NEVER create fake names, addresses, banks or amounts

--------------------------------
FORMAT
--------------------------------
{4:
:20:
:40A:IRREVOCABLE
:31C:
:31D:
:50:
:59:
:32B:
:41A:
:42C:AT SIGHT
:43P:
:43T:
:44E:
:44F:
:44C:
:45A:
:46A:
:47A:
:48:
:49:
:57A:
:71D:
:78:
:72Z:
-}

--------------------------------
OBJECTIVE
--------------------------------
Be accurate, not complete.
Better empty than wrong.

OUTPUT ONLY MT700.
"""

# ==============================
# VALIDACIÓN INTELIGENTE
# ==============================
VAL_PROMPT = """
You are a Trade Finance auditor.

Check the MT700.

Tasks:
1. Detect missing fields
2. Detect inconsistencies
3. Detect invented/suspicious data

Return:

RISK LEVEL:
LOW / MEDIUM / HIGH

ISSUES:
- list problems
"""

# ==============================
# LLM CALL
# ==============================
def call_llm(prompt, text):
    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": text}
            ],
            max_tokens=1000
        )

        content = response.choices[0].message.content

        if not content or content.strip() == "":
            return "⚠️ Empty response"

        return content

    except Exception as e:
        return f"Error: {str(e)}"


# ==============================
# SCORING REALISTA
# ==============================
def calculate_score(mt700, validation):

    score = 100
    val = validation.lower()

    if "high" in val:
        score -= 50
    elif "medium" in val:
        score -= 25

    if "missing" in val:
        score -= 20

    if "invented" in val or "suspicious" in val:
        score -= 40

    return max(score, 0)


# ==============================
# GENERACIÓN
# ==============================
if st.button("🚀 Generar MT700"):

    if not files:
        st.warning("Sube documentos")
    else:
        text = ""

        for f in files:
            try:
                content = f.read().decode("utf-8", errors="ignore")

                # limpiar caracteres basura
                content = "".join(c for c in content if c.isprintable())

                # limitar tamaño
                content = content[:4000]

                text += content + "\n\n"

            except:
                st.warning(f"No se pudo leer {f.name}")

        st.write("📄 DEBUG TEXTO:", text[:500])

        # GENERAR MT700
        mt700 = call_llm(GEN_PROMPT, text)

        # VALIDAR
        validation = call_llm(VAL_PROMPT, mt700)

        st.write("🔍 DEBUG MT700:", mt700[:500])

        score = calculate_score(mt700, validation)

        st.session_state["mt700"] = mt700
        st.session_state["validation"] = validation
        st.session_state["score"] = score

        st.success("✅ MT700 generado")


# ==============================
# RESULTADO
# ==============================
if "mt700" in st.session_state:

    col1, col2 = st.columns([2, 1])

    with col1:
        edited_mt700 = st.text_area(
            "📡 MT700",
            value=st.session_state["mt700"],
            height=400
        )

    with col2:
        st.metric("Confianza", f"{st.session_state['score']}%")

        if st.session_state["score"] >= 90:
            st.success("✅ Bajo riesgo")
        elif st.session_state["score"] >= 70:
            st.warning("⚠️ Riesgo medio")
        else:
            st.error("❌ Alto riesgo (NO EMITIR)")

        st.text_area("🔍 Validación", st.session_state["validation"], height=200)

    st.divider()

    if st.button("✅ Aprobar"):
        st.success("MT700 aprobado ✅")

    st.download_button(
        "⬇️ Descargar MT700",
        edited_mt700,
        file_name="MT700.txt"
    )
