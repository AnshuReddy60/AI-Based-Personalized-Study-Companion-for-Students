from flask import Blueprint, render_template, request, jsonify, current_app
import os
import pyttsx3
from pdfminer.high_level import extract_text
import threading
from utils import record_tool_usage  # Use utils.py to handle DB logging

pdf_bp = Blueprint("pdf_bp", __name__)

# Track progress per user
pdf_progress = {}

def convert_pdf_to_audio(pdf_path, user_id, audio_path):
    """Process PDF to audio in a background thread"""
    try:
        pdf_progress[user_id] = 0

        # Extract text from PDF
        text = extract_text(pdf_path)
        pdf_progress[user_id] = 30

        # Convert text to audio
        engine = pyttsx3.init()
        engine.save_to_file(text, audio_path)
        pdf_progress[user_id] = 70
        engine.runAndWait()
        pdf_progress[user_id] = 100  # Done

        print(f"[INFO] PDF converted for user {user_id}: {audio_path}")

        # Log usage via utils.py
        record_tool_usage(user_id, "PDF to Audio")

    except Exception as e:
        print(f"[ERROR] PDF processing failed: {e}")
        pdf_progress[user_id] = -1  # Error

# Routes
@pdf_bp.route("/pdf_to_audio")
def pdf_to_audio_page():
    return render_template("pdf_to_audio.html")

@pdf_bp.route("/pdf_to_audio_process", methods=["POST"])
def pdf_to_audio_process():
    pdf_file = request.files["pdf_file"]
    user_id = request.form.get("user_id", "1")

    # Save uploaded PDF
    upload_folder = os.path.join(current_app.root_path, "uploads")
    os.makedirs(upload_folder, exist_ok=True)
    pdf_path = os.path.join(upload_folder, pdf_file.filename)
    pdf_file.save(pdf_path)

    # Audio output path
    audio_folder = os.path.join(current_app.root_path, "static", "audios")
    os.makedirs(audio_folder, exist_ok=True)
    audio_path = os.path.join(audio_folder, pdf_file.filename.replace(".pdf", ".mp3"))

    # Start background thread (daemon=True so it won't block exit)
    threading.Thread(target=convert_pdf_to_audio, args=(pdf_path, user_id, audio_path), daemon=True).start()

    return jsonify({
        "status": "success",
        "message": "PDF processing started",
        "audio_file": os.path.basename(audio_path)
    })

@pdf_bp.route("/pdf_progress")
def pdf_progress_status():
    user_id = request.args.get("user_id", "1")
    progress = pdf_progress.get(user_id, 0)
    return jsonify({"progress": progress})
