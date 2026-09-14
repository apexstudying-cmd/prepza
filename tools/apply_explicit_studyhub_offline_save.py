from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'frontend/src/App.tsx'

IMPORT = "import { saveStudyHubDocumentOffline } from './offline/studyHubOffline'\n"
ACTIVITY_IMPORT = "import { mergeOfflineStudyResponse, startOfflineStudyTracking, syncOfflineStudyActivity } from './offline/studyActivity'\n"
GENERATED_IMPORT = "import { getGeneratedMaterialOffline, saveGeneratedMaterialOffline } from './offline/generatedMaterials'\n"

s = APP.read_text(encoding='utf-8')
anchor = "import { joinRealtimeChat, leaveRealtimeChat, sendReadRealtime, sendTypingRealtime } from './crypto/chatRealtime'\n"
if anchor not in s:
    raise SystemExit('App import anchor not found')
for import_line in (IMPORT, ACTIVITY_IMPORT, GENERATED_IMPORT):
    if import_line not in s:
        s = s.replace(anchor, anchor + import_line, 1)
        anchor = import_line

generation_replay = """  const requestBody = (() => { try { return typeof restOptions.body === 'string' ? JSON.parse(restOptions.body) : restOptions.body } catch { return null } })()\n  if (typeof navigator !== 'undefined' && !navigator.onLine && restOptions.method && restOptions.method.toUpperCase() !== 'GET' && /\\/documents\\/\\d+\\/(summarize|quiz|flashcards|podcast-script|mind-map)$/.test(path)) {\n    const cachedGenerated = await getGeneratedMaterialOffline(path, requestBody)\n    if (cachedGenerated != null) return cachedGenerated as T\n  }\n"""
if generation_replay not in s:
    anchor = "  const { headers: extraHeaders, ...restOptions } = options\n"
    if anchor not in s:
        raise SystemExit('API options anchor not found')
    s = s.replace(anchor, anchor + generation_replay, 1)

hook = """  if (res.ok && /^\\/library\\/\\d+\\/save$/.test(path) && body && Number.isInteger(Number(body.document_id))) {\n    try {\n      await saveStudyHubDocumentOffline(Number(body.document_id))\n      body.offline_available = true\n    } catch (_) {\n      body.offline_available = false\n    }\n  }\n\n  if (res.ok) await saveGeneratedMaterialOffline(path, requestBody, body)\n  body = mergeOfflineStudyResponse(path, body)\n"""
if hook not in s:
    anchor = "  if (!res.ok) {\n    throw new ApiError((body && body.error) || `Request failed (${res.status})`, res.status)\n  }\n"
    if anchor not in s:
        raise SystemExit('API success anchor not found')
    s = s.replace(anchor, anchor + hook, 1)

module_sync = """\nif (typeof window !== 'undefined') {\n  window.addEventListener('online', () => void syncOfflineStudyActivity())\n  window.setTimeout(() => void syncOfflineStudyActivity(), 1500)\n}\n"""
if module_sync not in s:
    marker = "// ─── Document upload helpers ───────────────────────────────────────────────\n"
    if marker not in s:
        raise SystemExit('module sync insertion anchor not found')
    s = s.replace(marker, module_sync + "\n" + marker, 1)

reader_marker = "function DocumentReaderScreen({ setScreen, activeDocumentId }: { setScreen: (s: Screen) => void; activeDocumentId: number | null }) {"
if reader_marker in s:
    tracking = "\n  useEffect(() => { if (activeDocumentId == null) return; return startOfflineStudyTracking(activeDocumentId, 'reading') }, [activeDocumentId])\n"
    if tracking not in s:
        s = s.replace(reader_marker, reader_marker + tracking, 1)

required = [IMPORT, ACTIVITY_IMPORT, GENERATED_IMPORT, "saveStudyHubDocumentOffline(Number(body.document_id))", "mergeOfflineStudyResponse(path, body)", "syncOfflineStudyActivity()", "getGeneratedMaterialOffline(path, requestBody)", "saveGeneratedMaterialOffline(path, requestBody, body)"]
missing = [x for x in required if x not in s]
if missing:
    raise SystemExit(f'explicit offline wiring verification failed: {missing}')

APP.write_text(s, encoding='utf-8')
print('StudyHub downloads, local activity, and offline generated-material replay wiring applied and verified.')