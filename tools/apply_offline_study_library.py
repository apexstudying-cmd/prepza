from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / 'frontend' / 'src' / 'lib' / 'appApi.ts'
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



def insert_library_save_hook(api_block: str, save_hook: str) -> str:
    """Insert the save hook before the successful API return, regardless of nesting."""
    if 'Library save -> offline asset download' in api_block:
        return api_block

    # Earlier offline-data/queue transformers wrap the fetch path in try/catch,
    # which indents this return one level deeper than the original helper.
    # Match the statement structurally and reuse its indentation rather than
    # depending on one exact whitespace layout.
    match = re.search(
        r"(?m)^([ \t]*)return\s+body\s+as\s+T\s*;?[ \t]*$",
        api_block,
    )
    if not match:
        raise SystemExit('Offline library: successful API return anchor not found')

    indent = match.group(1)
    lines = save_hook.strip("\n").splitlines()
    nonempty_indents = [
        len(line) - len(line.lstrip(" \t"))
        for line in lines if line.strip()
    ]
    baseline = min(nonempty_indents, default=0)
    normalized = [line[baseline:] if line.strip() else "" for line in lines]
    indented_hook = "\n".join(indent + line if line else "" for line in normalized)
    return api_block[:match.start()] + indented_hook + "\n" + api_block[match.start():]


def patch_api():
    s = API.read_text(encoding='utf-8')
    imports = [
        "import { getOfflineUserId } from '../offline/generatedMaterials'\n",
        "import { getSavedStudyHubOffline, listSavedStudyHubOffline, saveStudyHubDocumentOffline } from '../offline/studyHubOffline'\n",
    ]
    for line in reversed(imports):
        symbol = line.split('{', 1)[1].split('}', 1)[0].split(',')[0].strip()
        if symbol not in s:
            s = line + s

    api_marker = "export async function api<T = any>(path: string, options: RequestInit = {}): Promise<T> {"
    api_start = s.find(api_marker)
    if api_start < 0:
        raise SystemExit('Offline library: exported API helper not found')
    api_end = len(s)
    api_block = s[api_start:api_end].rstrip()

    if 'getSavedStudyHubOffline' not in api_block:
        destructure = "  const { headers: extraHeaders, ...restOptions } = options\n"
        method_line = "  const method = String(restOptions.method || 'GET').toUpperCase()\n"
        options_method_line = "  const method = String(options.method || 'GET').toUpperCase()\n"

        # The API helper has been rewritten by several independent build
        # transformations in local worktrees. Reuse an existing method
        # declaration where possible; otherwise insert a small, compatible
        # declaration at the start of the helper instead of requiring one
        # exact destructuring spelling.
        if method_line in api_block:
            gate_anchor = method_line
            gate_prefix = method_line
        elif options_method_line in api_block:
            gate_anchor = options_method_line
            gate_prefix = options_method_line
        elif destructure in api_block:
            gate_anchor = destructure
            gate_prefix = destructure + method_line
        else:
            method_match = re.search(
                r"^  const method = String\(.*\.method \|\| ['\"]GET['\"]\)\.toUpperCase\(\)\n",
                api_block,
                re.MULTILINE,
            )
            if method_match:
                gate_anchor = method_match.group(0)
                gate_prefix = gate_anchor
            else:
                # In the rare case that the helper has no recognizable method
                # declaration or options destructuring, insert at its first
                # newline. The gate ends with a newline, preserving the body.
                if "\n" not in api_block:
                    raise SystemExit('Offline library: api helper opening line not found')
                gate_anchor = "\n"
                gate_prefix = options_method_line

        offline_gate = f"""{gate_prefix}  const offline = typeof navigator !== 'undefined' && !navigator.onLine
  const offlineUserId = Number(getOfflineUserId() || 0)
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

    if (cleanPath === '/documents' || cleanPath === '/library' || cleanPath === '/study-hub' || cleanPath === '/library/saved') {{
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
      if (cleanPath === '/library/saved') return {{ saved: documents }} as T
      return {{ documents, saved_documents: documents, library: documents }} as T
    }}

    if (/^\\/documents\\/\\d+\\/reading$/.test(cleanPath)) return {{ page_num: 0 }} as T
  }}
"""
        api_block = api_block.replace(gate_anchor, offline_gate, 1)

    # A Library save is a user-visible offline action: after the server creates
    # the personal StudyHub copy, immediately download the actual document and
    # all reader pages into the existing account-scoped offline store.
    if 'Library save -> offline asset download' not in api_block:
        save_hook = """  // Library save -> offline asset download. The save endpoint is keyed by publication,
  // so do not assume its request body contains a document id. Prefer an id returned
  // by the endpoint and otherwise resolve the newly saved publication from the
  // account's saved list before downloading the actual StudyHub document.
  if (method === 'POST' && /^\\/library\\/\\d+\\/save$/.test(cleanPath)) {
    try {
      const responseBody = body && typeof body === 'object' ? body as any : {}
      let documentId = Number(responseBody.document_id ?? responseBody.documentId ?? responseBody.saved_document_id ?? responseBody.document?.id)
      if (!Number.isInteger(documentId) || documentId <= 0) {
        const publicationId = Number(cleanPath.split('/')[2])
        const savedResponse = await fetch('/library/saved', { credentials: 'include', cache: 'no-store' })
        if (savedResponse.ok) {
          const savedBody: any = await savedResponse.json()
          const match = (savedBody?.saved || []).find((item: any) => Number(item.id) === publicationId)
          documentId = Number(match?.document_id ?? match?.documentId)
        }
      }
      if (Number.isInteger(documentId) && documentId > 0) {
        try { await saveStudyHubDocumentOffline(documentId) } catch (_) {}
        if (body && typeof body === 'object') {
          responseBody.offline_available = !!(await getSavedStudyHubOffline(documentId, Number(getOfflineUserId() || 0)))
        }
      }
    } catch (_) {}
  }
"""
        api_block = insert_library_save_hook(api_block, save_hook)

    s = s[:api_start] + api_block + s[api_end:]
    required = [
        'getOfflineUserId()',
        'getSavedStudyHubOffline(documentId, offlineUserId)',
        'listSavedStudyHubOffline(offlineUserId)',
        "cleanPath === '/me'",
        "cleanPath === '/documents' || cleanPath === '/library' || cleanPath === '/study-hub' || cleanPath === '/library/saved'",
        'Library save -> offline asset download',
        'saveStudyHubDocumentOffline(documentId)',
    ]
    missing = [x for x in required if x not in s]
    if missing:
        raise SystemExit('Offline library verification failed: ' + ', '.join(missing))
    API.write_text(s, encoding='utf-8')


def main():
    patch_generated_user_id()
    patch_api()
    print('Offline StudyHub local document routing and save/download hook applied and verified.')


if __name__ == '__main__':
    main()
