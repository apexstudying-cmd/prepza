from pathlib import Path
import re

APP = Path('frontend/src/App.tsx')

IMPORT = "import { saveStudyHubDocumentOffline } from './offline/studyHubOffline'\n"
ACTIVITY_IMPORT = "import { mergeOfflineStudyResponse, startOfflineStudyTracking, syncOfflineStudyActivity } from './offline/studyActivity'\n"

s = APP.read_text(encoding='utf-8')

if IMPORT not in s:
    anchor = "import { joinRealtimeChat, leaveRealtimeChat, sendReadRealtime, sendTypingRealtime } from './crypto/chatRealtime'\n"
    if anchor not in s:
        raise SystemExit('App import anchor not found')
    s = s.replace(anchor, anchor + IMPORT, 1)
if ACTIVITY_IMPORT not in s:
    anchor = IMPORT
    if anchor not in s:
        raise SystemExit('StudyHub offline import anchor not found')
    s = s.replace(anchor, anchor + ACTIVITY_IMPORT, 1)

hook = """  // Product rule: Library Save is also the explicit offline download action.\n  // Explore views never call this; only the successful Library save endpoint does.\n  if (res.ok && /^\\/library\\/\\d+\\/save$/.test(path) && body && Number.isInteger(Number(body.document_id))) {\n    try {\n      await saveStudyHubDocumentOffline(Number(body.document_id))\n      body.offline_available = true\n    } catch (_) {\n      body.offline_available = false\n    }\n  }\n\n  body = mergeOfflineStudyResponse(path, body)\n"""

if hook not in s:
    anchor = "  if (!res.ok) {\n    throw new ApiError((body && body.error) || `Request failed (${res.status})`, res.status)\n  }\n"
    if anchor not in s:
        raise SystemExit('API success anchor not found')
    s = s.replace(anchor, anchor + hook, 1)

final_return = "  return body as T\n}"
if final_return in s and "syncOfflineStudyActivity" not in s.split(final_return, 1)[0]:
    s = s.replace(final_return, "  return body as T\n}", 1)

# Reconcile locally accumulated study time whenever connectivity returns.
module_sync = """\nif (typeof window !== 'undefined') {\n  window.addEventListener('online', () => void syncOfflineStudyActivity())\n  window.setTimeout(() => void syncOfflineStudyActivity(), 1500)\n}\n"""
if module_sync not in s:
    marker = "// ─── Document upload helpers ───────────────────────────────────────────────\n"
    if marker not in s:
        raise SystemExit('module sync insertion anchor not found')
    s = s.replace(marker, module_sync + "\n" + marker, 1)

# Native reader is the main document-study surface; PDF study canvas also
# receives tracking separately in apply_offline_study.py.
reader_marker = "function DocumentReaderScreen({ setScreen, activeDocumentId }: { setScreen: (s: Screen) => void; activeDocumentId: number | null }) {"
if reader_marker in s:
    tracking = "\n  useEffect(() => { if (activeDocumentId == null) return; return startOfflineStudyTracking(activeDocumentId, 'reading') }, [activeDocumentId])\n"
    if tracking not in s:
        s = s.replace(reader_marker, reader_marker + tracking, 1)

required = [IMPORT, ACTIVITY_IMPORT, "saveStudyHubDocumentOffline(Number(body.document_id))", "mergeOfflineStudyResponse(path, body)", "syncOfflineStudyActivity()"]
missing = [x for x in required if x not in s]
if missing:
    raise SystemExit(f'explicit StudyHub/offline activity verification failed: {missing}')

APP.write_text(s, encoding='utf-8')
print('explicit StudyHub download and local-first activity wiring applied and verified.')