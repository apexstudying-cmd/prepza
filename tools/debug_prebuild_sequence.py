from pathlib import Path
import json
import subprocess

ROOT = Path(__file__).resolve().parents[1]
FRONT = ROOT / "frontend"
pkg = json.loads((FRONT / "package.json").read_text())
commands = [part.strip() for part in pkg["scripts"]["prebuild"].split("&&")]

for index, command in enumerate(commands, 1):
    print(f"\n=== PREBUILD {index}/{len(commands)}: {command} ===", flush=True)
    result = subprocess.run(command, shell=True, cwd=FRONT)
    if result.returncode:
        raise SystemExit(result.returncode)
    app = (FRONT / "src/App.tsx").read_text(encoding="utf-8")
    if "pasted.trim()" in app:
        lines = app.splitlines()
        hits = [i for i, line in enumerate(lines, 1) if "pasted.trim()" in line]
        print("OTP_FRAGMENT_INTRODUCED_BY:", command)
        for line_no in hits:
            print("\n".join(f"{n}: {lines[n-1]}" for n in range(max(1,line_no-3), min(len(lines),line_no+3)+1)))
        raise SystemExit(91)

print("PREBUILD_SEQUENCE_COMPLETE")
