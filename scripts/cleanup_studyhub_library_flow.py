from pathlib import Path
import re

p = Path("frontend/src/App.tsx")
s = p.read_text()

# Keep exactly one screen-union member even if the runtime patch workflow
# runs again against an already-patched branch.
s, count = re.subn(r"(?:\n  \| 'upload-share-choice')+", "\n  | 'upload-share-choice'", s)
if count == 0 and "| 'upload-share-choice'" not in s:
    raise SystemExit("upload-share-choice screen union anchor missing")

p.write_text(s)
print("StudyHub/Library frontend cleanup applied")
