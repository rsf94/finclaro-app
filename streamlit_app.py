
import streamlit as st
import pdfplumber
import tempfile

st.set_page_config(page_title="FinClaro - Analiza tu estado de cuenta", layout="centered")

st.title("📄 FinClaro")
st.subheader("Sube tu estado de cuenta en PDF y obtén un análisis claro y útil")

uploaded_file = st.file_uploader("Cargar archivo PDF", type=["pdf"])

if uploaded_file:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
        tmp_file.write(uploaded_file.read())
        tmp_path = tmp_file.name

    st.success("Archivo cargado correctamente ✅")

    # Extraer texto con pdfplumber
    with pdfplumber.open(tmp_path) as pdf:
        all_text = ""
        for page in pdf.pages:
            all_text += page.extract_text() + "\n"

    if all_text.strip():
        st.subheader("📑 Vista previa del texto extraído")
        st.text_area("Texto del estado de cuenta", all_text, height=400)
    else:
        st.warning("No se pudo extraer texto del PDF. ¿Es escaneado?")
