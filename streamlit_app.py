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
Eres un asesor financiero. Analiza el siguiente estado de cuenta en español. Extrae insights clave y preséntalos en secciones claras y útiles para el usuario.

Tu respuesta debe estar organizada así:

1. **Resumen general**: saldo anterior, saldo actual, pagos, intereses cobrados, pago mínimo.
2. **Observaciones útiles**: uso del crédito, si el usuario pagó total o mínimo, alertas importantes.
3. **Gasto por categoría** (usa estimación heurística si no hay categorías explícitas). Usa estas categorías:
   - 🛒 Supermercado
   - 🍽️ Restaurantes
   - ⛽ Transporte y gasolina
   - 🧾 Servicios
   - ✈️ Viajes
   - 🛍️ Compras personales
   - 💳 Meses sin intereses
   Da el gasto en pesos por categoría. Ejemplo: Supermercado: $1234.50
4. **Consejos personalizados**: en tono empático y útil.

Es muy importante que no dejes secciones vacías. Si no encuentras información suficiente, indícalo con un mensaje breve.

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

                # Respuesta cruda para debug
                st.subheader("🧾 Respuesta sin procesar (debug)")
                st.code(respuesta)

                partes = respuesta.split("**")
                for sec in partes:
                    if "Resumen general" in sec:
                        st.subheader("📊 Resumen general")
                        st.markdown(sec.strip())
                    elif "Observaciones útiles" in sec:
                        st.subheader("🔍 Observaciones útiles")
                        st.markdown(sec.strip())
                    elif "Gasto por categoría" in sec:
                        st.subheader("📂 Gasto por categoría")
                        st.markdown(sec.strip())

                        try:
                            labels = []
                            values = []
                            lines = sec.split("\n")
                            for line in lines:
                                match = re.match(r"(.+):\s*\$([\d,]+\.\d{2})", line)
                                if match:
                                    labels.append(match.group(1).strip())
                                    values.append(float(match.group(2).replace(",", "")))
                            if labels and values:
                                fig, ax = plt.subplots()
                                ax.pie(values, labels=labels, autopct='%1.1f%%', startangle=90)
                                ax.axis("equal")
                                st.pyplot(fig)
                        except Exception:
                            st.warning("No se pudo graficar el gasto por categoría automáticamente.")

                    elif "Consejos personalizados" in sec:
                        st.subheader("💡 Consejos personalizados")
                        st.markdown(sec.strip())

            except Exception as e:
                st.error(f"❌ Error al procesar con DeepSeek: {e}")
