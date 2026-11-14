from pathlib import Path

root = Path(__file__).resolve().parents[1]
app = (root / "frontend/src/App.tsx").read_text(encoding="utf-8")
upload = (root / "frontend/src/screens/upload/UploadFlowScreens.tsx").read_text(encoding="utf-8")
publish = (root / "frontend/src/screens/library/PublishLibraryScreen.tsx").read_text(encoding="utf-8")

required_app = [
    "| 'upload-share-choice'",
    "import { UploadScreen, UploadShareChoiceScreen, ProcessingScreen } from './screens/upload/UploadFlowScreens'",
    "import PublishLibraryScreen from './screens/library/PublishLibraryScreen'",
    "case 'upload':",
    "case 'upload-share-choice':",
    "case 'processing':",
    "case 'publish-library':   return <PublishLibraryScreen setScreen={setScreen} activeDocumentId={activeDocumentId} EmptyState={EmptyState} />",
]
for anchor in required_app:
    if anchor not in app:
        raise SystemExit(f"missing app-shell upload/publish anchor: {anchor}")

required_upload = [
    "export function UploadScreen(",
    "export function UploadShareChoiceScreen(",
    "export function ProcessingScreen(",
    "setActiveDocumentId(created.document_id)",
    "setScreen('upload-share-choice')",
    "setScreen('publish-library')",
]
for anchor in required_upload:
    if anchor not in upload:
        raise SystemExit(f"missing upload-flow module anchor: {anchor}")

required_publish = [
    "export default function PublishLibraryScreen(",
    "setSelectedDocId(uploaded.id)",
    "setTitle(uploaded.title)",
    "d.status === 'ready' || d.id === activeDocumentId",
    "const canProceed1 = selectedDocId != null && title.trim().length > 0 && selectedDoc?.status === 'ready'",
    ">('/library/publish'",
    "'X-CSRF-Token': csrfToken",
]
for anchor in required_publish:
    if anchor not in publish:
        raise SystemExit(f"missing PublishLibrary module anchor: {anchor}")

if app.count("case 'upload-share-choice':") != 1:
    raise SystemExit("upload-share-choice route is duplicated")
if app.count("case 'publish-library':") != 1:
    raise SystemExit("publish-library route is duplicated")
if "function PublishLibraryScreen(" in app:
    raise SystemExit("PublishLibraryScreen is still declared inside App.tsx")

print("upload, post-upload choice, and PublishLibrary module ownership verified")
