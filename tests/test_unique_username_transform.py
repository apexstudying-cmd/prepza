"""Guard the unique-username prebuild patch across inline and extracted Signup ownership."""

from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/apply_unique_usernames.py"

BACKEND_ANCHOR = (
    "    existing_user = User.query.filter_by(email=email).first()\n"
    "    if existing_user:\n"
    '        return jsonify({"error": "An account with this email already exists"}), 409\n'
)
BACKEND_PATCHED = (
    "    existing_user = User.query.filter_by(email=email).first()\n"
    "    if existing_user:\n"
    '        return jsonify({"error": "An account with this email already exists"}), 409\n\n'
    "    if display_name:\n"
    "        existing_name = User.query.filter(func.lower(User.display_name) == display_name.lower()).first()\n"
    "        if existing_name:\n"
    '            return jsonify({"error": "Username already taken. Please choose another."}), 409\n'
)
STEPS = "  const steps = ['Name', 'Email', 'Password', 'University', 'Course', 'Year', 'Semester']\n"
STEPS_PATCHED = "  const steps = ['Username', 'Email', 'Password', 'University', 'Course', 'Year', 'Semester']\n"
PLACEHOLDER = 'placeholder="e.g. Arnold Gichuru" maxLength={50}'
PLACEHOLDER_PATCHED = 'placeholder="Choose a unique username" maxLength={50}'
VALIDATION = "if (step === 0 && !data.display_name.trim()) { setError('Please enter your name.'); return }"
VALIDATION_PATCHED = "if (step === 0 && !data.display_name.trim()) { setError('Please enter a username.'); return }"


def prepare_fixture(root: Path, *, extracted: bool) -> tuple[Path, Path]:
    (root / "tools").mkdir()
    (root / "frontend/src/screens/auth").mkdir(parents=True)
    shutil.copyfile(SCRIPT, root / "tools/apply_unique_usernames.py")
    (root / "app.py").write_text(BACKEND_ANCHOR, encoding="utf-8")

    screen = STEPS + PLACEHOLDER + "\n" + VALIDATION
    if extracted:
        (root / "frontend/src/App.tsx").write_text(
            "import { SignupScreen } from './screens/auth/AuthScreens'\n"
            "case 'signup': return <SignupScreen setScreen={setScreen} />\n",
            encoding="utf-8",
        )
        (root / "frontend/src/screens/auth/AuthScreens.tsx").write_text(
            "export function SignupScreen() {\n" + screen + "\n}\n",
            encoding="utf-8",
        )
        return root / "app.py", root / "frontend/src/screens/auth/AuthScreens.tsx"

    (root / "frontend/src/App.tsx").write_text(
        "function SignupScreen() {\n" + screen + "\n}\n",
        encoding="utf-8",
    )
    return root / "app.py", root / "frontend/src/App.tsx"


def run_patch(root: Path) -> None:
    subprocess.run(
        [sys.executable, str(root / "tools/apply_unique_usernames.py")],
        cwd=root,
        check=True,
    )


def assert_patched(app_path: Path, screen_path: Path) -> None:
    backend = app_path.read_text(encoding="utf-8")
    screen = screen_path.read_text(encoding="utf-8")
    assert BACKEND_PATCHED in backend
    assert STEPS_PATCHED in screen
    assert PLACEHOLDER_PATCHED in screen
    assert VALIDATION_PATCHED in screen


def test_unique_username_patch_targets_extracted_signup_module_and_is_idempotent(tmp_path):
    app_path, screen_path = prepare_fixture(tmp_path, extracted=True)

    run_patch(tmp_path)
    assert_patched(app_path, screen_path)

    before = screen_path.read_text(encoding="utf-8")
    run_patch(tmp_path)
    assert screen_path.read_text(encoding="utf-8") == before


def test_unique_username_patch_retains_inline_signup_fallback(tmp_path):
    app_path, screen_path = prepare_fixture(tmp_path, extracted=False)

    run_patch(tmp_path)
    assert_patched(app_path, screen_path)

    before = screen_path.read_text(encoding="utf-8")
    run_patch(tmp_path)
    assert screen_path.read_text(encoding="utf-8") == before
