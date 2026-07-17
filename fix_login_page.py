"""
Patch script: add email validation + password show/hide toggle to login.html

This makes THREE changes to static/login.html:
  1. Fixes showMessage() so error messages actually become visible
     (it was setting text/class but never un-hiding the box).
  2. Wraps the password input in a container with a clickable eye icon
     that toggles between hidden (dots) and visible (plain text) password.
  3. Adds a client-side check that rejects incomplete emails (e.g. missing
     ".com") with a clear message, instead of silently sending them to the
     server and getting a confusing "wrong password" error back.

Every replacement is guarded by an assert: if the expected original text
isn't found (e.g. because the file has already been patched, or differs
from what we expect), the script stops immediately and changes NOTHING.
Safe to inspect with `git diff` afterward, and safe to re-run --
it will simply refuse to apply a patch twice.

Usage:
    cd ~/Desktop/prepza
    python fix_login_page.py
"""

import pathlib

LOGIN_FILE = pathlib.Path("static/login.html")


def apply_replacement(text, old, new, label):
    count = text.count(old)
    assert count != 0, (
        f"[{label}] Could not find the expected original text in login.html.\n"
        "Nothing was changed. This usually means the file already differs "
        "from what this script expects (e.g. it was already patched, or "
        "edited by hand) -- let's look at it together before proceeding.\n\n"
        f"Expected to find:\n{old}"
    )
    assert count == 1, (
        f"[{label}] Expected exactly ONE match, but found {count}. "
        "Refusing to guess which one to change."
    )
    return text.replace(old, new)


def main():
    if not LOGIN_FILE.exists():
        raise SystemExit(
            "ERROR: static/login.html not found.\n"
            "Make sure you're in ~/Desktop/prepza before running this "
            "(run 'cd ~/Desktop/prepza' first)."
        )

    text = LOGIN_FILE.read_text(encoding="utf-8")

    # --- Change 1: fix showMessage() to actually reveal the message box ---
    old_show_message = """function showMessage(elId, text, type) {
  const el = document.getElementById(elId);
  el.textContent = text;
  el.className = 'message ' + type;
}"""
    new_show_message = """function showMessage(elId, text, type) {
  const el = document.getElementById(elId);
  el.textContent = text;
  el.className = 'message ' + type;
  el.style.display = 'block';
}"""
    text = apply_replacement(text, old_show_message, new_show_message, "showMessage fix")

    # --- Change 2: wrap password input with eye-toggle button ---
    old_password_field = """      <div class="field">
        <label for="login-password">Password</label>
        <input type="password" id="login-password" required autocomplete="current-password">
      </div>"""
    new_password_field = """      <div class="field">
        <label for="login-password">Password</label>
        <div style="position: relative;">
          <input type="password" id="login-password" required autocomplete="current-password" style="width: 100%; padding-right: 40px; box-sizing: border-box;">
          <button type="button" id="toggle-login-password" aria-label="Show password" style="position: absolute; right: 8px; top: 50%; transform: translateY(-50%); background: none; border: none; cursor: pointer; padding: 4px; display: flex; align-items: center;">
            <svg id="login-eye-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#16233E" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path>
              <circle cx="12" cy="12" r="3"></circle>
            </svg>
          </button>
        </div>
      </div>"""
    text = apply_replacement(text, old_password_field, new_password_field, "password eye-toggle HTML")

    # --- Change 3: add toggle JS + email-format validation in submit handler ---
    old_submit_start = """document.getElementById('login-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const email = document.getElementById('login-email').value.trim();
  const password = document.getElementById('login-password').value;
  const submitBtn = document.getElementById('login-submit');
  const msgEl = document.getElementById('login-message');
  msgEl.style.display = 'none';"""
    new_submit_start = """document.getElementById('toggle-login-password').addEventListener('click', () => {
  const pwInput = document.getElementById('login-password');
  const eyeIcon = document.getElementById('login-eye-icon');
  const toggleBtn = document.getElementById('toggle-login-password');
  if (pwInput.type === 'password') {
    pwInput.type = 'text';
    toggleBtn.setAttribute('aria-label', 'Hide password');
    eyeIcon.innerHTML = '<path d="M17.94 17.94A10.94 10.94 0 0 1 12 20c-7 0-11-8-11-8a18.5 18.5 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"></path><line x1="1" y1="1" x2="23" y2="23"></line>';
  } else {
    pwInput.type = 'password';
    toggleBtn.setAttribute('aria-label', 'Show password');
    eyeIcon.innerHTML = '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle>';
  }
});

document.getElementById('login-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const email = document.getElementById('login-email').value.trim();
  const password = document.getElementById('login-password').value;
  const submitBtn = document.getElementById('login-submit');
  const msgEl = document.getElementById('login-message');
  msgEl.style.display = 'none';

  const emailPattern = /^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$/;
  if (!emailPattern.test(email)) {
    showMessage('login-message', 'Please enter a complete email address (e.g. name@example.com).', 'error');
    return;
  }"""
    text = apply_replacement(text, old_submit_start, new_submit_start, "submit handler + email validation")

    LOGIN_FILE.write_text(text, encoding="utf-8")

    print("✅ Patched static/login.html successfully.")
    print("   1. showMessage() now un-hides the message box")
    print("   2. Password field now has a show/hide eye toggle")
    print("   3. Malformed emails are now rejected before hitting the server")
    print()
    print("Next steps:")
    print("  1. Review the change:  git diff static/login.html")
    print("  2. Test locally: python app.py, then open")
    print("     http://127.0.0.1:5000/static/login.html")
    print("       - try a malformed email (e.g. test@gmail) -> should show a message")
    print("       - click the eye icon -> password should toggle visible/hidden")
    print("  3. If it all works, commit:")
    print("     git add static/login.html")
    print("     git commit -m 'Add email validation and password toggle to login'")
    print("     git push")


if __name__ == "__main__":
    main()
