from flask import Blueprint, render_template, request, jsonify, session

resources_bp = Blueprint("resources_bp", __name__)

# Dummy AI resource generator (replace with real AI logic later)
def generate_resources(topic, level):
    resources = [
        {"title": f"{topic} - Beginner Guide", "url": "https://example.com/article1", "type": "Article", "level": level},
        {"title": f"{topic} Tutorial Video", "url": "https://youtube.com/example1", "type": "Video", "level": level},
        {"title": f"Advanced {topic} Concepts", "url": "https://example.com/article2", "type": "Article", "level": level},
        {"title": f"{topic} YouTube Deep Dive", "url": "https://youtube.com/example2", "type": "Video", "level": level},
    ]
    return resources

# Route to view AI Resource Tool page
@resources_bp.route("/resources")
def resources():
    return render_template("resources.html")

# Route to fetch AI resources (AJAX)
@resources_bp.route("/get_resources", methods=["POST"])
def get_resources():
    data = request.get_json()
    topic = data.get("topic", "")
    level = data.get("level", "beginner")
    resources = generate_resources(topic, level)
    return jsonify(resources)

# Route to save bookmarked resources in session
@resources_bp.route("/save_bookmark", methods=["POST"])
def save_bookmark():
    data = request.get_json()
    bookmark = data.get("bookmark")
    if "bookmarks" not in session:
        session["bookmarks"] = []
    session["bookmarks"].append(bookmark)
    session.modified = True
    return jsonify({"status": "success", "bookmarks": session["bookmarks"]})

# Route to fetch saved bookmarks
@resources_bp.route("/get_bookmarks")
def get_bookmarks():
    return jsonify(session.get("bookmarks", []))
