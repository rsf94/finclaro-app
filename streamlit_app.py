import streamlit as st
import pdfplumber
import tempfile
import requests
from PIL import Image
import matplotlib.pyplot as plt
import re

st.set_page_config(page_title="FinClaro - Análisis simple", layout="centered")

logo = Image.open("logo.png")
st.image(logo, width=160)
st.title("FinClaro")
st.subheader("Sube tu estado de cuenta en PDF y recibe observaciones claras")


def generar_prompt(texto):
    return f"""
You are a personal finance advisor helping a user who uploaded their credit card statement (in Spanish). Your job is to review the statement and provide helpful insights in Spanish.

Be clear, empathetic, and useful. Always generate a helpful summary, even if information is missing or incomplete.

Focus on:
- Overall account status
- Whether they paid in full or just the minimum
- How much they spent and in what categories
- Interest or missed payments
- Any red flags or notable patterns
- Any active "Meses Sin Intereses" (monthly installment plans)

Respond in **Spanish**, using paragraphs or bullet points to organize your insights.

Statement text:

<<<
{texto}
>>>
"""


def llamar_deepseek(texto, api_key):
    prompt = generar_prompt(texto)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    data = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": "You are an expert personal finance advisor."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3
    }

    response = requests.post("https://api.deepseek.com/v1/chat/completions", headers=headers, json=data)

    if response.status_code == 200:
        return response.json()["choices"][0]["message"]["content"]
    else:
        raise Exception(f"Error de DeepSeek: {response.status_code} - {response.text}")


uploaded_file = st.file_uploader("Cargar archivo PDF", type=["pdf"])

if uploaded_file:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
        tmp_file.write(uploaded_file.read())
        tmp_path = tmp_file.name

    st.success("Archivo cargado correctamente ✅")

    with pdfplumber.open(tmp_path) as pdf:
        all_text = ""
        for page in pdf.pages:
            txt = page.extract_text()
            if txt:
                all_text += txt + "\n"

    if not all_text.strip():
        st.error("No se pudo extraer texto del PDF. ¿Es escaneado?")
    else:
        with st.spinner("Analizando el estado de cuenta con inteligencia artificial..."):
            try:
                respuesta = llamar_deepseek(all_text, st.secrets["deepseek"]["api_key"])
                st.success("✅ Análisis completo")

                st.subheader("🔍 Observaciones del asesor financiero")
                st.markdown(respuesta)

                st.subheader("📊 Gasto por categoría (si aplica)")
                # Extraer líneas tipo "Supermercado: $1234.56" del texto completo
                try:
                    labels = []
                    values = []
                    lines = respuesta.split("\n")
                    for line in lines:
                        match = re.match(r"(.+?):\s*\$([\d,]+\.\d{2})", line)
                        if match:
                            labels.append(match.group(1).strip())
                            values.append(float(match.group(2).replace(",", "")))

                    if labels and values:
                        fig, ax = plt.subplots()
                        ax.pie(values, labels=labels, autopct='%1.1f%%', startangle=90)
                        ax.axis("equal")
                        st.pyplot(fig)
                except Exception:
                    st.warning("No se pudo generar la gráfica automáticamente.")

            except Exception as e:
                st.error(f"❌ Error al procesar con DeepSeek: {e}")
