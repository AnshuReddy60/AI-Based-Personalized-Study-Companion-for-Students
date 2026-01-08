from flask import Blueprint, render_template, request, jsonify
import sqlite3
import re
from collections import Counter
from datetime import datetime
from flask_login import current_user, login_required

flashcards_bp = Blueprint("flashcards", __name__)
DB_PATH = "users.db"  # Make sure this matches your database file

# ------------------------
# Helper: Generate Topic
# ------------------------
def generate_topic(text):
    sentences = re.split(r'(?<=[.!?]) +', text.strip())
    first_sentence = sentences[0].strip() if sentences else "Flashcard Topic"

    words = re.findall(r'\w+', text.lower())
    stopwords = set(['the','and','of','in','to','a','is','for','on','with','as','by','this','that','it'])
    keywords = [w for w in words if w not in stopwords and len(w) > 3]
    top_keywords = [w for w,_ in Counter(keywords).most_common(2)]

    topic = first_sentence
    if top_keywords:
        topic += ": " + ", ".join(top_keywords).title()
    return topic

# ------------------------
# Helper: Extract Main Points
# ------------------------
def extract_main_points(text, max_points=10):
    sentences = re.split(r'(?<=[.!?]) +', text)
    sentences = [s.strip() for s in sentences if len(s.strip().split()) > 4]

    words = re.findall(r'\w+', text.lower())
    stopwords = set(['the','and','of','in','to','a','is','for','on','with','as','by','this','that','it'])
    keywords = [w for w in words if w not in stopwords]

    word_freq = Counter(keywords)

    scored_sentences = []
    for s in sentences:
        s_words = re.findall(r'\w+', s.lower())
        score = sum(word_freq.get(w, 0) for w in s_words)
        scored_sentences.append((score, s))

    top_sentences = [s for _, s in sorted(scored_sentences, reverse=True)[:max_points]]

    concise_points = []
    for s in top_sentences:
        words = s.split()
        if len(words) > 15:
            s = ' '.join(words[:15]) + '...'
        concise_points.append(s)

    return concise_points

# ------------------------
# Helper: Record Tool Usage
# ------------------------
def record_tool_usage(user_id, tool_name):
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO tool_usage (user_id, tool_name, ts)
            VALUES (?, ?, ?)
        """, (user_id, tool_name, datetime.utcnow().isoformat()))

        # Increment flashcards_count in users table
        cur.execute("UPDATE users SET flashcards_count = COALESCE(flashcards_count,0)+1 WHERE id=?", (user_id,))
        conn.commit()
        conn.close()
        print(f"[INFO] Tool usage recorded: {tool_name} for user {user_id}")
    except Exception as e:
        print("[ERROR] Recording tool usage:", e)

# ------------------------
# Routes
# ------------------------
@flashcards_bp.route("/flashcards")
@login_required
def flashcards_page():
    return render_template("flashcards.html")


@flashcards_bp.route("/generate_flashcards", methods=["POST"])
@login_required
def generate_flashcards():
    data = request.get_json()
    text = data.get("text", "")
    if not text.strip():
        return jsonify({"flashcards": []})

    topic = generate_topic(text)
    main_points = extract_main_points(text, max_points=10)

    return jsonify({"flashcards": [{"topic": topic, "points": main_points}]})


@flashcards_bp.route("/save_flashcard", methods=["POST"])
@login_required
def save_flashcard():
    data = request.get_json()
    topic = data.get("topic", "")
    points = data.get("points", [])
    user_id = current_user.id  # use logged-in user

    if not topic or not points:
        return jsonify({"success": False, "msg": "Invalid flashcard"})

    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS flashcards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic TEXT,
                points TEXT
            )
        """)
        cur.execute("INSERT INTO flashcards (topic, points) VALUES (?, ?)", (topic, "\n".join(points)))
        conn.commit()
        conn.close()

        # Record tool usage
        record_tool_usage(user_id, "Flashcards")

        return jsonify({"success": True})
    except Exception as e:
        print("[ERROR] Saving flashcard:", e)
        return jsonify({"success": False, "msg": "Server error"})


@flashcards_bp.route("/get_flashcards")
@login_required
def get_flashcards():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, topic, points FROM flashcards")
    rows = cur.fetchall()
    flashcards = []
    for row in rows:
        points_list = [p.strip() for p in row[2].split("\n") if p.strip()]
        flashcards.append({
            "id": row[0],
            "topic": row[1],
            "points": points_list
        })
    conn.close()
    return jsonify({"flashcards": flashcards})


@flashcards_bp.route("/delete_flashcard/<int:fid>", methods=["DELETE"])
@login_required
def delete_flashcard(fid):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM flashcards WHERE id=?", (fid,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})
