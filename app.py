import streamlit as st
import fitz  # PyMuPDF
import re
import json

st.set_page_config(page_title="MT700 PDF Page 1 Reader", layout="wide")
st.title("📄 MT700 - Lector PDF página 1")

uploaded = st.file_uploader("Sube un PDF", type=["pdf"])


def extract_first_page_text(pdf_bytes: bytes) -> str:
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        if doc.page_count == 0:
            return ""
        page = doc[0]
        text = page.get_text("text")
        return text.strip()
    except Exception:
        return ""


def extract_first_page_blocks(pdf_bytes: bytes) -> str:
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        if doc.page_count == 0:
            return ""
        page = doc[0]
        blocks = page.get_text("blocks")
        blocks = sorted(blocks, key=lambda b: (b[1], b[0]))
        text = "\n".join(block[4].strip() for block in blocks if str(block[4]).strip())
        return text.strip()
    except Exception:
        return ""


def clean_text(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


def extract_field(pattern, text, flags=re.IGNORECASE | re.DOTALL, group=1):
    m = re.search(pattern, text, flags)
    return m.group(group).strip() if m else None


def parse_page1_fields(text: str) -> dict:
    data = {
        "applicant": None,
        "beneficiary": None,
        "beneficiary_address": None,
        "advising_bank": None,
        "advising_bank_address": None,
        "swift": None,
        "account_no": None,
        "confirmation": None,
        "expiry_date": None,
        "expiry_place": None,
        "currency": None,
        "amount": None,
        "amount_words": None,
        "availability": None,
        "tenor": None,
        "documents_required": [],
        "goods_description": None,
        "hs_code": None,
        "incoterm": None,
        "port_of_loading": None,
        "port_of_destination": None,
        "latest_shipment_date": None,
        "partial_shipments": None,
        "transhipment": None,
        "presentation_days": None,
        "charges_outside_spain": None,
        "other_conditions": None,
    }

    applicant = extract_field(
        r"ORDENANTE:?\s*(.*?)\s*Muy señores nuestros:",
        text
    )
    if applicant:
        data["applicant"] = applicant.replace("\n", ", ")

    beneficiary_block = extract_field(
        r"Beneficiario\s*(.*?)\s*el cual deberá ser avisado a través",
        text
    )
    if beneficiary_block:
        lines = [x.strip() for x in beneficiary_block.split("\n") if x.strip()]
        if lines:
            data["beneficiary"] = lines[0]
        if len(lines) > 1:
            data["beneficiary_address"] = ", ".join(lines[1:])

    advising_bank_block = extract_field(
        r"BANCO DEL BENEFICIARIO\):\s*(.*?)\s*AÑADIENDO|BANCO DEL BENEFICIARIO\):\s*(.*?)\s*ACC/No\.",
        text
    )
    if advising_bank_block:
        lines = [x.strip() for x in advising_bank_block.split("\n") if x.strip()]
        if lines:
            data["advising_bank"] = lines[0]
        if len(lines) > 1:
            data["advising_bank_address"] = ", ".join(lines[1:])

    swift = extract_field(r"SWIFT\.?\s*[: ]\s*([A-Z0-9]{8,11})", text)
    if swift:
        data["swift"] = swift

    account_no = extract_field(r"ACC/No\.?\s*([A-Z0-9 ]+)", text)
    if account_no:
        data["account_no"] = account_no

    if re.search(r"SIN AÑADIR SU CONFIRMACIÓN", text, re.IGNORECASE):
        data["confirmation"] = "WITHOUT"
    elif re.search(r"AÑADIENDO.*SU CONFIRMACIÓN", text, re.IGNORECASE):
        data["confirmation"] = "MAY ADD"

    expiry_date = extract_field(r"Lugar y fecha de vencimiento\s*:?\s*([0-9]{2}/[0-9]{2}/[0-9]{4})", text)
    if expiry_date:
        data["expiry_date"] = expiry_date
    data["expiry_place"] = "SPAIN"

    curr_amt = re.search(r"Divisa e importe\s*:?\s*([\d\.,]+)\s*([A-Z]{3})|Divisa e importe\s*:?\s*([A-Z]{3})\s*([\d\.,]+)", text, re.IGNORECASE)
    if curr_amt:
        if curr_amt.group(1) and curr_amt.group(2):
            data["amount"] = curr_amt.group(1).strip()
            data["currency"] = curr_amt.group(2).strip().upper()
        elif curr_amt.group(3) and curr_amt.group(4):
            data["currency"] = curr_amt.group(3).strip().upper()
            data["amount"] = curr_amt.group(4).strip()

    amount_words = extract_field(r"\(en letra\)\s*(.*?)\s*Crédito utilizable", text)
    if amount_words:
        data["amount_words"] = amount_words.replace("\n", " ")

    if re.search(r"Para\s*X\s*PAGO", text, re.IGNORECASE):
        data["availability"] = "BY PAYMENT"
    elif re.search(r"ACEPTACION", text, re.IGNORECASE):
        data["availability"] = "BY ACCEPTANCE"
    elif re.search(r"NEGOCIACION", text, re.IGNORECASE):
        data["availability"] = "BY NEGOTIATION"

    tenor = extract_field(r"a:\s*(LA VISTA|[^\n]+)", text)
    if tenor:
        data["tenor"] = tenor

    docs_block = extract_field(
        r"Contra la presentación de los siguientes documentos:\s*(.*?)\s*Cubriendo el embarque de",
        text
    )
    if docs_block:
        lines = [x.strip(" -\n\r\t") for x in docs_block.split("\n") if x.strip()]
        cleaned_docs = []
        for line in lines:
            if any(k in line.upper() for k in [
                "FACTURA", "BILL OF LADING", "AIR WAYBILL", "CMR", "CIM",
                "PÓLIZA", "POLIZA", "SEGURO", "CERTIFICADO", "PACKING LIST", "FORM"
            ]):
                cleaned_docs.append(line)
        data["documents_required"] = cleaned_docs

    goods_block = extract_field(
        r"Cubriendo el embarque de \(Mercancías\)\s*:?\s*(.*?)\s*Cond\. de Entrega",
        text
    )
    if goods_block:
        data["goods_description"] = goods_block.replace("\n", " ")

    hs_code = extract_field(r"Partida arancelaria\s*:?\s*([0-9]{6,10})", text)
    if hs_code:
        data["hs_code"] = hs_code

    incoterm = extract_field(r"Cond\. de Entrega \(Incoterms\)\s*:?\s*([A-Z]{3}\s*\(?[A-Z]*\)?)", text)
    if incoterm:
        data["incoterm"] = incoterm

    pol = extract_field(r"Embarque:\s*desde\s*(.*?)\s*Con destino a:", text)
    if pol:
        data["port_of_loading"] = pol.replace("\n", " ")

    pod = extract_field(r"Con destino a:\s*(.*?)\s*No más tarde del", text)
    if pod:
        data["port_of_destination"] = pod.replace("\n", " ")

    latest_shipment = extract_field(r"No más tarde del\s*:?\s*([0-9]{2}/[0-9]{2}/[0-9]{4})", text)
    if latest_shipment:
        data["latest_shipment_date"] = latest_shipment

    if re.search(r"Expediciones parciales:\s*X\s*AUTORIZADAS", text, re.IGNORECASE):
        data["partial_shipments"] = "ALLOWED"
    elif re.search(r"Expediciones parciales:.*PROHIBIDAS", text, re.IGNORECASE):
        data["partial_shipments"] = "NOT ALLOWED"

    if re.search(r"TRANSBORDOS\s*PERMITIDOS", text, re.IGNORECASE):
        data["transhipment"] = "ALLOWED"
    elif re.search(r"TRANSBORDOS.*PROHIBIDAS", text, re.IGNORECASE):
        data["transhipment"] = "NOT ALLOWED"

    presentation_days = extract_field(r"Documentos a presentar dentro de los\s*([0-9]+)\s*d[ií]as", text)
    if presentation_days:
        data["presentation_days"] = presentation_days

    if re.search(r"Los gastos bancarios fuera de España son por cuenta de\s*X\s*Beneficiario", text, re.IGNORECASE):
        data["charges_outside_spain"] = "BENEFICIARY"
    elif re.search(r"Los gastos bancarios fuera de España son por cuenta de.*Ordenante", text, re.IGNORECASE):
        data["charges_outside_spain"] = "APPLICANT"

    other_conditions = extract_field(r"Otras condiciones\s*:?\s*(.*?)\s*El presente crédito queda sujeto", text)
    if other_conditions:
        data["other_conditions"] = other_conditions.replace("\n", " ")

    return data


def to_swift_date(ddmmyyyy: str):
    if not ddmmyyyy:
        return None
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", ddmmyyyy)
    if not m:
        return None
    dd, mm, yyyy = m.groups()
    return yyyy[2:] + mm + dd


def build_mt700(fields: dict) -> str:
    issue_date = "260514"
    expiry = to_swift_date(fields.get("expiry_date")) or "260621"
    amount = (fields.get("amount") or "").replace(".", "").replace(",", ".")
    currency = fields.get("currency") or "USD"

    applicant = fields.get("applicant") or "APPLICANT NOT AVAILABLE"
    beneficiary = fields.get("beneficiary") or "BENEFICIARY NOT AVAILABLE"
    beneficiary_address = fields.get("beneficiary_address") or ""
    advising_bank = fields.get("swift") or (fields.get("advising_bank") or "BANK NOT AVAILABLE")
    goods = fields.get("goods_description") or "GOODS AS 
