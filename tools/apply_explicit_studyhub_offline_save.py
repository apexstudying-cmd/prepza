from pathlib import Path

APP = Path('frontend/src/App.tsx')

IMPORT = "import { saveStudyHubDocumentOffline } from './offline/studyHubOffline'\n"

s = APP.read_text(encoding='utf-8')

if IMPORT not in s:
    anchor = "import { joinRealtimeChat, leaveRealtimeChat, sendReadRealtime, sendTypingRealtime } from './crypto/chatRealtime'\n"
    if anchor not in s:
        raise SystemExit('App import anchor not found')
    s = s.replace(anchor, anchor + IMPORT, 1)

hook = """  // Product rule: Library Save is also the explicit offline download action.\n  // Explore views never call this; only the successful Library save endpoint does.\n  if (res.ok && /^\\/library\\/\\d+\\/save$/.test(path) && body && Number.isInteger(Number(body.document_id))) {\n    try {\n      await saveStudyHubDocumentOffline(Number(body.document_id))\n      body.offline_available = true\n    } catch (_) {\n      // The server-side save remains valid even if local storage cannot accept\n      // the download. The response exposes the state for a future UX message.\n      body.offline_available = false\n    }\n  }\n"""

if hook not in s:
    anchor = "  if (!res.ok) {\n    throw new ApiError((body && body.error) || `Request failed (${res.status})`, res.status)\n  }\n"
    if anchor not in s:
        raise SystemExit('API success anchor not found')
    s = s.replace(anchor, anchor + hook, 1)

required = [IMPORT, "saveStudyHubDocumentOffline(Number(body.document_id))", "body.offline_available = true"]
missing = [x for x in required if x not in s]
if missing:
    raise SystemExit(f'explicit StudyHub offline save verification failed: {missing}')

APP.write_text(s, encoding='utf-8')
print('explicit StudyHub Save -> offline download wiring applied and verified.')
