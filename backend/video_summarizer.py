# video_summarizer.py
from flask import Blueprint, render_template, request, send_file
import os
import subprocess
import tempfile
import yt_dlp
from nltk.tokenize import sent_tokenize
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename
import whisper
from transformers import pipeline
from utils import record_tool_usage

# CONFIG
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

FFMPEG_PATH = r"C:\ffmpeg-8.0-full_build\ffmpeg-8.0-full_build\bin\ffmpeg.exe"
os.environ["IMAGEIO_FFMPEG_EXE"] = FFMPEG_PATH

video_bp = Blueprint("video_summarizer", __name__)

# Models (load once)
whisper_model = whisper.load_model("small")
summarizer = pipeline("summarization", model="facebook/bart-large-cnn")

def extract_audio(video_path):
    audio_path = os.path.join(UPLOAD_FOLDER, "temp_audio.wav")
    cmd = [FFMPEG_PATH, "-i", video_path, "-ac", "1", "-ar", "16000", audio_path, "-y"]
    subprocess.run(cmd, check=True)
    return audio_path

def transcribe_audio(audio_path):
    res = whisper_model.transcribe(audio_path)
    return res.get("text", "")

def summarize_text(text, max_lines=25):
    sentences = sent_tokenize(text)
    return " ".join(sentences[:max_lines])

def download_youtube_video(video_link):
    video_path = os.path.join(UPLOAD_FOLDER, "yt_video.mp4")
    ydl_opts = {"outtmpl": video_path, "format": "mp4/best", "quiet": True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.extract_info(video_link, download=True)
    return video_path

@video_bp.route("/video_summarizer", methods=["GET", "POST"])
@login_required
def video_summarizer():
    transcript = summary = error = None
    summary_file_path = None

    if request.method == "POST":
        video_file = request.files.get("video_file")
        video_link = request.form.get("video_link")
        try:
            summary_length = min(int(request.form.get("summary_length", 25)), 25)
        except:
            summary_length = 25

        video_path = None
        try:
            # Save or download video
            if video_file and video_file.filename:
                safe_name = secure_filename(video_file.filename)
                video_path = os.path.join(UPLOAD_FOLDER, safe_name)
                video_file.save(video_path)
            elif video_link:
                clean_link = video_link.split("&")[0].split("?si=")[0]
                video_path = download_youtube_video(clean_link)
            else:
                error = "Please upload a video or provide a YouTube link."
                return render_template("video_summarizer.html", error=error)

            # Extract -> Transcribe -> Summarize
            audio_path = extract_audio(video_path)
            transcript = transcribe_audio(audio_path)
            summary = summarize_text(transcript, max_lines=summary_length)

            # Save summary to temp file for download
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
            tmp.write(summary.encode("utf-8"))
            tmp.close()
            summary_file_path = tmp.name

            # Cleanup extracted files (best-effort)
            for f in (audio_path, video_path):
                try:
                    if f and os.path.exists(f):
                        os.remove(f)
                except Exception as ee:
                    print("[WARN] cleanup failed:", ee)

            # Record usage (only if user is authenticated)
            try:
                if current_user and getattr(current_user, "is_authenticated", False):
                    record_tool_usage(current_user.id, "Video Summarizer")
                else:
                    print("[WARN] Not recording usage: user not authenticated.")
            except Exception as e:
                print("[WARN] record_tool_usage failed:", e)

        except Exception as e:
            error = f"❌ Error: {e}"

    return render_template(
        "video_summarizer.html",
        transcript=transcript,
        summary=summary,
        error=error,
        summary_file=summary_file_path
    )

@video_bp.route("/download_summary/<path:file_path>")
@login_required
def download_summary(file_path):
    if os.path.exists(file_path):
        return send_file(file_path, as_attachment=True, download_name="summary.txt")
    return "File not found", 404
