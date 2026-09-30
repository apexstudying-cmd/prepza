from pathlib import Path

source = Path("frontend/src/offline/studyHubOffline.ts").read_text(encoding="utf-8")

required = "const MAX_SINGLE_ASSET_BYTES = 75 * 1024 * 1024"
if required not in source:
    raise SystemExit("StudyHub single-document offline limit changed unexpectedly")

required_total = "const MAX_TOTAL_ASSET_BYTES = 250 * 1024 * 1024"
if required_total not in source:
    raise SystemExit("StudyHub total offline storage limit must remain 250 MiB")

if "1024 * 1024 * 1024" in source:
    raise SystemExit("StudyHub still contains the obsolete 1 GiB total storage limit")

print("StudyHub offline storage limits verified: 75 MiB per document, 250 MiB total")
