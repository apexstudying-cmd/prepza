from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'frontend' / 'src' / 'App.tsx'
s = APP.read_text(encoding='utf-8')

IMPORTS = [
    "import { saveStudyHubDocumentOffline } from './offline/studyHubOffline'\n",
    "import { mergeOfflineStudyResponse, startOfflineStudyTracking, syncOfflineStudyActivity } from './offline/studyActivity'\n",
    "import { getGeneratedMaterialOffline, saveGeneratedMaterialOffline } from './offline/generatedMaterials'\n",
]
anchor = "import { joinRealtimeChat, leaveRealtimeChat, sendReadRealtime, sendTypingRealtime } from './crypto/chatRealtime'\n"
if anchor not in s:
    raise SystemExit('Offline wiring: App import anchor not found')
for line in IMPORTS:
    if line not in s:
        s = s.replace(anchor, anchor + line, 1)
        anchor = line

api_start = s.find('async function api<T = any>(path: string, options: RequestInit = {}): Promise<T> {')
api_end = s.find('\n}\n\n// ─── Document upload helpers', api_start)
if api_start < 0 or api_end < 0:
    raise SystemExit('Offline wiring: generated api helper boundaries not found')
api = s[api_start:api_end + 2]

# Generated-material replay is strictly GET-independent and only applies to
# known generation endpoints. It never turns arbitrary mutations into offline work.
replay = """  const requestBody = (() => {
    try { return typeof restOptions.body === 'string' ? JSON.parse(restOptions.body) : restOptions.body }
    catch { return null }
  })()
  if (typeof navigator !== 'undefined' && !navigator.onLine && String(restOptions.method || 'GET').toUpperCase() !== 'GET' && /\\/documents\\/\\d+\\/(summarize|quiz|flashcards|podcast-script|mind-map)$/.test(path)) {
    const cachedGenerated = await getGeneratedMaterialOffline(path, requestBody)
    if (cachedGenerated != null) return cachedGenerated as T
  }
"""
options_anchor = "  const { headers: extraHeaders, ...restOptions } = options\n"
if 'const cachedGenerated = await getGeneratedMaterialOffline(path, requestBody)' not in api:
    if options_anchor not in api:
        raise SystemExit('Offline wiring: API options anchor not found')
    api = api.replace(options_anchor, options_anchor + replay, 1)

# Only the successful Library-save response triggers the explicit download.
# The request itself remains online-only; this avoids queueing a save twice.
hook = """  if (/^\\/library\\/\\d+\\/save$/.test(path) && body && Number.isInteger(Number(body.document_id))) {
    try {
      await saveStudyHubDocumentOffline(Number(body.document_id))
      body.offline_available = true
    } catch {
      body.offline_available = false
    }
  }
  void saveGeneratedMaterialOffline(path, requestBody, body)
  body = mergeOfflineStudyResponse(path, body)
"""
if 'saveStudyHubDocumentOffline(Number(body.document_id))' not in api:
    return_match = re.search(r'(?m)^  return body as T\n$', api)
    if not return_match:
        return_match = re.search(r'(?m)^  return body\n$', api)
    if not return_match:
        raise SystemExit('Offline wiring: API return boundary not found')
    api = api[:return_match.start()] + hook + api[return_match.start():]

s = s[:api_start] + api + s[api_end + 2:]

# Sync on reconnect and once after startup. Both are idempotent; failures are
# intentionally swallowed by the sync helper so online startup cannot break.
module_sync = """\nif (typeof window !== 'undefined') {
  window.addEventListener('online', () => void syncOfflineStudyActivity())
  window.setTimeout(() => void syncOfflineStudyActivity(), 1500)
}
"""
if 'window.addEventListener(\'online\', () => void syncOfflineStudyActivity())' not in s:
    marker = "// ─── Document upload helpers ───────────────────────────────────────────────\n"
    if marker not in s:
        raise SystemExit('Offline wiring: module sync anchor not found')
    s = s.replace(marker, module_sync + "\n" + marker, 1)

# PDF reader tracking is already supplied by apply_offline_study.py. Do not
# inject a second tracker into the reader component.
required = [
    IMPORTS[0], IMPORTS[1], IMPORTS[2],
    'getGeneratedMaterialOffline(path, requestBody)',
    'saveStudyHubDocumentOffline(Number(body.document_id))',
    'saveGeneratedMaterialOffline(path, requestBody, body)',
    'mergeOfflineStudyResponse(path, body)',
    'syncOfflineStudyActivity()',
]
missing = [x for x in required if x not in s]
if missing:
    raise SystemExit('Offline wiring verification failed: ' + ', '.join(missing))

APP.write_text(s, encoding='utf-8')
print('Explicit offline study replay wiring applied safely.')
