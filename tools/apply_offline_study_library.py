from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'frontend' / 'src' / 'App.tsx'
GEN = ROOT / 'frontend' / 'src' / 'offline' / 'generatedMaterials.ts'


def patch_generated_user_id():
    s = GEN.read_text(encoding='utf-8')
    if 'export function getOfflineUserId()' in s:
        return
    anchor = "export function setOfflineUserId(userId: number) {\n"
    if anchor not in s:
        raise SystemExit('Offline library: user-id anchor not found')
    start = s.index(anchor)
    insert_after = s.index('\n}', start) + 2
    addition = "\n\nexport function getOfflineUserId(): number | null {\n  try {\n    const raw = localStorage.getItem(USER_KEY)\n    const id = Number(raw)\n    return Number.isInteger(id) && id > 0 ? id : null\n  } catch (_) { return null }\n}"
    s = s[:insert_after] + addition + s[insert_after:]
    GEN.write_text(s, encoding='utf-8')


def patch_app():
    s = APP.read_text(encoding='utf-8')
    anchor = "import { joinRealtimeChat, leaveRealtimeChat, sendReadRealtime, sendTypingRealtime } from './crypto/chatRealtime'\n"
    imports = [
        "import { getOfflineUserId } from './offline/generatedMaterials'\n",
        "import { getSavedStudyHubOffline, listSavedStudyHubOffline, removeStudyHubOfflineCopy, saveStudyHubDocumentOffline } from './offline/studyHubOffline'\n",
    ]
    if anchor not in s:
        raise SystemExit('Offline library: App import anchor not found')
    insert = anchor
    for line in imports:
        if line not in s:
            insert += line
    if insert != anchor:
        s = s.replace(anchor, insert, 1)

    api_marker = "async function api<T = any>(path: string, options: RequestInit = {}): Promise<T> {"
    api_start = s.find(api_marker)
    if api_start < 0:
        raise SystemExit('Offline library: api helper not found')
    api_end = s.find('\n}\n\n// ─── Document upload helpers', api_start)
    if api_end < 0:
        raise SystemExit('Offline library: api helper boundary not found')
    api_block = s[api_start:api_end]
    if 'getSavedStudyHubOffline' not in api_block:
        needle = "  const { headers: extraHeaders, ...restOptions } = options\n"
        if needle not in api_block:
            raise SystemExit('Offline library: api options anchor not found')
        offline_gate = """  const { headers: extraHeaders, ...restOptions } = options
  const method = String(restOptions.method || 'GET').toUpperCase()
  const offline = typeof navigator !== 'undefined' && !navigator.onLine
  const offlineUserId = getOfflineUserId()

  // Saved StudyHub documents are the authoritative local document source
  // for this account while offline. Unsaved documents still require network.
  if (offline && method === 'GET' && offlineUserId) {
    if (/^\\/documents\\/\\d+$/.test(path)) {
      const documentId = Number(path.split('/')[2])
      const saved = await getSavedStudyHubOffline(documentId, offlineUserId)
      if (saved) {
        return {
          id: saved.documentId,
          title: saved.title || 'Saved document',
          original_filename: saved.title || 'Saved document',
          status: 'ready',
          file_type: saved.fileType || 'pdf',
          file_size_bytes: null,
          page_count: saved.pageCount || null,
          error_message: null,
          view_url: saved.assetUrls?.find((url: string) => !url.includes('/reading/page/')) || null,
          materials: [],
          created_at: new Date(saved.savedAt).toISOString(),
        } as T
      }
    }
    if (path === '/documents') {
      const saved = await listSavedStudyHubOffline(offlineUserId)
      return {
        documents: saved.map((row: any) => ({
          id: row.documentId,
          title: row.title || 'Saved document',
          status: 'ready',
          file_type: row.fileType || 'pdf',
          page_count: row.pageCount || null,
          created_at: new Date(row.savedAt).toISOString(),
        })),
      } as T
    }
    if (/^\\/documents\\/\\d+\\/reading$/.test(path)) return { page_num: 0 } as T
  }
"""
        api_block = api_block.replace(needle, offline_gate, 1)

    save_hook = """  if (path.match(/^\\/library\\/\\d+\\/save$/) && body && Number.isInteger(Number(body.document_id))) {
    try { body.offline_available = true; await saveStudyHubDocumentOffline(Number(body.document_id)) }
    catch (_) { body.offline_available = false }
  }
"""
    if 'saveStudyHubDocumentOffline(Number(body.document_id))' not in api_block:
        return_anchor = "  return body as T\n"
        if return_anchor not in api_block:
            raise SystemExit('Offline library: API return anchor not found')
        api_block = api_block.replace(return_anchor, save_hook + return_anchor, 1)
    s = s[:api_start] + api_block + s[api_end:]

    if 'function OfflineSavedStudyShelf' not in s:
        marker = "function LibraryScreen({ setScreen, setActiveDocumentId }: { setScreen: (s: Screen) => void; setActiveDocumentId: (id: number | null) => void }) {"
        if marker not in s:
            raise SystemExit('Offline library: LibraryScreen marker not found')
        component = r'''function OfflineSavedStudyShelf({ setScreen, setActiveDocumentId }: { setScreen: (s: Screen) => void; setActiveDocumentId: (id: number | null) => void }) {
  const { tokens: T } = useTheme()
  const [rows, setRows] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  const reload = () => {
    const userId = getOfflineUserId()
    if (!userId) { setRows([]); setLoading(false); return }
    setLoading(true)
    listSavedStudyHubOffline(userId).then(setRows).catch(() => setRows([])).finally(() => setLoading(false))
  }

  useEffect(() => {
    reload()
    const onChange = () => reload()
    window.addEventListener('prepza:studyhub-offline-changed', onChange)
    window.addEventListener('online', onChange)
    return () => {
      window.removeEventListener('prepza:studyhub-offline-changed', onChange)
      window.removeEventListener('online', onChange)
    }
  }, [])

  if (loading || rows.length === 0) return null
  return (
    <section style={{ marginBottom: 18 }}>
      <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 16, padding: 14 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
          <div>
            <div style={{ fontWeight: 850, fontSize: 15, color: T.text }}>Saved on this device</div>
            <div style={{ fontSize: 11, color: T.textMuted, marginTop: 2 }}>Available without internet</div>
          </div>
          <span style={{ fontSize: 10, fontWeight: 800, color: '#4CC97B', background: 'rgba(76,201,123,0.12)', borderRadius: 20, padding: '5px 8px' }}>OFFLINE</span>
        </div>
        {rows.map(row => (
          <div key={row.key} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 0', borderTop: `1px solid ${T.border}` }}>
            <div style={{ width: 38, height: 38, borderRadius: 11, background: 'rgba(201,168,76,0.12)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>📄</div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontWeight: 750, fontSize: 12, color: T.text }} className="line-clamp-1">{row.title || 'Saved document'}</div>
              <div style={{ fontSize: 10, color: T.textMuted }}>{row.pageCount ? `${row.pageCount} pages` : 'Saved for offline study'}</div>
            </div>
            <button onClick={() => { setActiveDocumentId(row.documentId); setScreen('document-study') }} style={{ border: `1px solid ${N.gold}55`, background: 'rgba(201,168,76,0.08)', color: N.gold, borderRadius: 10, padding: '7px 10px', fontSize: 10, fontWeight: 800, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Study</button>
            <button aria-label={`Remove ${row.title || 'document'} offline copy`} onClick={() => { const id = getOfflineUserId(); if (id) void removeStudyHubOfflineCopy(row.documentId, id).then(reload) }} style={{ border: 'none', background: 'none', color: T.textMuted, borderRadius: 8, padding: 6, cursor: 'pointer', fontSize: 14 }}>×</button>
          </div>
        ))}
      </div>
    </section>
  )
}

'''
        s = s.replace(marker, component + marker, 1)

    marker = "function LibraryScreen({ setScreen, setActiveDocumentId }: { setScreen: (s: Screen) => void; setActiveDocumentId: (id: number | null) => void }) {"
    start = s.index(marker)
    ret = s.find('  return (', start)
    if ret < 0:
        raise SystemExit('Offline library: LibraryScreen return not found')
    first_tag_end = s.find('>', ret)
    if first_tag_end < 0:
        raise SystemExit('Offline library: LibraryScreen root element not found')
    if '<OfflineSavedStudyShelf ' not in s[ret:first_tag_end + 500]:
        insert = "\n      <OfflineSavedStudyShelf setScreen={setScreen} setActiveDocumentId={setActiveDocumentId} />"
        s = s[:first_tag_end + 1] + insert + s[first_tag_end + 1:]

    required = [
        'getOfflineUserId()', 'getSavedStudyHubOffline(documentId, offlineUserId)',
        'listSavedStudyHubOffline(offlineUserId)', 'saveStudyHubDocumentOffline(Number(body.document_id))',
        'function OfflineSavedStudyShelf', '<OfflineSavedStudyShelf',
    ]
    missing = [x for x in required if x not in s]
    if missing: raise SystemExit('Offline library verification failed: ' + ', '.join(missing))
    APP.write_text(s, encoding='utf-8')


def main():
    patch_generated_user_id()
    patch_app()
    print('Offline StudyHub library surface and local document routing applied and verified.')


if __name__ == '__main__':
    main()
