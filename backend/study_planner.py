from flask import Blueprint, render_template, request, jsonify
from flask_login import current_user, login_required
import sqlite3, datetime

study_bp = Blueprint('study_bp', __name__)
DATABASE = "users.db"

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

# ---------- PAGE ----------
@study_bp.route('/study_planner')
@login_required
def study_planner():
    return render_template('study_planner.html')

# ---------- GENERATE PLAN ----------
@study_bp.route('/generate_plan', methods=['POST'])
@login_required
def generate_plan():
    data = request.get_json()
    subjects = [s.strip() for s in data.get('subjects', [])]
    knowledge_levels = [k.strip().lower() for k in data.get('knowledge', [])]
    available_hours = float(data.get('available_hours', 3))
    preferred_hours = data.get('preferred_hours', '18:00-21:00')
    breaks_pref = data.get('breaks', '10 mins after every hour')
    mode = data.get('mode', 'Weekly')
    deadline_str = data.get('deadline', None)

    # Parse preferred hours
    try:
        start_hour, end_hour = [int(h.split(':')[0]) for h in preferred_hours.split('-')]
    except:
        start_hour, end_hour = 18, 21

    # Parse break duration
    try:
        break_mins = int(breaks_pref.split()[0])
    except:
        break_mins = 10

    # Weight subjects
    weight_map = {'beginner': 1.5, 'intermediate': 1.0, 'advanced': 0.5}
    weights = [weight_map.get(k, 1.0) for k in knowledge_levels]
    total_weight = sum(weights) or 1
    time_per_subject = [available_hours * 60 * (w / total_weight) for w in weights]  # in minutes

    today = datetime.date.today()

    # Days list
    if mode.lower() == "weekly":
        monday = today - datetime.timedelta(days=today.weekday())
        days = [monday + datetime.timedelta(days=i) for i in range(7)]
    elif mode.lower() == "deadline" and deadline_str:
        try:
            deadline = datetime.datetime.strptime(deadline_str, "%Y-%m-%d").date()
        except ValueError:
            deadline = today
        days = [today + datetime.timedelta(days=i) for i in range((deadline - today).days + 1)]
    else:
        days = [today]

    plan = []
    for day in days:
        current_time = start_hour * 60
        day_tasks = []
        remaining = time_per_subject.copy()

        while any(r > 0 for r in remaining) and current_time < end_hour * 60:
            for i, subj in enumerate(subjects):
                if remaining[i] <= 0 or current_time >= end_hour * 60:
                    continue
                study_block = min(50, int(remaining[i]), end_hour*60 - current_time)
                end_time = current_time + study_block
                day_tasks.append({
                    "time": f"{current_time//60:02d}:{current_time%60:02d} - {end_time//60:02d}:{end_time%60:02d}",
                    "subject": subj
                })
                current_time = end_time
                remaining[i] -= study_block

                # Break
                if current_time + break_mins <= end_hour*60:
                    day_tasks.append({
                        "time": f"{current_time//60:02d}:{current_time%60:02d} - {(current_time + break_mins)//60:02d}:{(current_time + break_mins)%60:02d}",
                        "subject": "Break"
                    })
                    current_time += break_mins

        # Deadline review
        if mode.lower() == "deadline" and day == days[-1] and current_time < end_hour*60:
            day_tasks.append({
                "time": f"{current_time//60:02d}:{current_time%60:02d} - {end_hour:02d}:00",
                "subject": "Deadline Review"
            })

        plan.append({"date": day.strftime('%A, %d-%m-%Y'), "tasks": day_tasks})

    # -------------------- RECORD TOOL USAGE --------------------
    try:
        conn = get_db()
        cur = conn.cursor()
        # Insert into tool_usage table
        cur.execute("""
            INSERT INTO tool_usage (user_id, tool_name, ts)
            VALUES (?, ?, ?)
        """, (current_user.id, "Adaptive Study Planner", datetime.datetime.utcnow().isoformat()))
        
        # Increment study_planner_count
        cur.execute("""
            UPDATE users 
            SET study_planner_count = COALESCE(study_planner_count, 0) + 1 
            WHERE id = ?
        """, (current_user.id,))
        conn.commit()
        conn.close()
        print(f"[INFO] Adaptive Study Planner usage recorded for user {current_user.id}")
    except Exception as e:
        print("Error recording study planner usage:", e)

    return jsonify({"plan": plan})
