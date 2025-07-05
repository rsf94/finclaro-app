
import streamlit as st
import pdfplumber
import tempfile
import openai
import json

st.set_page_config(page_title="FinClaro - Analiza tu estado de cuenta", layout="centered")

st.title("📄 FinClaro")
st.subheader("Sube tu estado de cuenta en PDF y obtén un análisis claro y útil")

openai.api_key = st.secrets["openai"]["api_key"]

def prompt_estado_cuenta(texto):
    return f"""
Eres un asistente financiero. Tu tarea es analizar el texto plano de un estado de cuenta bancario en español y devolver un JSON estructurado con la siguiente información:

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

Analiza el siguiente texto de un estado de cuenta y responde solo con el JSON:

<<<
{texto}
>>>
"""

uploaded_file = st.file_uploader("Cargar archivo PDF", type=["pdf"])

if uploaded_file:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
        tmp_file.write(uploaded_file.read())
        tmp_path = tmp_file.name

    st.success("Archivo cargado correctamente ✅")

    # Extraer texto
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
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "Eres un experto en análisis financiero."},
                    {"role": "user", "content": prompt_estado_cuenta(all_text)}
                ],
                temperature=0.3,
                max_tokens=2000
            )

            respuesta = response["choices"][0]["message"]["content"]
            resultado_json = json.loads(respuesta)

            st.success("✅ Análisis completo")
            st.subheader("Resumen general")
            st.json(resultado_json["resumen"])

            st.subheader("Movimientos detectados")
            st.dataframe(resultado_json["movimientos"])

        except Exception as e:
            st.error(f"❌ Error al procesar con OpenAI: {e}")
