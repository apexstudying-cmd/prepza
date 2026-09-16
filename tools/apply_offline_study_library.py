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
        "import { getSavedStudyHubOffline, listSavedStudyHubOffline, saveStudyHubDocumentOffline } from './offline/studyHubOffline'\n",
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
        method_line = "  const method = String(restOptions.method || 'GET').toUpperCase()\n"
        if method_line not in api_block:
            method_line = method_line
        else:
            method_line = ''
        offline_gate = f"""  const {{ headers: extraHeaders, ...restOptions }} = options
{method_line}  const offline = typeof navigator !== 'undefined' && !navigator.onLine
  const offlineUserId = getOfflineUserId()
  const cleanPath = String(path || '').split('?')[0].split('#')[0].replace(/\\/+$/, '') || '/'

  // Saved StudyHub documents are the authoritative local document source
  // for this account while offline. Unsaved documents still require network.
  if (offline && method === 'GET' && offlineUserId) {{
    if (cleanPath === '/me') {{
      return {{ id: offlineUserId }} as T
    }}

    if (/^\\/documents\\/\\d+$/.test(cleanPath)) {{
      const documentId = Number(cleanPath.split('/')[2])
      const saved = await getSavedStudyHubOffline(documentId, offlineUserId)
      if (saved) {{
        return {{
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
        }} as T
      }}
    }}

    if (cleanPath === '/documents' || cleanPath === '/library' || cleanPath === '/study-hub') {{
      const saved = await listSavedStudyHubOffline(offlineUserId)
      const documents = saved.map((row: any) => ({{
        id: row.documentId,
        document_id: row.documentId,
        title: row.title || 'Saved document',
        original_filename: row.title || 'Saved document',
        status: 'ready',
        file_type: row.fileType || 'pdf',
        page_count: row.pageCount || null,
        created_at: new Date(row.savedAt).toISOString(),
        offline_available: true,
      }}))
      return {{ documents, saved_documents: documents, library: documents }} as T
    }}

    if (/^\\/documents\\/\\d+\\/reading$/.test(cleanPath)) return {{ page_num: 0 }} as T
  }}
"""
        api_block = api_block.replace(needle, offline_gate, 1)

    if 'saveStudyHubDocumentOffline(Number(body.document_id))' not in api_block:
        save_hook = """  if (path.startsWith('/library/') && path.endsWith('/save') && body && Number.isInteger(Number(body.document_id))) {
    try { body.offline_available = true; await saveStudyHubDocumentOffline(Number(body.document_id)) }
    catch (_) { body.offline_available = false }
  }
"""
        return_anchor = "  return body as T\n"
        if return_anchor not in api_block:
            raise SystemExit('Offline library: API return anchor not found')
        api_block = api_block.replace(return_anchor, save_hook + return_anchor, 1)

    s = s[:api_start] + api_block + s[api_end:]
    required = [
        'getOfflineUserId()',
        'getSavedStudyHubOffline(documentId, offlineUserId)',
        'listSavedStudyHubOffline(offlineUserId)',
        "cleanPath === '/me'",
        "cleanPath === '/documents' || cleanPath === '/library' || cleanPath === '/study-hub'",
        'saveStudyHubDocumentOffline(Number(body.document_id))',
    ]
    missing = [x for x in required if x not in s]
    if missing:
        raise SystemExit('Offline library verification failed: ' + ', '.join(missing))
    APP.write_text(s, encoding='utf-8')


def main():
    patch_generated_user_id()
    patch_app()
    print('Offline StudyHub local document routing and save/download hook applied and verified.')


if __name__ == '__main__':
    main()
