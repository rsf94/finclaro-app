import streamlit as st
import pdfplumber
import tempfile
import requests
import re
import pandas as pd
from PIL import Image

st.set_page_config(page_title="FinClaro - Análisis simple", layout="centered")

# Cargar logo (ajusta la ruta si hace falta)
logo = Image.open("logo.png")
st.image(logo, width=160)
st.title("FinClaro")
st.subheader("Sube tu estado de cuenta en PDF y recibe observaciones claras")

def convert_date_spanish_to_iso(date_str):
    months_es_to_en = {
        "ENE": "JAN", "FEB": "FEB", "MAR": "MAR", "ABR": "APR",
        "MAY": "MAY", "JUN": "JUN", "JUL": "JUL", "AGO": "AUG",
        "SEP": "SEP", "OCT": "OCT", "NOV": "NOV", "DIC": "DEC"
    }
    for es, en in months_es_to_en.items():
        date_str = date_str.upper().replace(es, en)
    return pd.to_datetime(date_str, format="%d-%b-%Y").strftime("%Y-%m-%d")

def extract_payment_due_date_flexible(text):
    lines = text.splitlines()
    for line in lines:
        if "fecha límite de pago" in line.lower():
            idx = lines.index(line)
            candidates = lines[idx:idx+3]
            for cand in candidates:
                match = re.search(r"(\d{1,2}-[A-Z]{3}-\d{4})", cand.upper())
                if match:
                    return convert_date_spanish_to_iso(match.group(1))
    return None

def extract_general_info(text):
    text_clean = text.replace('\xa0', ' ').replace('\n', ' ')
    bank_match = re.search(r"\bBanco\b(?:\s+[A-Za-záéíóúÁÉÍÓÚñÑ]+){1,4}", text_clean, re.IGNORECASE)
    bank = bank_match.group(0).strip() if bank_match else "Unknown"
    card_type_match = re.search(r"\bTarjeta\b\s+(?:de\s+)?(Crédito|Débito|Debito)", text_clean, re.IGNORECASE)
    card_type = card_type_match.group(1).capitalize() if card_type_match else "Unknown"
    segment_match = re.search(r"Estado de Cuenta\s+([A-Za-z]+)", text_clean, re.IGNORECASE)
    segment = segment_match.group(1).capitalize() if segment_match else "Unknown"
    return {"bank": bank, "card_type": card_type, "segment": segment}

def parse_financial_summary_table(text):
    lines = [line.strip() for line in text.replace('\xa0', ' ').splitlines() if line.strip()]
    keys_map = {
        "adeudo del periodo anterior": "previous_balance",
        "cargos regulares": "regular_charges",
        "cargos compras a meses": "installment_purchases",
        "monto de intereses": "interest_amount",
        "monto de comisiones": "commission_amount",
        "iva de intereses y comisiones": "tax_on_interest_commission",
        "pagos y abonos": "payments_and_credits",
        "pago para no generar intereses": "payment_to_avoid_interest"
    }
    result = {}
    i = 0
    while i < len(lines) - 1:
        label = lines[i].lower()
        label_clean = re.sub(r"\(.*?\)|\d+", "", label).strip()
        for k in keys_map:
            if k in label_clean:
                value_line = lines[i + 1].replace("$", "").replace(",", "").replace("+", "").replace("-", "").strip()
                try:
                    result[keys_map[k]] = float(value_line)
                except:
                    result[keys_map[k]] = None
                i += 1
                break
        i += 1
    for v in keys_map.values():
        if v not in result:
            result[v] = None
    return result

def extract_movements(text):
    regex_charge = re.compile(
        r"(?P<date>\d{2}-[A-Z]{3}-\d{4})\s+\d{2}-[A-Z]{3}-\d{4}\s+(?P<description>.+?)\s+\+\$(?P<amount>[\d,]+\.\d{2})",
        re.MULTILINE
    )
    regex_payment = re.compile(
        r"(?P<date>\d{2}-[A-Z]{3}-\d{4})\s+\d{2}-[A-Z]{3}-\d{4}\s+(?P<description>PAGO.+?)\s+-\$(?P<amount>[\d,]+\.\d{2})",
        re.MULTILINE
    )
    charges = regex_charge.findall(text)
    payments = regex_payment.findall(text)

    df_charges = pd.DataFrame(charges, columns=["date", "description", "amount"])
    df_charges["amount"] = df_charges["amount"].str.replace(",", "").astype(float)
    df_charges["type"] = "charge"

    df_payments = pd.DataFrame(payments, columns=["date", "description", "amount"])
    df_payments["amount"] = df_payments["amount"].str.replace(",", "").astype(float)
    df_payments["type"] = "payment"

    df_movements = pd.concat([df_charges, df_payments], ignore_index=True)

    months_es_to_en = {
        "ENE": "JAN", "FEB": "FEB", "MAR": "MAR", "ABR": "APR",
        "MAY": "MAY", "JUN": "JUN", "JUL": "JUL", "AGO": "AUG",
        "SEP": "SEP", "OCT": "OCT", "NOV": "NOV", "DIC": "DEC"
    }
    for es, en in months_es_to_en.items():
        df_movements["date"] = df_movements["date"].str.replace(es, en)
    df_movements["date"] = pd.to_datetime(df_movements["date"], format="%d-%b-%Y").dt.strftime("%Y-%m-%d")
    df_movements["description"] = df_movements["description"].str.replace(r"[^\x20-\x7E]", " ", regex=True).str.replace(r"\s+", " ", regex=True).str.strip()

    return df_movements.to_dict(orient="records")

def extract_msi_purchases(text):
    lines = [line.strip() for line in text.splitlines()]
    msi_records = []
    i = 0
    while i < len(lines) - 6:
        try:
            date = convert_date_spanish_to_iso(lines[i])
            description = re.sub(r"\s+", " ", lines[i + 1])
            original_amount = float(lines[i + 2].replace("$", "").replace(",", ""))
            pending_balance = float(lines[i + 3].replace("$", "").replace(",", ""))
            payment_required = float(lines[i + 4].replace("$", "").replace(",", ""))
            payment_number = lines[i + 5]
            interest_rate = lines[i + 6]
            msi_records.append({
                "date": date,
                "description": description,
                "original_amount": original_amount,
                "pending_balance": pending_balance,
                "payment_required": payment_required,
                "payment_number": payment_number,
                "interest_rate": interest_rate
            })
        except:
            pass
        i += 1
    return msi_records

def add_consistency_flag(financial_summary, movements, tolerance=10):
    cargos_sum = sum(m["amount"] for m in movements if m["type"] == "charge")
    pagos_sum = sum(m["amount"] for m in movements if m["type"] == "payment")

    cargos_resumen = (financial_summary.get("regular_charges") or 0) + (financial_summary.get("installment_purchases") or 0)
    pagos_resumen = financial_summary.get("payments_and_credits") or 0

    cargos_diff = abs(cargos_sum - cargos_resumen)
    pagos_diff = abs(pagos_sum - pagos_resumen)

    cargos_ok = cargos_diff <= tolerance
    pagos_ok = pagos_diff <= tolerance

    financial_summary["summary_consistent"] = cargos_ok and pagos_ok
    financial_summary["cargos_difference"] = cargos_diff
    financial_summary["pagos_difference"] = pagos_diff

    return financial_summary

def llamar_deepseek(prompt, api_key):
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3
    }
    response = requests.post("https://api.deepseek.com/v1/chat/completions", headers=headers, json=data)
    if response.status_code == 200:
        return response.json()["choices"][0]["message"]["content"]
    else:
        raise Exception(f"Error DeepSeek: {response.status_code} {response.text}")

def fallback_deepseek_for_field(field_name, pdf_text, api_key):
    prompt = f"Extrae el campo '{field_name}' del siguiente estado de cuenta en texto:\n\n{pdf_text}"
    return llamar_deepseek(prompt, api_key)

def main():
    st.title("FinClaro - Análisis de Estado de Cuenta Banorte")

    uploaded_file = st.file_uploader("Sube tu estado de cuenta en PDF", type=["pdf"])

    if uploaded_file:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
            tmp_file.write(uploaded_file.read())
            tmp_path = tmp_file.name

        with pdfplumber.open(tmp_path) as pdf:
            full_text = ""
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    full_text += text + "\\n"

        if not full_text.strip():
            st.error("No se pudo extraer texto del PDF. ¿Es un PDF escaneado?")
            return

        st.info("Procesando extracción local...")
        metadata = extract_metadata(full_text)
        financial_summary = parse_financial_summary_table(full_text)
        movements = extract_movements(full_text)
        msi_purchases = extract_msi_purchases(full_text)
        financial_summary = add_consistency_flag(financial_summary, movements)

        cargos_sum = sum(m["amount"] for m in movements if m["type"] == "charge")
        pagos_sum = sum(m["amount"] for m in movements if m["type"] == "payment")

        campos_faltantes = [k for k, v in financial_summary.items() if v is None]

        st.write("Campos faltantes en resumen:", campos_faltantes)
        st.write(f"Suma cargos movimientos: {cargos_sum}")
        st.write(f"Cargos resumen: {(financial_summary.get('regular_charges') or 0) + (financial_summary.get('installment_purchases') or 0)}")
        st.write(f"Suma pagos movimientos: {pagos_sum}")
        st.write(f"Pagos resumen: {financial_summary.get('payments_and_credits') or 0}")

        if campos_faltantes or not financial_summary["summary_consistent"]:
            st.warning("Inconsistencias detectadas. Consultando DeepSeek para completar análisis...")
            api_key = st.secrets["deepseek"]["api_key"]

            for campo in campos_faltantes:
                try:
                    valor = fallback_deepseek_for_field(campo, full_text, api_key)
                    st.write(f"Campo {campo} extraído con DeepSeek:")
                    st.write(valor)
                except Exception as e:
                    st.error(f"Error consultando DeepSeek para {campo}: {e}")
        else:
            st.success("Extracción local completa y consistente.")

        st.subheader("Resumen financiero")
        st.json(financial_summary)

        st.subheader("Movimientos (primeros 10)")
        st.table(movements[:10])

        st.subheader("Compras a Meses Sin Intereses")
        st.table(msi_purchases)

        st.subheader("Metadata del Estado de Cuenta")
        st.json(metadata)

if __name__ == "__main__":
    main()
