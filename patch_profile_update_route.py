"""
Patch script: adds a PATCH /profile route so logged-in users can update
their year and semester (e.g. after a real user had none set, or after
a semester ends).

Run from repo root:
    python patch_profile_update_route.py
"""

import pathlib

FILE = pathlib.Path("app.py")

text = FILE.read_text(encoding="utf-8")

anchor = '''@app.route("/me")
def me():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    user = User.query.get(user_id)
    return jsonify({
        "id": user.id,
        "email": user.email,
        "year": user.year,
        "semester": user.semester,
        "email_verified": user.email_verified,
    })
'''

assert text.count(anchor) == 1, (
    f"Expected exactly 1 occurrence of the /me route block, found {text.count(anchor)} — "
    "file may have changed. Stopping without changes."
)

new_route = anchor + '''

@app.route("/profile", methods=["PATCH"])
def update_profile():
    """
    Lets a logged-in student update their own year and semester -
    e.g. a real account that never had them set, or a student moving
    on to a new semester. Uses the same validation rules as /signup.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    year = data.get("year")
    semester = data.get("semester")

    if year is None or semester is None:
        return jsonify({"error": "year and semester are both required"}), 400

    if not isinstance(year, int) or year < 1 or year > 4:
        return jsonify({"error": "Year must be a number between 1 and 4"}), 400

    if not isinstance(semester, int) or semester not in (1, 2):
        return jsonify({"error": "Semester must be 1 or 2"}), 400

    user = User.query.get(user_id)
    user.year = year
    user.semester = semester
    db.session.commit()

    return jsonify({
        "message": "Profile updated",
        "year": user.year,
        "semester": user.semester,
    })
'''

text = text.replace(anchor, new_route, 1)

FILE.write_text(text, encoding="utf-8")
print("app.py patched successfully - added PATCH /profile route.")
