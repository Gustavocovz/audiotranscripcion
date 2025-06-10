import streamlit as st
import requests
import tempfile
import os
from pydub import AudioSegment
from fpdf import FPDF

# Configuración inicial
st.set_page_config(page_title="Transcriptor AssemblyAI", layout="wide")
st.title("🗣️ Transcriptor con Diarización - AssemblyAI (ES)")

# Configuración de AssemblyAI
API_KEY = st.secrets["ASSEMBLYAI_API_KEY"]
upload_endpoint = "https://api.assemblyai.com/v2/upload"
transcript_endpoint = "https://api.assemblyai.com/v2/transcript"
headers = {"authorization": API_KEY}

# Cargar archivos (máximo 5)
uploaded_files = st.file_uploader(
    "Sube hasta 5 archivos de audio (.wav)", type=["wav"],
    accept_multiple_files=True
)

if uploaded_files:
    if len(uploaded_files) > 5:
        st.error("⚠️ Solo se permiten hasta 5 archivos.")
    else:
        transcripciones = []

        for file in uploaded_files:
            st.subheader(f"🎧 Archivo: {file.name}")
            st.audio(file, format="audio/wav")

            # Convertir a 16kHz y guardar temporalmente
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
                audio = AudioSegment.from_wav(file)
                audio = audio.set_frame_rate(16000).set_channels(1)
                audio.export(tmp.name, format="wav")
                audio_path = tmp.name

            # Subir archivo a AssemblyAI
            with open(audio_path, 'rb') as f:
                response = requests.post(upload_endpoint, headers=headers, data=f)
            audio_url = response.json()['upload_url']

            # Enviar a transcripción
            payload = {
                "audio_url": audio_url,
                "language_code": "es",
                "speaker_labels": True,
                "diarization": True,
                "punctuate": True,
                "format_text": True
            }
            response = requests.post(transcript_endpoint, json=payload, headers=headers)
            transcript_id = response.json()['id']

            # Esperar resultado
            status = "queued"
            with st.spinner("🔄 Transcribiendo... esto puede tardar unos segundos."):
                while status not in ["completed", "error"]:
                    polling = requests.get(f"{transcript_endpoint}/{transcript_id}", headers=headers).json()
                    status = polling["status"]

            if status == "completed":
                utterances = polling.get("utterances", [])
                texto_completo = ""
                for utt in utterances:
                    speaker = utt['speaker']
                    start = utt['start'] // 1000
                    texto = utt['text']
                    texto_completo += f"[{start}s] Speaker {speaker}: {texto}\n"
                transcripciones.append((file.name, texto_completo))
                st.success("✅ Transcripción exitosa")
                st.text_area("Transcripción:", value=texto_completo, height=200)
            else:
                st.error("❌ Error en la transcripción")

            os.remove(audio_path)

        # Exportar a PDF
        if transcripciones:
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", size=12)
            pdf.cell(200, 10, "Transcripciones - AssemblyAI", ln=True, align="C")
            pdf.ln(10)

            for nombre, texto in transcripciones:
                pdf.set_font("Arial", style="B", size=12)
                pdf.cell(200, 10, f"Archivo: {nombre}", ln=True)
                pdf.set_font("Arial", size=12)
                for linea in texto.split('\n'):
                    pdf.multi_cell(0, 10, linea)
                pdf.ln(5)

            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as pdf_file:
                pdf.output(pdf_file.name)
                with open(pdf_file.name, "rb") as f:
                    st.download_button(
                        label="📄 Descargar PDF con transcripciones",
                        data=f,
                        file_name="transcripciones_assemblyai.pdf",
                        mime="application/pdf"
                    )
                os.remove(pdf_file.name)
