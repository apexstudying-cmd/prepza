from pathlib import Path

s = Path("frontend/src/App.tsx").read_text()

required = [
    "| 'upload-share-choice'",
    "setScreen('upload-share-choice')",
    'function UploadShareChoiceScreen({ setScreen, activeDocumentId }',
    'Share to Prepza Library',
    "case 'upload-share-choice':",
]
for anchor in required:
    if anchor not in s:
        raise SystemExit(f"missing upload/share UX anchor: {anchor}")

if s.count("| 'upload-share-choice'") != 1:
    raise SystemExit("upload-share-choice screen union member is duplicated")

if s.count("case 'upload-share-choice':") != 1:
    raise SystemExit("upload-share-choice render case is duplicated")

if "setActiveDocumentId(created.document_id)\n      setScreen('processing')" in s:
    raise SystemExit("upload still bypasses the explicit post-upload choice")

print("post-upload StudyHub/Library choice UX anchors verified")
