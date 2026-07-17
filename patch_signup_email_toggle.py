"""
Patch script: add email validation + password show/hide toggle to signup.html
Mirrors the pattern already committed in login.html (commit 3504d18).

Run from repo root:
    python patch_signup_email_toggle.py
"""

import pathlib

FILE = pathlib.Path("static/signup.html")

text = FILE.read_text(encoding="utf-8")

# --- 1. Wrap the password input with an eye-toggle button ---------------

old_password_block = '''      <div class="field">
        <label for="signup-password">Password</label>
        <input type="password" id="signup-password" required autocomplete="new-password" minlength="8">
        <p class="hint">At least 8 characters</p>
      </div>'''

assert old_password_block in text, "signup-password field block not found — file may have changed"

new_password_block = '''      <div class="field">
        <label for="signup-password">Password</label>
        <div style="position: relative;">
          <input type="password" id="signup-password" required autocomplete="new-password" minlength="8" style="width: 100%; padding-right: 40px; box-sizing: border-box;">
          <button type="button" id="toggle-signup-password" aria-label="Show password" style="position: absolute; right: 8px; top: 50%; transform: translateY(-50%); background: none; border: none; cursor: pointer; padding: 4px; display: flex; align-items: center;">
            <svg id="signup-eye-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#16233E" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path>
              <circle cx="12" cy="12" r="3"></circle>
            </svg>
          </button>
        </div>
        <p class="hint">At least 8 characters</p>
      </div>'''

text = text.replace(old_password_block, new_password_block, 1)

# --- 2. Add the toggle click handler + email regex check in <script> ----

old_script_start = "document.getElementById('signup-form').addEventListener('submit', async (e) => {\n  e.preventDefault();"

assert old_script_start in text, "signup-form submit handler start not found"

new_script_start = '''document.getElementById('toggle-signup-password').addEventListener('click', () => {
  const pwInput = document.getElementById('signup-password');
  const eyeIcon = document.getElementById('signup-eye-icon');
  const toggleBtn = document.getElementById('toggle-signup-password');
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

document.getElementById('signup-form').addEventListener('submit', async (e) => {
  e.preventDefault();'''

text = text.replace(old_script_start, new_script_start, 1)

# --- 3. Insert email format check right after the year/semester check ----

old_validation_block = '''  if (!year || !semester) {
    msgEl.textContent = 'Please select your year and semester.';
    msgEl.className = 'message error';
    return;
  }'''

assert old_validation_block in text, "year/semester validation block not found"

new_validation_block = '''  const emailPattern = /^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$/;
  if (!emailPattern.test(email)) {
    msgEl.textContent = 'Please enter a complete email address (e.g. name@example.com).';
    msgEl.className = 'message error';
    return;
  }

  if (!year || !semester) {
    msgEl.textContent = 'Please select your year and semester.';
    msgEl.className = 'message error';
    return;
  }'''

text = text.replace(old_validation_block, new_validation_block, 1)

FILE.write_text(text, encoding="utf-8")
print("signup.html patched successfully.")
