from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'frontend' / 'src' / 'App.tsx'
s = APP.read_text(encoding='utf-8')

IMPORT_ANCHOR = "import { joinRealtimeChat, leaveRealtimeChat, sendReadRealtime, sendTypingRealtime } from './crypto/chatRealtime'\n"
IMPORTS = [
    "import { saveStudyHubDocumentOffline } from './offline/studyHubOffline'\n",
    "import { mergeOfflineStudyResponse, syncOfflineStudyActivity } from './offline/studyActivity'\n",
    "import { getGeneratedMaterialOffline, saveGeneratedMaterialOffline } from './offline/generatedMaterials'\n",
]
if IMPORT_ANCHOR not in s:
    raise SystemExit('Offline wiring: import anchor not found')
anchor = IMPORT_ANCHOR
for line in IMPORTS:
    if line not in s:
        s = s.replace(anchor, anchor + line, 1)
    anchor = line

# The offline foundation is intentionally built by earlier prebuild stages.
# Anchor to a line introduced by the sync-queue layer so this patch cannot
# accidentally modify an unrelated function if App.tsx changes later.
api_marker = "  const queueOffline = method !== 'GET' && String((extraHeaders as Record<string, string> | undefined)?.['X-Prepza-Offline-Queue'] || '').toLowerCase() === 'true'\n"
if api_marker not in s:
    raise SystemExit('Offline wiring: sync-queue API anchor not found')

offline_gate = """  const requestBody = (() => {
    try { return typeof restOptions.body === 'string' ? JSON.parse(restOptions.body) : restOptions.body }
    catch { return null }
  })()
  if (typeof navigator !== 'undefined' && !navigator.onLine && method !== 'GET' && /\\/documents\\/\\d+\\/(summarize|quiz|flashcards|podcast-script|mind-map)$/.test(path)) {
    const cachedGenerated = await getGeneratedMaterialOffline(path, requestBody)
    if (cachedGenerated != null) return cachedGenerated as T
  }
"""
if 'const cachedGenerated = await getGeneratedMaterialOffline(path, requestBody)' not in s:
    s = s.replace(api_marker, api_marker + offline_gate, 1)

fetch_anchor = """    if (canUseOfflineData && body !== null) {
      void writePrepzaOffline(cacheKey, body)
    }
    return body as T
"""
fetch_replacement = """    if (canUseOfflineData && body !== null) {
      void writePrepzaOffline(cacheKey, body)
    }
    if (/^\\/library\\/\\d+\\/save$/.test(path) && body && Number.isInteger(Number((body as any).document_id))) {
      try {
        await saveStudyHubDocumentOffline(Number((body as any).document_id))
        ;(body as any).offline_available = true
      } catch {
        ;(body as any).offline_available = false
      }
    }
    void saveGeneratedMaterialOffline(path, requestBody, body)
    return mergeOfflineStudyResponse(path, body)
"""
if 'saveStudyHubDocumentOffline(Number((body as any).document_id))' not in s:
    if fetch_anchor not in s:
        raise SystemExit('Offline wiring: cached API success anchor not found')
    s = s.replace(fetch_anchor, fetch_replacement, 1)

SYNC = """\nif (typeof window !== 'undefined') {
  window.addEventListener('online', () => void syncOfflineStudyActivity())
  window.setTimeout(() => void syncOfflineStudyActivity(), 1500)
}
"""
if "window.addEventListener('online', () => void syncOfflineStudyActivity())" not in s:
    marker = "// ─── Document upload helpers"
    if marker not in s:
        raise SystemExit('Offline wiring: module sync anchor not found')
    s = s.replace(marker, SYNC + "\n" + marker, 1)

required = [
    *IMPORTS,
    'getGeneratedMaterialOffline(path, requestBody)',
    'saveStudyHubDocumentOffline(Number((body as any).document_id))',
    'saveGeneratedMaterialOffline(path, requestBody, body)',
    'mergeOfflineStudyResponse(path, body)',
    'syncOfflineStudyActivity()',
]
missing = [item for item in required if item not in s]
if missing:
    raise SystemExit('Offline wiring verification failed: ' + ', '.join(missing))

APP.write_text(s, encoding='utf-8')
print('Explicit offline study replay wiring applied safely.')
