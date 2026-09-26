"""Normalize final loading skeleton gates after all build-time App transforms."""
from pathlib import Path
import re

APP = Path(__file__).resolve().parents[1] / "frontend" / "src" / "App.tsx"
s = APP.read_text(encoding="utf-8")
s = s.replace('ExploreStudentLocal', 'ExploreStudent')

pattern = re.compile(r"if\s*\(loading\)\s*return\s*(<Skeleton[A-Za-z0-9_]+\s*/>)")
s, count = pattern.subn(r"if (loading) return <DelayedScreenSkeleton>\1</DelayedScreenSkeleton>", s)

if "function DelayedScreenSkeleton" not in s:
    raise SystemExit("FINAL_LOADING_GATE_FAILED: delayed skeleton helper missing")
APP.write_text(s, encoding="utf-8")
print(f"Final loading gates normalized: wrapped={count}")
