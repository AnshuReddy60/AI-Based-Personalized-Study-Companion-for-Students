import sqlite3
from datetime import datetime
from flask import current_app

DB_PATH = "users.db"

def record_tool_usage(user_id, tool_name):
    """Record a tool usage in the tool_usage table and update counters."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        # Insert into tool_usage table
        cur.execute("""
            INSERT INTO tool_usage (user_id, tool_name, ts)
            VALUES (?, ?, ?)
        """, (user_id, tool_name, datetime.utcnow().isoformat()))
        conn.commit()

        # Increment usage counters in users table
        tool_name_lower = tool_name.lower()
        if "pdf" in tool_name_lower and "audio" not in tool_name_lower:
            cur.execute("UPDATE users SET summarizer_count = COALESCE(summarizer_count,0)+1 WHERE id=?", (user_id,))
        elif "pdf" in tool_name_lower and "audio" in tool_name_lower:
            cur.execute("UPDATE users SET audio_count = COALESCE(audio_count,0)+1 WHERE id=?", (user_id,))
        elif "quiz" in tool_name_lower:
            cur.execute("UPDATE users SET quiz_count = COALESCE(quiz_count,0)+1 WHERE id=?", (user_id,))
        elif "video" in tool_name_lower:
            cur.execute("UPDATE users SET video_count = COALESCE(video_count,0)+1 WHERE id=?", (user_id,))
        elif "flashcards" in tool_name_lower:
            cur.execute("UPDATE users SET flashcards_count = COALESCE(flashcards_count,0)+1 WHERE id=?", (user_id,))
        elif "study_planner" in tool_name_lower or "adaptive study planner" in tool_name_lower:
            cur.execute("UPDATE users SET study_planner_count = COALESCE(study_planner_count,0)+1 WHERE id=?", (user_id,))

        conn.commit()
        conn.close()
        print(f"[INFO] Tool usage recorded: {tool_name} for user {user_id}")

    except Exception as e:
        print("Error recording tool usage:", e)
