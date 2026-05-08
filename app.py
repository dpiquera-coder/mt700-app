import streamlit as st
from groq import Groq

client = Groq(api_key=st.secrets["GROQ_API_KEY"])

st.title("MT700 Generator")

files = st.file_uploader("Sube documentos", accept_multiple_files=True)

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
            model="llama-3.1-8b-instant",
            messages=[
