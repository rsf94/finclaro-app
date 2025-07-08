import streamlit as st
import pdfplumber
import tempfile
import requests
import re
import pandas as pd
from PIL import Image

st.set_page_config(page_title="FinClaro - Análisis simple", layout="centered")

# Carga el logo, reemplaza "logo.png" por la ruta correcta si hace falta
logo = Image.open("logo.png")
st.image(logo, width=160)
st.title("FinClaro")
st.subheader("Sube tu estado de cuenta en PDF y recibe observaciones claras")

def parse_resumen_financiero_fijo(text):
    start_marker = "RESUMEN DE CARGOS Y ABONOS DEL PERIODO"
    end_marker = "COMPRAS Y CARGOS DIFERIDOS A MESES SIN INTERESES"
    start_idx = text.find(start_marker)
    if start_idx == -1:
        return {}
    end_idx = text.find(end_marker, start_idx)
    if end_idx == -1:
        end_idx = len(text)
    block = text[start_idx:end_idx]

    lines = [line.strip() for line in block.splitlines() if line.strip()]

    campos_ordenados = [
        "previous_balance",
        "regular_charges",
        "installment_purchases",
        "interest_amount",
        "commission_amount",
        "tax_on_interest_commission",
        "payments_and_credits",
        "payment_to_avoid_interest"
    ]

    numeros = []
    for line in lines:
        encontrados = re.findall(r"[\d,.]+\.\d{2}", line)
        for num in encontrados:
            numeros.append(float(num.replace(",", "")))

    resultado = {}
    for i, campo in enumerate(campos_ordenados):
        if i < len(numeros):
            resultado[campo] = numeros[i]
        else:
            resultado[campo] = None

    return resultado

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

def llamar_deepseek_simple(field_name, pdf_text, api_key):
    prompt = f"Extrae solo el valor numérico para '{field_name}' del siguiente texto:\n\n{pdf_text}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0
    }
    response = requests.post("https://api.deepseek.com/v1/chat/completions", headers=headers, json=data)
    if response.status_code == 200:
        return response.json()["choices"][0]["message"]["content"].strip()
    else:
        raise Exception(f"Error DeepSeek: {response.status_code} {response.text}")

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
                txt = page.extract_text()
                if txt:
                    full_text += txt + "\n"

        if not full_text.strip():
            st.error("No se pudo extraer texto del PDF. ¿Es un PDF escaneado?")
            return

        financial_summary = parse_resumen_financiero_fijo(full_text)
        movements = extract_movements(full_text)
        financial_summary = add_consistency_flag(financial_summary, movements)

        campos_faltantes = [k for k, v in financial_summary.items() if v is None]
        if campos_faltantes:
            st.warning(f"Campos faltantes: {campos_faltantes}. Consultando DeepSeek para completarlos...")
            api_key = st.secrets["deepseek"]["api_key"]
            for campo in campos_faltantes:
                try:
                    valor = llamar_deepseek_simple(campo, full_text, api_key)
                    try:
                        financial_summary[campo] = float(valor.replace(",", ""))
                    except:
                        financial_summary[campo] = valor
                except Exception as e:
                    st.error(f"Error al consultar DeepSeek para {campo}: {e}")

        st.subheader("Resumen financiero")
        st.json(financial_summary)

        st.subheader("Movimientos (primeros 10)")
        st.table(movements[:10])

if __name__ == "__main__":
    main()
