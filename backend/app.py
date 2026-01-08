from flask import Flask,g, render_template, request, jsonify, redirect, url_for
from flask_login import LoginManager, login_user, login_required, logout_user, current_user, UserMixin
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
from datetime import datetime, date
from video_summarizer import video_bp
from utils import record_tool_usage
from pdf_to_audio import pdf_bp
from flashcards import flashcards_bp
from study_planner import study_bp
from resources import resources_bp   

# 1️⃣ Define Flask app first
app = Flask(__name__)

DATABASE = "users.db"
DB_PATH = "database.db" 

def get_db():
    """Return a SQLite connection tied to Flask app context."""
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(exception):
    """Close the DB at the end of request."""
    db = g.pop('db', None)
    if db is not None:
        db.close()

# If you have these modules, keep them; otherwise ensure they exist
try:
    from summarizer import extract_text_from_pdf, summarize_text
except Exception:
    def extract_text_from_pdf(path): return ""
    def summarize_text(text, word_count=150): return "Summary placeholder."

try:
    from quiz_generator import generate_quiz
except Exception:
    def generate_quiz(topic, num_questions): return {"error": "quiz generator missing"}

# -------------------- App Setup --------------------
app = Flask(__name__)
app.secret_key = "your_secret_key_here"
app.register_blueprint(video_bp)
app.register_blueprint(pdf_bp)
app.register_blueprint(flashcards_bp)
app.register_blueprint(study_bp)
app.register_blueprint(resources_bp)
login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)

# -------------------- Folders & Config --------------------
DATABASE = "users.db"
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10 MB max file

# -------------------- User Model --------------------
class User(UserMixin):
    def __init__(self, id, name, email, password_hash, summarizer_count=0, quiz_count=0):
        self.id = id
        self.name = name
        self.email = email
        self.password_hash = password_hash
        self.summarizer_count = summarizer_count
        self.quiz_count = quiz_count

    @staticmethod
    def get(user_id):
        conn = sqlite3.connect(DATABASE)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT id, name, email, password_hash, COALESCE(summarizer_count,0) as summarizer_count, COALESCE(quiz_count,0) as quiz_count FROM users WHERE id = ?", (user_id,))
        row = cur.fetchone()
        conn.close()
        if row:
            return User(row["id"], row["name"], row["email"], row["password_hash"], row["summarizer_count"], row["quiz_count"])
        return None

    @staticmethod
    def get_by_email(email):
        conn = sqlite3.connect(DATABASE)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT id, name, email, password_hash, COALESCE(summarizer_count,0) as summarizer_count, COALESCE(quiz_count,0) as quiz_count FROM users WHERE email = ?", (email,))
        row = cur.fetchone()
        conn.close()
        if row:
            return User(row["id"], row["name"], row["email"], row["password_hash"], row["summarizer_count"], row["quiz_count"])
        return None

    @staticmethod
    def create(name, email, password):
        password_hash = generate_password_hash(password)
        conn = sqlite3.connect(DATABASE)
        cur = conn.cursor()
        cur.execute("INSERT INTO users (name, email, password_hash, summarizer_count, quiz_count) VALUES (?, ?, ?, 0, 0)",
                    (name, email, password_hash))
        conn.commit()
        user_id = cur.lastrowid
        conn.close()
        return User(user_id, name, email, password_hash, 0, 0)

@login_manager.user_loader
def load_user(user_id):
    return User.get(user_id)

# -------------------- DB Init --------------------
def init_db():
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()
    # users table with usage columns
    cur.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        summarizer_count INTEGER DEFAULT 0,
        quiz_count INTEGER DEFAULT 0,
        video_count INTEGER DEFAULT 0,
        audio_count INTEGER DEFAULT 0
    )
''')
    # login_activity: one row per login event
    cur.execute('''
        CREATE TABLE IF NOT EXISTS login_activity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            ts TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    ''')

    # quiz_attempts: store individual quiz attempts and score
    cur.execute('''
        CREATE TABLE IF NOT EXISTS quiz_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            score INTEGER NOT NULL,
            ts TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    ''')

    # tool_usage: generic tool usage events
    cur.execute('''
        CREATE TABLE IF NOT EXISTS tool_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            tool_name TEXT NOT NULL,
            ts TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    ''')
    # schedules: user's calendar items
    cur.execute('''
        CREATE TABLE IF NOT EXISTS schedules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            date TEXT NOT NULL,
            notes TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# -------------------- Utility functions --------------------
def record_login_activity(user_id):
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()
    cur.execute("INSERT INTO login_activity (user_id, ts) VALUES (?, ?)", (user_id, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

def record_tool_usage(user_id, tool_name):
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()
    cur.execute("INSERT INTO tool_usage (user_id, tool_name, ts) VALUES (?, ?, ?)", (user_id, tool_name, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()
    # increment users table counter if desired
    if tool_name.lower().startswith("pdf") or "summarizer" in tool_name.lower():
        conn = sqlite3.connect(DATABASE)
        cur = conn.cursor()
        cur.execute("UPDATE users SET summarizer_count = COALESCE(summarizer_count,0) + 1 WHERE id = ?", (user_id,))
        conn.commit()
        conn.close()
    if "quiz" in tool_name.lower():
        conn = sqlite3.connect(DATABASE)
        cur = conn.cursor()
        cur.execute("UPDATE users SET quiz_count = COALESCE(quiz_count,0) + 1 WHERE id = ?", (user_id,))
        conn.commit()
        conn.close()

def record_quiz_attempt(user_id, score, total_questions=None):
    conn = get_db()
    cur = conn.cursor()
    if total_questions is not None:
        cur.execute(
            "INSERT INTO quiz_attempts (user_id, score, total_questions, ts) VALUES (?, ?, ?, ?)",
            (user_id, score, total_questions, datetime.utcnow().isoformat())
        )
    else:
        cur.execute(
            "INSERT INTO quiz_attempts (user_id, score, ts) VALUES (?, ?, ?)",
            (user_id, score, datetime.utcnow().isoformat())
        )
    conn.commit()


# -------------------- Routes --------------------
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/dashboard")
@login_required
def dashboard():
    # record today's login/activity visit
    try:
        record_login_activity(current_user.id)
    except Exception:
        pass
    # Render dashboard page (counts will be fetched via AJAX)
    return render_template("dashboard.html", user_name=current_user.name)

@app.route("/api/dashboard_data")
@login_required
def api_dashboard_data():
    try:
        uid = current_user.id
        conn = get_db()
        cur = conn.cursor()

        # ----- Login activity -----
        cur.execute("SELECT ts FROM login_activity WHERE user_id = ?", (uid,))
        rows = cur.fetchall()
        login_dates = {}
        for r in rows:
            ts = r["ts"]
            if ts:
                d = ts[:10]
                login_dates[d] = login_dates.get(d, 0) + 1

        # ----- Quiz attempts -----
        cur.execute("PRAGMA table_info(quiz_attempts)")
        columns = [col["name"] for col in cur.fetchall()]
        has_total = "total_questions" in columns

        if has_total:
            cur.execute(
                "SELECT score, total_questions, ts FROM quiz_attempts WHERE user_id = ? ORDER BY ts ASC",
                (uid,)
            )
            quiz_rows = cur.fetchall()
            quiz_attempts = [{"score": r["score"], "total": r["total_questions"], "ts": r["ts"]} for r in quiz_rows]
        else:
            cur.execute(
                "SELECT score, ts FROM quiz_attempts WHERE user_id = ? ORDER BY ts ASC",
                (uid,)
            )
            quiz_rows = cur.fetchall()
            quiz_attempts = [{"score": r["score"], "total": 0, "ts": r["ts"]} for r in quiz_rows]

        # ----- Tool usage from DB -----
        # Fetch from tool_usage table
        cur.execute(
            "SELECT tool_name, COUNT(*) as cnt FROM tool_usage WHERE user_id = ? GROUP BY tool_name",
            (uid,)
        )
        tool_rows = cur.fetchall()
        tool_usage = {r["tool_name"]: r["cnt"] for r in tool_rows} if tool_rows else {}

        # Ensure all tools exist
        tools_list = ["PDF Summarizer", "Quiz Generator", "Video Summarizer", "PDF to Audio", "Flashcards","Adaptive Study Planner"]
        for tool in tools_list:
            if tool not in tool_usage:
                tool_usage[tool] = 0

        # ----- Schedules -----
        cur.execute(
            "SELECT id, title, date, notes, created_at FROM schedules WHERE user_id = ? ORDER BY date ASC",
            (uid,)
        )
        sched_rows = cur.fetchall()
        schedules = [
            {
                "id": r["id"],
                "title": r["title"],
                "date": r["date"],
                "notes": r["notes"] or "",
                "created_at": r["created_at"]
            } for r in sched_rows
        ] if sched_rows else []

        return jsonify({
            "login_activity": login_dates,
            "quiz_attempts": quiz_attempts,
            "tool_usage": tool_usage,  # PDF to Audio count will now show correctly
            "schedules": schedules,
            "user_name": getattr(current_user, "name", "User")
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# Route to record quiz attempt (call from your quiz submission JS)
@app.route('/record_quiz_attempt', methods=['POST'])
@login_required
def record_quiz_attempt():
    try:
        # Force parse JSON even if headers are off
        data = request.get_json(force=True)
        print(f"[INFO] POST /record_quiz_attempt received: {data}")

        score = data.get('score')
        total_questions = data.get('total_questions')

        if score is None or total_questions is None:
            return jsonify({"error": "Missing score or total_questions"}), 400

        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO quiz_attempts (user_id, score, total_questions, ts) VALUES (?, ?, ?, ?)",
            (current_user.id, score, total_questions, datetime.utcnow().isoformat())
        )
        conn.commit()
        print(f"[INFO] Quiz attempt recorded for user {current_user.id} | Score: {score}/{total_questions}")
        return jsonify({"message": "Quiz attempt recorded successfully"})
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# Route to add schedule entry
@app.route("/add_schedule", methods=["POST"])
@login_required
def add_schedule():
    title = request.form.get("title", "").strip()
    date_str = request.form.get("date", "").strip()  # expected YYYY-MM-DD
    notes = request.form.get("notes", "").strip()
    if not title or not date_str:
        return redirect(url_for("dashboard"))
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()
    cur.execute("INSERT INTO schedules (user_id, title, date, notes, created_at) VALUES (?, ?, ?, ?, ?)",
                (current_user.id, title, date_str, notes, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()
    return redirect(url_for("dashboard"))

# -------------------- Existing features kept intact --------------------
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name = request.form.get("name").strip()
        email = request.form.get("email").strip().lower()
        password = request.form.get("password")
        confirm_password = request.form.get("confirm_password")

        if not name or not email or not password or not confirm_password:
            return "Please fill all fields", 400
        if password != confirm_password:
            return "Passwords do not match", 400
        if User.get_by_email(email):
            return "Email already registered", 400

        user = User.create(name, email, password)
        login_user(user)
        return redirect(url_for("dashboard"))
    return render_template("signup.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email").strip().lower()
        password = request.form.get("password")
        user = User.get_by_email(email)
        if not user or not check_password_hash(user.password_hash, password):
            return "Invalid credentials", 400
        login_user(user)
        # record login activity here as well
        try:
            record_login_activity(user.id)
        except Exception:
            pass
        return redirect(url_for("dashboard"))
    return render_template("login.html")

@app.route("/features")
def features():
    return render_template("features.html")

@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/contact")
def contact():
    return render_template("contact.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("index"))

@app.route("/summarizer_tool")
@login_required
def summarizer_page():
    return render_template("summarizer.html", user_name=current_user.name)

@app.route("/summarize", methods=["POST"])
@login_required
def summarize():
    try:
        if "pdf_file" not in request.files:
            return jsonify({"error": "No PDF file uploaded"}), 400

        file = request.files["pdf_file"]
        if file.filename == "":
            return jsonify({"error": "No file selected"}), 400

        # Save file temporarily
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(file_path)

        # Get word limit
        word_limit = request.form.get("word_limit", 150)
        try:
            word_limit = int(word_limit)
        except:
            word_limit = 150

        # Extract text and summarize
        text = extract_text_from_pdf(file_path)
        summary = summarize_text(text, word_count=word_limit)

        # Increment usage counter and record tool usage
        conn = sqlite3.connect(DATABASE)
        cur = conn.cursor()
        cur.execute("UPDATE users SET summarizer_count = COALESCE(summarizer_count,0) + 1 WHERE id = ?", (current_user.id,))
        conn.commit()
        conn.close()
        record_tool_usage(current_user.id, "PDF Summarizer")

        # Clean up uploaded file
        if os.path.exists(file_path):
            os.remove(file_path)

        return jsonify({"summary": summary})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/quiz_tool")
@login_required
def quiz_tool():
    return render_template("quiz_tool.html", user_name=current_user.name)

# -------------------- Generate Quiz API --------------------
@app.route("/generate_quiz", methods=["POST"])
@login_required
def generate_quiz_route():
    topic = request.form.get("topic")
    num_questions = int(request.form.get("num_questions", 5))

    quiz = generate_quiz(topic, num_questions)
    if "error" in quiz:
        return jsonify({"error": quiz["error"]}), 400

    # Update quiz_count in DB and record tool usage (we still keep this)
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()
    cur.execute("UPDATE users SET quiz_count = COALESCE(quiz_count,0) + 1 WHERE id = ?", (current_user.id,))
    conn.commit()
    conn.close()
    record_tool_usage(current_user.id, "Quiz Generator")

    return jsonify({"quiz": quiz})


# PDF Summarizer page
@app.route("/pdf_summarizer")
@login_required
def pdf_summarizer():
    return render_template("summarizer.html", user_name=current_user.name)

# Quiz Generator page
@app.route("/quiz_generator")
@login_required
def quiz_generator():
    return render_template("quiz_tool.html", user_name=current_user.name)

def record_tool_usage(user_id, tool_name):
    """Record a tool usage in the tool_usage table."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO tool_usage (user_id, tool_name, ts)
            VALUES (?, ?, ?)
        """, (user_id, tool_name, datetime.now()))
        conn.commit()
        conn.close()
        print(f"[INFO] Tool usage recorded: {tool_name} by user {user_id}")
    except Exception as e:
        print("Error recording tool usage:", e)

# -------------------- Calendar (FullCalendar) API --------------------
@app.route("/get_events")
@login_required
def get_events():
    """Return all events for the logged-in user."""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT id, title, date, notes FROM schedules WHERE user_id = ?", (current_user.id,))
    rows = cur.fetchall()
    conn.close()

    events = []
    for r in rows:
        events.append({
            "id": r["id"],
            "title": r["title"],
            "start": r["date"],  # FullCalendar expects 'start'
            "description": r["notes"]
        })
    return jsonify(events)


@app.route("/add_event", methods=["POST"])
@login_required
def add_event():
    """Add a new event to the schedules table."""
    data = request.get_json()
    title = data.get("title")
    start = data.get("start")
    notes = data.get("description", "")

    if not title or not start:
        return jsonify({"error": "Missing title or date"}), 400

    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO schedules (user_id, title, date, notes, created_at) VALUES (?, ?, ?, ?, ?)",
        (current_user.id, title, start, notes, datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()
    return jsonify({"message": "Event added successfully"})


# -------------------- Run App --------------------
if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)
