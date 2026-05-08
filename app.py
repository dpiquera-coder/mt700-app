import streamlit as st
from groq import Groq

# ==============================
# CONFIG
# ==============================
client = Groq(api_key=st.secrets["GROQ_API_KEY"])

st.set_page_config(page_title="MT700 Generator", layout="wide")
st.title("📡 MT700 Generator - Trade Finance")

files = st.file_uploader("Sube documentos", accept_multiple_files=True)

# ==============================
# PROMPTS NIVEL BANCO
# ==============================
GEN_PROMPT = """
You are a senior Trade Finance officer.

Generate a COMPLETE SWIFT MT700.

STRICT FORMAT:

{1:F01BANKXXXX0000000000}
{2:I700BANKXXXXN}
{4:
:27:1/1
:20:REFERENCE
:40A:IRREVOCABLE
:31C:DATE
:31D:DATE PLACE

:50:APPLICANT
:59:BENEFICIARY

:32B:USD AMOUNT

:41A:BANK
BY PAYMENT
:42C:AT SIGHT

:43P:ALLOWED
:43T:ALLOWED

:44E:PORT OF LOADING
:44F:PORT OF DESTINATION
:44C:DATE

:45A:GOODS DESCRIPTION + INCOTERM + HS CODE

:46A:DOCUMENTS REQUIRED

:47A:CONDITIONS

:48:21 DAYS AFTER SHIPMENT

:49:WITHOUT

:57A:ADVISING BANK

:71D:ALL CHARGES FOR BENEFICIARY

:78:REIMBURSEMENT INSTRUCTIONS

:72Z:WITHOUT CONFIRMATION
-}

RULES:
- NEVER return empty
- If missing data → infer realistic banking data
- Keep internal consistency
"""

VAL_PROMPT = """
You are a Trade Finance validator.

Check MT700:

Rules:
- Must include fields :20, :32B, :50, :59, :45A
- Must follow SWIFT structure
- Must be consistent

Return:

OK

or

ERROR:
- list issues
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
# SCORING
# ==============================
def calculate_score(mt700, validation):

    score = 100

    text = (mt700 + validation).lower()

    if "error" in text:
        score -= 40

    if "missing" in text:
        score -= 20

    if ":20" not in mt700:
        score -= 15
    if ":32b" not in mt700.lower():
        score -= 15
    if ":50" not in mt700:
        score -= 10
    if ":59" not in mt700:
        score -= 10

    return max(score, 0)


# ==============================
# BOTÓN GENERAR
# ==============================
if st.button("🚀 Generar MT700"):

    if not files:
        st.warning("Sube documentos")

    else:
        text = ""

        for f in files:
            try:
                content = f.read().decode("utf-8", errors="ignore")

                # limpiar caracteres
                content = "".join(c for c in content if c.isprintable())

                content = content[:4000]

                text += content + "\n\n"

            except Exception as e:
                st.warning(f"Error leyendo {f.name}")

        st.write("📄 DEBUG TEXTO:", text[:500])

        # GENERAR
        mt700 = call_llm(GEN_PROMPT, text)
        validation = call_llm(VAL_PROMPT, mt700)

        st.write("🔍 DEBUG MT700:", mt700[:500])

        score = calculate_score(mt700, validation)

        st.session_state["mt700"] = mt700
        st.session_state["validation"] = validation
        st.session_state["score"] = score

        st.success("✅ Generado")


# ==============================
# RESULTADOS
# ==============================
if "mt700" in st.session_state:

    col1, col2 = st.columns([2, 1])

    with col1:
        edited_mt700 = st.text_area(
            "📡 MT700",
            st.session_state["mt700"],
            height=400
        )

    with col2:
        st.metric("Confianza", str(st.session_state["score"]) + "%")

        if st.session_state["score"] >= 90:
            st.success("✅ Alto nivel")
        elif st.session_state["score"] >= 70:
            st.warning("⚠️ Revisar")
        else:
            st.error("❌ No emitir")

        st.text_area("Validación", st.session_state["validation"], height=200)

    st.divider()

    if st.button("✅ Aprobar"):
        st.success("MT700 aprobado ✅")

    st.download_button(
        "⬇️ Descargar MT700",
        edited_mt700,
        file_name="MT700.txt"
    )
