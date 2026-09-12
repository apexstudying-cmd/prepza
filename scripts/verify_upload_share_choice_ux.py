from pathlib import Path

s = Path("frontend/src/App.tsx").read_text()

required = [
    "| 'upload-share-choice'",
    "setScreen('upload-share-choice')",
    'function UploadShareChoiceScreen({ setScreen, activeDocumentId }',
    'Share to Prepza Library',
    "case 'upload-share-choice':",
    "'upload-share-choice'",
]
for anchor in required:
    if anchor not in s:
        raise SystemExit(f"missing upload/share UX anchor: {anchor}")

if "setActiveDocumentId(created.document_id)\n      setScreen('processing')" in s:
    raise SystemExit("upload still bypasses the explicit post-upload choice")

print("post-upload StudyHub/Library choice UX anchors verified")
