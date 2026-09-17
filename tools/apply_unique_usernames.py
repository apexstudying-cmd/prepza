from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: Path, old: str, new: str) -> bool:
    text = path.read_text(encoding="utf-8")
    if new in text:
        return False
    if old not in text:
        raise SystemExit(f"Unique-username patch anchor missing: {path}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    return True


app = ROOT / "app.py"
replace_once(
    app,
    '    existing_user = User.query.filter_by(email=email).first()\n    if existing_user:\n        return jsonify({"error": "An account with this email already exists"}), 409\n',
    '    existing_user = User.query.filter_by(email=email).first()\n    if existing_user:\n        return jsonify({"error": "An account with this email already exists"}), 409\n\n    if display_name:\n        existing_name = User.query.filter(func.lower(User.display_name) == display_name.lower()).first()\n        if existing_name:\n            return jsonify({"error": "Username already taken. Please choose another."}), 409\n',
)

frontend = ROOT / "frontend/src/App.tsx"
replace_once(
    frontend,
    "  const steps = ['Name', 'Email', 'Password', 'University', 'Course', 'Year', 'Semester']\n",
    "  const steps = ['Username', 'Email', 'Password', 'University', 'Course', 'Year', 'Semester']\n",
)
replace_once(
    frontend,
    'placeholder="e.g. Arnold Gichuru" maxLength={50}',
    'placeholder="Choose a unique username" maxLength={50}',
)
replace_once(
    frontend,
    "if (step === 0 && !data.display_name.trim()) { setError('Please enter your name.'); return }",
    "if (step === 0 && !data.display_name.trim()) { setError('Please enter a username.'); return }",
)
