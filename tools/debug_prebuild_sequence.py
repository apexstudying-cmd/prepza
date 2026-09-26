from pathlib import Path
import json, subprocess
root=Path(__file__).resolve().parents[1]; front=root/'frontend'
cmds=[x.strip() for x in json.loads((front/'package.json').read_text())['scripts']['prebuild'].split('&&')]
for i,cmd in enumerate(cmds,1):
    r=subprocess.run(cmd,shell=True,cwd=front)
    if r.returncode: raise SystemExit(r.returncode)
    app=(front/'src/App.tsx').read_text()
    if "pasted.trim()" in app or app.count("function CheckEmailScreen")>1 or app.count("export default function App")>1:
        print("CORRUPTION_AFTER",i,cmd)
        lines=app.splitlines()
        for n,line in enumerate(lines,1):
            if "pasted.trim()" in line or "function CheckEmailScreen" in line or "export default function App" in line:
                print(n,line)
        raise SystemExit(91)
print("OK")
