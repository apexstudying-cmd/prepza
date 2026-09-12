from pathlib import Path

s = Path("frontend/src/App.tsx").read_text()

required = [
    "| 'upload-share-choice'",
    "setScreen('upload-share-choice')",
    'function UploadShareChoiceScreen({ setScreen, activeDocumentId }',
    'Share to Prepza Library',
    "case 'upload-share-choice':",
    "function PublishLibraryScreen({ setScreen, activeDocumentId }",
    "setSelectedDocId(uploaded.id)",
    "setTitle(uploaded.title)",
    "case 'publish-library':   return <PublishLibraryScreen setScreen={setScreen} activeDocumentId={activeDocumentId} />",
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

if "setScreen('publish-library')" not in s:
    raise SystemExit("share choice does not open the Library publishing flow")

if "d.status === 'ready' || d.id === activeDocumentId" not in s:
    raise SystemExit("publish flow does not retain the uploaded document while it prepares")

if "const canProceed1 = selectedDocId != null && title.trim().length > 0 && selectedDoc?.status === 'ready'" not in s:
    raise SystemExit("publish flow could submit a document before it is ready")

print("post-upload StudyHub/Library choice and document binding anchors verified")
