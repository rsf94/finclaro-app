
import streamlit as st
import pdfplumber
import tempfile
import requests

st.set_page_config(page_title="FinClaro - Análisis simple", layout="centered")

st.title("📄 FinClaro")
st.subheader("Sube tu estado de cuenta en PDF y recibe observaciones claras")

def generar_prompt(texto):
    return f"""
Eres un asesor financiero. Analiza el siguiente estado de cuenta en español y proporciona observaciones útiles para el usuario. 
Sé claro, directo, empático y útil. Resume lo más importante que ves en los movimientos, pagos, intereses, uso de crédito, meses sin intereses, etc.

Texto del estado de cuenta:

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
            {"role": "system", "content": "Eres un asesor financiero experto en crédito personal."},
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
                st.subheader("🔍 Observaciones e insights")
                st.markdown(respuesta)
            except Exception as e:
                st.error(f"❌ Error al procesar con DeepSeek: {e}")
