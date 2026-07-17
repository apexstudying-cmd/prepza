"""
Fix script: removes the duplicated emailPattern validation block in signup.html
(caused by the previous patch script being run twice).

Run from repo root:
    python fix_duplicate_emailpattern.py
"""

import pathlib

FILE = pathlib.Path("static/signup.html")

text = FILE.read_text(encoding="utf-8")

duplicated = '''const emailPattern = /^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$/;
  if (!emailPattern.test(email)) {
    msgEl.textContent = 'Please enter a complete email address (e.g. name@example.com).';
    msgEl.className = 'message error';
    return;
  }
  const emailPattern = /^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$/;
  if (!emailPattern.test(email)) {
    msgEl.textContent = 'Please enter a complete email address (e.g. name@example.com).';
    msgEl.className = 'message error';
    return;
  }'''

assert text.count(duplicated) == 1, (
    f"Expected exactly 1 occurrence of the duplicated block, found {text.count(duplicated)}. "
    "File may already be fixed, or differ from what was expected — stopping without changes."
)

single = '''const emailPattern = /^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$/;
  if (!emailPattern.test(email)) {
    msgEl.textContent = 'Please enter a complete email address (e.g. name@example.com).';
    msgEl.className = 'message error';
    return;
  }'''

text = text.replace(duplicated, single, 1)

FILE.write_text(text, encoding="utf-8")
print("Duplicate emailPattern block removed successfully.")
