import fitz  # PyMuPDF
from transformers import pipeline
import re
import os

# CPU only
os.environ["CUDA_VISIBLE_DEVICES"] = "-1"

# Load summarization model once (CPU)
summarizer_model = pipeline("summarization", model="facebook/bart-large-cnn", device=-1)

# ----------------- Extract clean text -----------------
def extract_text_from_pdf(pdf_path):
    text = ""
    with fitz.open(pdf_path) as doc:
        for page in doc:
            page_text = page.get_text("text")
            # Remove page numbers (lines with only numbers)
            page_text = "\n".join([line for line in page_text.splitlines() if not re.fullmatch(r"\s*\d+\s*", line)])
            # Remove references like [12] or (2021)
            page_text = re.sub(r'\[[0-9]*\]', '', page_text)
            page_text = re.sub(r'\([0-9]{4}\)', '', page_text)
            text += page_text + "\n"
    # Remove multiple newlines
    text = re.sub(r'\n+', '\n', text)
    return text.strip()

# ----------------- Summarize text -----------------
def summarize_text(text, word_count=200):
    """Summarize text approximately to user-specified word_count."""
    # Split text into manageable chunks for summarizer
    paragraphs = [p for p in text.split("\n") if len(p.strip()) > 20]
    chunks = []
    current_chunk = ""
    for para in paragraphs:
        if len(current_chunk.split()) + len(para.split()) <= 400:
            current_chunk += " " + para
        else:
            chunks.append(current_chunk.strip())
            current_chunk = para
    if current_chunk:
        chunks.append(current_chunk.strip())

    # Summarize each chunk
    summary_text = ""
    for chunk in chunks:
        if len(chunk.strip()) == 0:
            continue
        try:
            result = summarizer_model(chunk, max_length=200, min_length=50, do_sample=False)
            summary_text += result[0]['summary_text'] + " "
        except:
            continue

    # Truncate to exact word_count
    words = summary_text.split()
    if len(words) > word_count:
        summary_text = " ".join(words[:word_count])
    return summary_text.strip()