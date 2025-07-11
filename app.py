import streamlit as st
import requests
import time
import tempfile
import os
import subprocess
from fpdf import FPDF

# Configuración inicial
st.set_page_config(page_title="Transcriptor Optimizado", layout="wide")
st.title("🎧 Transcriptor de Audio")

# API AssemblyAI
ASSEMBLYAI_API_KEY = st.secrets["assemblyai_key"]
upload_endpoint = "https://api.assemblyai.com/v2/upload"
transcript_endpoint = "https://api.assemblyai.com/v2/transcript"
headers = {"authorization": ASSEMBLYAI_API_KEY}

# Consultar saldo
def consultar_saldo():
    response = requests.get("https://api.assemblyai.com/v2/balance", headers=headers)
    if response.status_code == 200:
        return float(response.json()["balance"])
    return None

saldo = consultar_saldo()
if saldo is not None:
    st.info(f"💰 Créditos disponibles en AssemblyAI: **${saldo:.2f} USD**")
else:
    st.warning("⚠️ No se pudo consultar el saldo en AssemblyAI.")

# Estados
if "transcripciones" not in st.session_state:
    st.session_state.transcripciones = []

if "procesados" not in st.session_state:
    st.session_state.procesados = []

if "pdf_ready" not in st.session_state:
    st.session_state.pdf_ready = False

if "pdf_temp_path" not in st.session_state:
    st.session_state.pdf_temp_path = None

# Botón de descarga si PDF está listo
if st.session_state.pdf_ready and os.path.exists(st.session_state["pdf_temp_path"]):
    with open(st.session_state["pdf_temp_path"], "rb") as f:
        st.download_button(
            label="📄 Descargar PDF con hablantes y tiempos",
            data=f.read(),
            file_name="transcripciones_diarizadas.pdf",
            mime="application/pdf"
        )

# Contenedor de transcripciones
transcripciones_container = st.container()

# Subida de archivos
uploaded_files = st.file_uploader(
    "Sube hasta 5 archivos de audio (.wav, .mp3)",
    type=["wav", "mp3"],
    accept_multiple_files=True
)

# Funciones
def subir_audio(file_path):
    with open(file_path, 'rb') as f:
        response = requests.post(upload_endpoint, headers=headers, data=f)
    return response.json()['upload_url']

def solicitar_transcripcion(audio_url):
    data = {
        "audio_url": audio_url,
        "speaker_labels": True,
        "language_code": "es",
        "auto_chapters": False
    }
    response = requests.post(transcript_endpoint, json=data, headers=headers)
    return response.json()['id']

def esperar_transcripcion(transcript_id, progress_bar):
    intentos = 0
    while True:
        response = requests.get(f"{transcript_endpoint}/{transcript_id}", headers=headers)
        status = response.json()['status']
        if status == "completed":
            progress_bar.progress(100)
            return response.json()
        elif status == "error":
            raise Exception(response.json()['error'])
        intentos += 1
        progress_bar.progress(min(90, intentos * 5))
        time.sleep(5)

def formatear_tiempo(segundos):
    minutos = int(segundos // 60)
    segundos_restantes = int(segundos % 60)
    return f"{minutos:02}:{segundos_restantes:02}"

# Procesamiento
if uploaded_files:
    for file in uploaded_files:
        if file.name in st.session_state.procesados:
            continue

        progress_bar = st.progress(0)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
            tmp.write(file.getbuffer())
            tmp_path = tmp.name

        try:
            # Convertir a mono y 16000 Hz usando ffmpeg
            converted_path = tmp_path.replace(".wav", "_converted.wav")
            ffmpeg_cmd = [
                "ffmpeg", "-y",
                "-i", tmp_path,
                "-ac", "1",
                "-ar", "16000",
                converted_path
            ]
            subprocess.run(ffmpeg_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

            audio_url = subir_audio(converted_path)
            progress_bar.progress(30)
            transcript_id = solicitar_transcripcion(audio_url)
            progress_bar.progress(50)
            result = esperar_transcripcion(transcript_id, progress_bar)

            texto_formateado = ""
            for utt in result['utterances']:
                start = formatear_tiempo(utt['start'] / 1000)
                end = formatear_tiempo(utt['end'] / 1000)
                speaker = utt['speaker']
                texto = utt['text']
                texto_formateado += f"[{start} - {end}] {speaker}: {texto}\n"

            st.session_state.transcripciones.append((file.name, texto_formateado))
            st.session_state.procesados.append(file.name)

            # Mostrar resultados arriba
            with transcripciones_container:
                st.markdown("---")
                st.subheader(f"🎧 Archivo: {file.name}")
                st.audio(converted_path, format="audio/wav")
                st.success("✅ Transcripción lista con hablantes y tiempos")

        except Exception as e:
            st.error(f"❌ Error: {e}")

        finally:
            os.remove(tmp_path)
            if os.path.exists(converted_path):
                os.remove(converted_path)

# Generar PDF
if st.session_state.transcripciones and not st.session_state.pdf_ready:
    pdf = FPDF()

    for nombre, texto in st.session_state.transcripciones:
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        pdf.cell(200, 10, "Transcripción con Hablantes y Tiempos", ln=True, align="C")
        pdf.ln(10)

        pdf.set_font("Arial", style="B", size=12)
        pdf.cell(200, 10, f"Archivo: {nombre}", ln=True)
        pdf.set_font("Arial", size=11)

        for linea in texto.split('\n'):
            pdf.multi_cell(0, 8, linea)
        pdf.ln(5)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as pdf_file:
        pdf.output(pdf_file.name)
        st.session_state.pdf_temp_path = pdf_file.name
        st.session_state.pdf_ready = True

    st.rerun()


