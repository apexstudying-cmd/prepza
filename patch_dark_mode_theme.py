"""
Patch script - Stage 2: adds a site-wide dark/light theme mechanism to
every existing frontend page (login, signup, dashboard, unit, viewer).

What this does, per file:
  1. Inserts a tiny inline script at the very top of <head> that reads
     the saved theme ('light' or 'dark') from localStorage and sets it
     on <html data-theme="..."> BEFORE the page paints, avoiding a flash
     of the wrong theme.
  2. Adds a [data-theme="dark"] CSS variable override block, reusing
     the exact same variable names each page already defines in :root,
     so all existing component styles pick up the dark palette for free.
  3. Adds a few small targeted dark-mode overrides for hardcoded colors
     that aren't driven by CSS variables (input backgrounds, chip
     backgrounds, modal backgrounds).

Also fixes a small pre-existing bug in dashboard.html: the "not logged
in" redirect pointed to '/login.html' instead of '/static/login.html'.

viewer.html intentionally keeps its PDF page canvas white in dark mode -
that's the actual document content, not UI chrome, so it stays as-is.

The actual light/dark TOGGLE control lives in settings.html (added in
Stage 3) - this script only lays the groundwork so every page responds
correctly once that toggle writes to localStorage.

Run from repo root:
    python patch_dark_mode_theme.py
"""

import pathlib

THEME_INIT_OLD = '''<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">'''

THEME_INIT_NEW = '''<meta charset="UTF-8">
<script>
(function() {
  var theme = localStorage.getItem('prepza-theme') || 'light';
  document.documentElement.setAttribute('data-theme', theme);
})();
</script>
<meta name="viewport" content="width=device-width, initial-scale=1.0">'''

DARK_ROOT_BLOCK_WITH_CARD = '''

  [data-theme="dark"] {
    --navy: #2C3E63;
    --navy-dark: #1B2A47;
    --gold: #D4AF37;
    --crimson: #E0576F;
    --page-bg: #14181F;
    --card-bg: #1E232D;
    --border: #323A48;
    --text-primary: #E8EAED;
    --text-secondary: #A8AFBC;
    --text-muted: #6B7280;
  }'''

DARK_ROOT_BLOCK_NO_CARD = '''

  [data-theme="dark"] {
    --navy: #2C3E63;
    --navy-dark: #1B2A47;
    --gold: #D4AF37;
    --crimson: #E0576F;
    --page-bg: #14181F;
    --border: #323A48;
    --text-primary: #E8EAED;
    --text-secondary: #A8AFBC;
    --text-muted: #6B7280;
  }'''

ROOT_BLOCK_STANDARD = '''  :root {
    --navy: #16233E;
    --navy-dark: #0F1929;
    --gold: #C9A227;
    --crimson: #8C1D2B;
    --page-bg: #F4F5F7;
    --card-bg: #FFFFFF;
    --border: #E2E4E9;
    --text-primary: #16233E;
    --text-secondary: #5B6478;
    --text-muted: #8B93A3;
  }'''

ROOT_BLOCK_VIEWER = '''  :root {
    --navy: #16233E;
    --navy-dark: #0F1929;
    --gold: #C9A227;
    --crimson: #8C1D2B;
    --page-bg: #EDEEF1;
    --border: #E2E4E9;
    --text-primary: #16233E;
    --text-secondary: #5B6478;
    --text-muted: #8B93A3;
  }'''


def apply_common_edits(path, root_block, dark_block, extra_dark_css=""):
    text = path.read_text(encoding="utf-8")

    assert text.count(THEME_INIT_OLD) == 1, f"{path}: theme-init anchor not found or not unique"
    text = text.replace(THEME_INIT_OLD, THEME_INIT_NEW, 1)

    assert text.count(root_block) == 1, f"{path}: :root block not found or not unique"
    text = text.replace(root_block, root_block + dark_block, 1)

    if extra_dark_css:
        assert text.count("</style>") == 1, f"{path}: </style> not found or not unique"
        text = text.replace("</style>", extra_dark_css + "\n</style>", 1)

    path.write_text(text, encoding="utf-8")
    print(f"{path}: patched.")


# --- login.html -----------------------------------------------------------
apply_common_edits(
    pathlib.Path("static/login.html"),
    ROOT_BLOCK_STANDARD,
    DARK_ROOT_BLOCK_WITH_CARD,
    extra_dark_css='''
  [data-theme="dark"] input {
    background: var(--card-bg);
    color: var(--text-primary);
  }
  [data-theme="dark"] input:focus {
    background: var(--card-bg);
  }''',
)

# --- signup.html ------------------------------------------------------------
apply_common_edits(
    pathlib.Path("static/signup.html"),
    ROOT_BLOCK_STANDARD,
    DARK_ROOT_BLOCK_WITH_CARD,
    extra_dark_css='''
  [data-theme="dark"] input,
  [data-theme="dark"] select {
    background: var(--card-bg);
    color: var(--text-primary);
  }
  [data-theme="dark"] input:focus,
  [data-theme="dark"] select:focus {
    background: var(--card-bg);
  }''',
)

# --- dashboard.html ---------------------------------------------------------
dashboard_path = pathlib.Path("static/dashboard.html")
apply_common_edits(
    dashboard_path,
    ROOT_BLOCK_STANDARD,
    DARK_ROOT_BLOCK_WITH_CARD,
    extra_dark_css='''
  [data-theme="dark"] .unit-code {
    background: rgba(255, 255, 255, 0.08);
  }''',
)

# Fix pre-existing bug: both redirects (401 handler, and logout handler)
# should go to /static/login.html, not /login.html
dash_text = dashboard_path.read_text(encoding="utf-8")

redirect_401_old = "    if (meRes.status === 401) {\n      window.location.href = '/login.html';\n      return;\n    }"
redirect_401_new = "    if (meRes.status === 401) {\n      window.location.href = '/static/login.html';\n      return;\n    }"
assert dash_text.count(redirect_401_old) == 1, "dashboard.html: 401 redirect block not found or not unique"
dash_text = dash_text.replace(redirect_401_old, redirect_401_new, 1)

redirect_logout_old = "  await fetch('/logout', { method: 'POST' });\n  window.location.href = '/login.html';"
redirect_logout_new = "  await fetch('/logout', { method: 'POST' });\n  window.location.href = '/static/login.html';"
assert dash_text.count(redirect_logout_old) == 1, "dashboard.html: logout redirect block not found or not unique"
dash_text = dash_text.replace(redirect_logout_old, redirect_logout_new, 1)

dashboard_path.write_text(dash_text, encoding="utf-8")
print(f"{dashboard_path}: fixed both /login.html -> /static/login.html redirect bugs.")

# --- unit.html ---------------------------------------------------------------
apply_common_edits(
    pathlib.Path("static/unit.html"),
    ROOT_BLOCK_STANDARD,
    DARK_ROOT_BLOCK_WITH_CARD,
    extra_dark_css='''
  [data-theme="dark"] .unit-code-chip {
    background: rgba(255, 255, 255, 0.08);
  }
  [data-theme="dark"] .modal {
    background: var(--card-bg);
  }
  [data-theme="dark"] .modal input {
    background: var(--page-bg);
    color: var(--text-primary);
  }''',
)

# --- viewer.html ---------------------------------------------------------------
# Deliberately no extra_dark_css here: the PDF page canvas stays white on
# purpose (it's the actual document content, not UI chrome).
apply_common_edits(
    pathlib.Path("static/viewer.html"),
    ROOT_BLOCK_VIEWER,
    DARK_ROOT_BLOCK_NO_CARD,
)

print("\nAll 5 pages patched successfully with the dark/light theme mechanism.")
