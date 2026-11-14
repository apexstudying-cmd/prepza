from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "frontend/src/App.tsx"
UPLOAD_MODULE_PATH = ROOT / "frontend/src/screens/upload/UploadFlowScreens.tsx"
UPLOAD_CONFIG_PATH = ROOT / "frontend/src/screens/upload/uploadConfig.ts"
FILE_UTILS_PATH = ROOT / "frontend/src/lib/fileUtils.ts"
APP_SHELL_PATH = ROOT / "frontend/src/navigation/AppShell.tsx"
NAVIGATION_TYPES_PATH = ROOT / "frontend/src/types/navigation.ts"
FRONTEND_PACKAGE_PATH = ROOT / "frontend/package.json"


def _component(name: str) -> tuple[Path, str]:
    owners: list[tuple[Path, str]] = []
    for path in (APP_PATH, UPLOAD_MODULE_PATH):
        if not path.exists():
            continue
        source = path.read_text(encoding="utf-8")
        match = re.search(
            rf"(?m)^(?:export\s+)?function\s+{re.escape(name)}\b",
            source,
        )
        if not match:
            continue
        tail = source[match.end():]
        next_component = re.search(
            r"(?m)^(?:export\s+)?function\s+[A-Z][A-Za-z0-9_]*\b",
            tail,
        )
        end = match.end() + next_component.start() if next_component else len(source)
        owners.append((path, source[match.start():end]))

    assert len(owners) == 1, (
        f"{name} must have exactly one owner in App.tsx or UploadFlowScreens.tsx; "
        f"found {[str(path.relative_to(ROOT)) for path, _ in owners]}"
    )
    return owners[0]


def _all_upload_sources() -> str:
    paths = (APP_PATH, UPLOAD_MODULE_PATH, UPLOAD_CONFIG_PATH, FILE_UTILS_PATH)
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in paths
        if path.exists()
    )


def test_upload_screens_have_one_feature_owner_and_explicit_parent_props():
    upload_path, upload = _component("UploadScreen")
    choice_path, choice = _component("UploadShareChoiceScreen")
    processing_path, processing = _component("ProcessingScreen")

    assert upload_path == choice_path == processing_path, (
        "The connected upload/choice/processing flow must move as one feature boundary."
    )
    assert "setScreen: (s: Screen) => void" in upload
    assert "setActiveDocumentId: (id: number | null) => void" in upload
    assert "setScreen: (s: Screen) => void" in choice
    assert "activeDocumentId: number | null" in choice
    assert "setScreen: (s: Screen) => void" in processing
    assert "activeDocumentId: number | null" in processing

    if upload_path == UPLOAD_MODULE_PATH:
        module = UPLOAD_MODULE_PATH.read_text(encoding="utf-8")
        app = APP_PATH.read_text(encoding="utf-8")
        assert "from './screens/upload/UploadFlowScreens'" in app
        assert "TopBar: UploadTopBar" in upload
        assert "TopBar: UploadTopBar" in choice
        assert "from '../../App'" not in module
        assert "from '../App'" not in module


def test_upload_file_policy_remains_eight_types_and_fifty_megabytes():
    source = _all_upload_sources()
    allowed = re.search(
        r"ALLOWED_UPLOAD_EXTENSIONS\s*=\s*\[\s*"
        r"['\"]pdf['\"]\s*,\s*['\"]doc['\"]\s*,\s*['\"]docx['\"]\s*,\s*"
        r"['\"]ppt['\"]\s*,\s*['\"]pptx['\"]\s*,\s*['\"]jpg['\"]\s*,\s*"
        r"['\"]jpeg['\"]\s*,\s*['\"]png['\"]\s*\]",
        source,
        re.S,
    )
    assert allowed, "The existing PDF/Office/JPG/PNG upload allow-list changed."
    assert re.search(
        r"MAX_UPLOAD_SIZE_BYTES\s*=\s*50\s*\*\s*1024\s*\*\s*1024",
        source,
    ), "The existing 50 MB document limit changed."

    _, upload = _component("UploadScreen")
    assert 'accept=".pdf,.doc,.docx,.ppt,.pptx,.jpg,.jpeg,.png"' in upload


def test_upload_registration_storage_confirmation_and_offline_order_are_preserved():
    _, upload = _component("UploadScreen")
    required_in_order = [
        "const ext = getFileExtension(file.name)",
        "if (!ext || !ALLOWED_UPLOAD_EXTENSIONS.includes(ext))",
        "if (file.size > MAX_UPLOAD_SIZE_BYTES)",
        "const contentHash = await sha256Hex(file)",
        "const me = await api<",
        "}>('/documents', {",
        "original_filename: file.name",
        "file_size_bytes: file.size",
        "content_hash: contentHash",
        "if (!created.duplicate && created.upload_url)",
        "const putRes = await fetch(created.upload_url, { method: 'PUT', body: file })",
        "setUploadStage('Confirming upload...')",
        "await saveUploadedFileOffline(created.document_id, file, {",
        "setActiveDocumentId(created.document_id)",
        "setScreen('upload-share-choice')",
    ]
    positions = []
    for token in required_in_order:
        assert token in upload, f"Upload contract is missing: {token}"
        positions.append(upload.index(token))
    assert positions == sorted(positions), (
        "Upload validation, registration, signed PUT, confirmation, local-first "
        "persistence and navigation must remain in their existing order."
    )
    assert "headers: { 'X-CSRF-Token': me.csrf_token }" in upload
    assert "userId: me.id" in upload
    assert "fileType: ext" in upload
    assert "contentHash," in upload


def test_upload_confirmation_retries_only_a_conflict_once():
    _, upload = _component("UploadScreen")
    confirmation_call = (
        "api(" + chr(96) + "/documents/" + "$" +
        "{created.document_id}/uploaded" + chr(96)
    )
    assert upload.count(confirmation_call) == 2, (
        "The confirmation request should have one initial attempt and one 409 retry."
    )
    assert "if (e instanceof ApiError && e.status === 409)" in upload
    assert "await new Promise(r => setTimeout(r, 1500))" in upload
    assert "else {\n            throw e\n          }" in upload


def test_post_upload_choice_keeps_studyhub_private_until_explicit_publish():
    _, choice = _component("UploadShareChoiceScreen")
    detail_request = (
        "api<DocumentDetail>(" + chr(96) + "/documents/" + "$" +
        "{activeDocumentId}" + chr(96) + ")"
    )
    assert detail_request in choice
    assert "const openStudyHub = () => setScreen('processing')" in choice
    assert "const publish = () => setScreen('publish-library')" in choice
    assert "It is private by default. Sharing to Library is optional and requires your explicit choice." in choice
    assert "onClick={publish}" in choice
    assert "onClick={openStudyHub}" in choice


def test_processing_polling_stops_on_terminal_states_and_cleans_up():
    _, processing = _component("ProcessingScreen")
    for token in (
        "let cancelled = false",
        "let timer: ReturnType<typeof setTimeout>",
        "const poll = async () =>",
        "if (result.status === 'ready' || result.status === 'failed') return",
        "setTimeout(poll, 2500)",
        "return () => { cancelled = true; clearTimeout(timer) }",
        "status === 'failed'",
        "status === 'ready'",
        "setScreen('doc-ready')",
        "setScreen('upload')",
    ):
        assert token in processing, f"Processing contract is missing: {token}"


def test_app_route_props_and_bottom_navigation_rules_remain_unchanged():
    app = APP_PATH.read_text(encoding="utf-8")
    routes = (
        r"case 'upload':\s*return <UploadScreen setScreen=\{setScreen\} "
        r"setActiveDocumentId=\{setActiveDocumentId\} TopBar=\{TopBar\} />",
        r"case 'upload-share-choice':\s*return <UploadShareChoiceScreen "
        r"setScreen=\{setScreen\} activeDocumentId=\{activeDocumentId\} TopBar=\{TopBar\} />",
        r"case 'processing':\s*return <ProcessingScreen "
        r"setScreen=\{setScreen\} activeDocumentId=\{activeDocumentId\} />",
    )
    for route in routes:
        assert re.search(route, app), f"Existing upload route dispatch changed: {route}"

    screen_types = NAVIGATION_TYPES_PATH.read_text(encoding="utf-8")
    for screen in ("'upload'", "'upload-share-choice'", "'processing'"):
        assert screen in screen_types

    shell = APP_SHELL_PATH.read_text(encoding="utf-8")
    no_nav = re.search(r"const noNav: Screen\[\] = \[(.*?)\]", shell, re.S)
    assert no_nav, "AppShell's existing no-bottom-navigation screen list is missing."
    hidden = re.findall(r"['\"]([^'\"]+)['\"]", no_nav.group(1))
    assert "upload-share-choice" in hidden
    assert "processing" in hidden
    assert "upload" not in hidden



def test_shared_upload_policy_and_file_helpers_have_single_owner():
    config = UPLOAD_CONFIG_PATH.read_text(encoding="utf-8")
    file_utils = FILE_UTILS_PATH.read_text(encoding="utf-8")
    app = APP_PATH.read_text(encoding="utf-8")

    assert "export const ALLOWED_UPLOAD_EXTENSIONS = ['pdf', 'doc', 'docx', 'ppt', 'pptx', 'jpg', 'jpeg', 'png']" in config
    assert "export const MAX_UPLOAD_SIZE_BYTES = 50 * 1024 * 1024" in config
    assert "export const MAX_CHAT_ATTACHMENT_SIZE_BYTES = 20 * 1024 * 1024" in config
    assert "export const IMAGE_FILE_TYPES = ['jpg', 'jpeg', 'png']" in config
    assert "export function getFileExtension(" in file_utils
    assert "export async function sha256Hex(" in file_utils
    assert "from './lib/fileUtils'" in app
    assert "from './screens/upload/uploadConfig'" in app
    assert "function getFileExtension(" not in app
    assert "async function sha256Hex(" not in app
    assert "const ALLOWED_UPLOAD_EXTENSIONS" not in app
    assert "const MAX_CHAT_ATTACHMENT_SIZE_BYTES" not in app


def test_upload_transformer_inventory_is_wired_and_legacy_patch_is_not_prebuild():
    package = json.loads(FRONTEND_PACKAGE_PATH.read_text(encoding="utf-8"))
    prebuild = package["scripts"]["prebuild"]
    assert "tools/apply_library_publish_context_ux.py" in prebuild

    for legacy in (
        "scripts/apply_upload_share_choice_ux.py",
        "scripts/apply_upload_publish_binding.py",
        "scripts/apply_upload_publish_binding_repair.py",
    ):
        assert legacy not in prebuild

    publish_transform = (
        ROOT / "tools/apply_library_publish_context_ux.py"
    ).read_text(encoding="utf-8")
    assert "function PublishLibraryScreen(" in publish_transform
    assert "APP = Path" in publish_transform

    frontend_workflow = (
        ROOT / ".github/workflows/frontend-build.yml"
    ).read_text(encoding="utf-8")
    assert "'tests/test_upload_flow_module_contract.py'" in frontend_workflow
    assert "tests/test_upload_flow_module_contract.py" in frontend_workflow
