import streamlit as st
import pdfplumber
import tempfile
import json
import requests

st.set_page_config(page_title="FinClaro - Analiza tu estado de cuenta", layout="centered")

st.title("📄 FinClaro")
st.subheader("Sube tu estado de cuenta en PDF y obtén un análisis claro y útil")

def prompt_estado_cuenta(texto):
    return f"""
Eres un asistente financiero. Tu tarea es analizar el texto plano de un estado de cuenta bancario en español y devolver dos cosas:

1. Un JSON estructurado con esta información:

{{
  "banco": "nombre del banco",
  "periodo": {{
    "fecha_corte": "YYYY-MM-DD",
    "fecha_pago": "YYYY-MM-DD"
  }},
  "resumen": {{
    "saldo_anterior": number,
    "saldo_actual": number,
    "pago_minimo": number,
    "pago_para_no_generar_intereses": number,
    "intereses_cobrados": number
  }},
  "movimientos": [
    {{
      "fecha": "YYYY-MM-DD",
      "descripcion": "texto",
      "monto": number,
      "tipo": "cargo" o "pago"
    }}
  ],
  "msi_detalle": [
    {{
      "fecha": "YYYY-MM-DD",
      "descripcion": "texto",
      "monto_original": number,
      "meses_totales": number,
      "meses_restantes": number,
      "pago_mensual": number
    }}
  ]
}}

2. Una lista de insights financieros para el usuario. Usa este formato:

**INSIGHTS**

- Tu saldo actual es mayor al anterior, lo cual indica que acumulaste más deuda.
- Solo pagaste el mínimo, podrías generar intereses.
- Tienes 3 cargos a meses sin intereses por un total de $X.
- Tu gasto mensual fue de $X, principalmente en categoría Y.

Solo responde con el JSON y luego los insights. No incluyas texto adicional fuera de eso.

Aquí está el texto del estado de cuenta:

<<<
{texto}
>>>
"""

def llamar_deepseek(texto, api_key):
    prompt = prompt_estado_cuenta(texto)
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    data = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": "Eres un experto en análisis financiero."},
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
        st.info("Procesando estado de cuenta con inteligencia artificial...")

        try:
            respuesta = llamar_deepseek(all_text, st.secrets["deepseek"]["api_key"])

            # Separar JSON e insights
            json_part = respuesta.split("**INSIGHTS**")[0].strip()
            insights_part = respuesta.split("**INSIGHTS**")[-1].strip()

            resultado_json = json.loads(json_part)

            st.success("✅ Análisis completo")
            st.subheader("Resumen general")
            st.json(resultado_json["resumen"])

            st.subheader("Movimientos detectados")
            st.dataframe(resultado_json["movimientos"])

            st.subheader("🔍 Insights financieros")
            st.markdown(insights_part)

        except Exception as e:
            st.error(f"❌ Error al procesar con DeepSeek: {e}")
