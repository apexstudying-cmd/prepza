"""
Diagnostic - prints exact repr() of the regions patch_add_chat_backend.py
needs to anchor on, straight from your real app.py. Run this and paste
the full output back - do not summarize or retype it, copy-paste the
raw output exactly as printed.

Usage:
    python diagnose_chat_patch_anchors.py
"""

with open("app.py", "r", encoding="utf-8", newline="") as f:
    raw = f.read()

content = raw.replace("\r\n", "\n")
lines = content.split("\n")

print("=" * 70)
print("Searching for models insertion point (near AiUsageLog / mpesa)")
print("=" * 70)

hits = [i for i, l in enumerate(lines) if "class AiUsageLog" in l]
if not hits:
    print("class AiUsageLog NOT FOUND. Searching for last class before "
          "get_mpesa_access_token instead...")
    mpesa_hits = [i for i, l in enumerate(lines) if "def get_mpesa_access_token" in l]
    if mpesa_hits:
        idx = mpesa_hits[0]
        print(f"def get_mpesa_access_token found at line {idx}")
        print("--- 20 lines before it ---")
        print(repr("\n".join(lines[max(0, idx - 20):idx + 1])))
    else:
        print("get_mpesa_access_token NOT FOUND either. Printing all class "
              "definitions in the file so we can find the right anchor:")
        for i, l in enumerate(lines):
            if l.startswith("class "):
                print(i, l)
else:
    idx = hits[0]
    print(f"class AiUsageLog found at line {idx}")
    end = idx
    while end < len(lines) and (lines[end].startswith("class ") or lines[end].startswith("    ") or lines[end].strip() == ""):
        end += 1
        if end - idx > 25:
            break
    print("--- class AiUsageLog through the next ~5 lines ---")
    print(repr("\n".join(lines[idx:end + 5])))

print()
print("=" * 70)
print("Searching for routes insertion point (near ResultCode Accepted / Admin routes)")
print("=" * 70)

hits2 = [i for i, l in enumerate(lines) if "ResultDesc" in l and "Accepted" in l]
if not hits2:
    print("'ResultDesc...Accepted' line NOT FOUND. Searching for "
          "'# ---------- Admin routes' instead:")
    admin_hits = [i for i, l in enumerate(lines) if "Admin routes" in l]
    if admin_hits:
        idx2 = admin_hits[0]
        print(f"Admin routes section header found at line {idx2}")
        print("--- 10 lines before it ---")
        print(repr("\n".join(lines[max(0, idx2 - 10):idx2 + 1])))
    else:
        print("Admin routes section header NOT FOUND either. Printing all "
              "'# ----------' section headers in the file:")
        for i, l in enumerate(lines):
            if l.startswith("# ----------"):
                print(i, l)
else:
    idx2 = hits2[0]
    print(f"'ResultDesc...Accepted' found at line {idx2}")
    print("--- that line through 5 lines after ---")
    print(repr("\n".join(lines[idx2:idx2 + 6])))
