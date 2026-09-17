from pathlib import Path

APP = Path('frontend/src/App.tsx')


def patch_study_hub(s):
    if 'const [readingPage, setReadingPage] = useState(0)' not in s:
        old_state = "  const [showCreate, setShowCreate] = useState(false)\n"
        new_state = "  const [showCreate, setShowCreate] = useState(false)\n  const [readingPage, setReadingPage] = useState(0)\n"
        if old_state not in s:
            raise SystemExit('study hub state anchor not found')
        s = s.replace(old_state, new_state, 1)

    old_effect = '''    setLoading(true)\n    setError('')\n    api<DocumentDetail>(`/documents/${activeDocumentId}`)\n      .then(data => { if (!cancelled) setDocument(data) })\n      .catch(err => { if (!cancelled) setError(err instanceof ApiError ? err.message : 'Could not open this document.') })\n      .finally(() => { if (!cancelled) setLoading(false) })\n'''
    new_effect = '''    setLoading(true)\n    setError('')\n    Promise.all([\n      api<DocumentDetail>(`/documents/${activeDocumentId}`),\n      api<{ page_num: number }>(`/documents/${activeDocumentId}/reading`),\n    ])\n      .then(([data, progress]) => {\n        if (cancelled) return\n        setDocument(data)\n        DOC_CACHE[activeDocumentId] = data\n        setReadingPage(Math.max(0, progress.page_num || 0))\n      })\n      .catch(err => { if (!cancelled) setError(err instanceof ApiError ? err.message : 'Could not open this document.') })\n      .finally(() => { if (!cancelled) setLoading(false) })\n'''
    if old_effect in s:
        s = s.replace(old_effect, new_effect, 1)

    old_header = '''        <div style={{ color: '#fff', fontSize: 20, fontWeight: 850, lineHeight: 1.25 }} className="line-clamp-2">{document.title}</div>\n        <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: 11, marginTop: 6 }}>\n          {document.page_count ? `${document.page_count} pages` : 'Document'}{document.file_type ? ` · ${document.file_type.toUpperCase()}` : ''}\n        </div>\n'''
    new_header = '''        <div style={{ color: '#fff', fontSize: 20, fontWeight: 850, lineHeight: 1.25 }} className="line-clamp-2">{document.title}</div>\n        <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: 11, marginTop: 6 }}>\n          {document.page_count ? `${document.page_count} pages` : 'Document'}{document.file_type ? ` · ${document.file_type.toUpperCase()}` : ''}\n        </div>\n        {document.page_count ? (() => {\n          const studiedPercent = Math.min(100, Math.round((Math.min(readingPage + 1, document.page_count) / document.page_count) * 100))\n          return <div style={{ marginTop: 12 }}>\n            <div style={{ display: 'flex', justifyContent: 'space-between', color: 'rgba(255,255,255,0.62)', fontSize: 10, marginBottom: 5 }}>\n              <span>Study progress</span><span>{studiedPercent}%</span>\n            </div>\n            <div style={{ height: 5, borderRadius: 999, background: 'rgba(255,255,255,0.12)', overflow: 'hidden' }}>\n              <div style={{ height: '100%', width: `${studiedPercent}%`, background: N.gold, borderRadius: 999 }} />\n            </div>\n          </div>\n        })() : null}\n'''
    if old_header in s and 'Study progress' not in s:
        s = s.replace(old_header, new_header, 1)
    return s


def patch_native_reader(s):
    marker = "function DocumentReaderScreen({ setScreen, activeDocumentId }: { setScreen: (s: Screen) => void; activeDocumentId: number | null }) {"
    start = s.find(marker)
    if start < 0:
        raise SystemExit('native reader function anchor not found')
    end = s.find('\n// ─── ', start + len(marker))
    if end < 0:
        end = len(s)
    section = s[start:end]

    old_state = "  const [csrfToken, setCsrfToken] = useState('')\n"
    new_state = "  const [csrfToken, setCsrfToken] = useState('')\n  const [readerUserId, setReaderUserId] = useState<number | null>(null)\n  const localProgressKey = activeDocumentId == null || readerUserId == null ? '' : `prepza-reading-progress:${readerUserId}:${activeDocumentId}`\n  const saveLocalPage = (value: number, key = localProgressKey) => {\n    if (!key) return\n    try { localStorage.setItem(key, String(Math.max(0, value))) } catch {}\n  }\n"
    if old_state in section and 'readerUserId' not in section:
        section = section.replace(old_state, new_state, 1)

    old_me = "api<{csrf_token:string}>('/me')"
    if old_me in section:
        section = section.replace(old_me, "api<{csrf_token:string; id:number}>('/me')", 1)

    old_then = ".then(([detail, progress, me]) => { if (cancelled) return; setDoc(detail); setPage(progress.page_num || 0); setSavedPage(progress.page_num || 0); setCsrfToken(me.csrf_token) })"
    new_then = ".then(([detail, progress, me]) => { if (cancelled) return; const userId = Number(me.id); const userKey = `prepza-reading-progress:${userId}:${activeDocumentId}`; const localPage = (() => { try { return Math.max(0, Number(localStorage.getItem(userKey) || 0) || 0) } catch { return 0 } })(); const restoredPage = Math.max(0, localPage || progress.page_num || 0); setReaderUserId(userId); setDoc(detail); setPage(restoredPage); setSavedPage(progress.page_num || 0); saveLocalPage(restoredPage, userKey); setCsrfToken(me.csrf_token) })"
    if old_then in section:
        section = section.replace(old_then, new_then, 1)

    old_post = "api(`/documents/${activeDocumentId}/reading`, {method:'POST', headers:{'X-CSRF-Token':csrfToken}, body:JSON.stringify({page_num:page})}).then(()=>setSavedPage(page)).catch(()=>{})"
    new_post = "api(`/documents/${activeDocumentId}/reading`, {method:'POST', headers:{'X-CSRF-Token':csrfToken, 'X-Prepza-Offline-Queue':'true'}, body:JSON.stringify({page_num:page})}).then(()=>setSavedPage(page)).catch(()=>{})"
    if old_post in section:
        section = section.replace(old_post, new_post, 1)

    old_page_effect = "    if (activeDocumentId == null || !csrfToken || page === savedPage) return\n    const timer = setTimeout(() => api(`/documents/${activeDocumentId}/reading`, {method:'POST', headers:{'X-CSRF-Token':csrfToken, 'X-Prepza-Offline-Queue':'true'}, body:JSON.stringify({page_num:page})}).then(()=>setSavedPage(page)).catch(()=>{}), 250)"
    new_page_effect = "    if (activeDocumentId == null || page === savedPage) return\n    saveLocalPage(page)\n    if (!csrfToken) return\n    const timer = setTimeout(() => api(`/documents/${activeDocumentId}/reading`, {method:'POST', headers:{'X-CSRF-Token':csrfToken, 'X-Prepza-Offline-Queue':'true'}, body:JSON.stringify({page_num:page})}).then(()=>setSavedPage(page)).catch(()=>{}), 250)"
    if old_page_effect in section:
        section = section.replace(old_page_effect, new_page_effect, 1)

    old_page_url = "  const pageUrl = `/documents/${activeDocumentId}/reading/page/${current}`"
    new_page_url = "  const pageUrl = `/documents/${activeDocumentId}/reading/page/${current}${readerUserId != null ? `?prepza_user=${readerUserId}` : ''}`"
    if old_page_url in section and 'prepza_user=' not in section:
        section = section.replace(old_page_url, new_page_url, 1)

    return s[:start] + section + s[end:]


def patch_offline_reading_gate(s):
    marker = "    if (/^\\/documents\\/\\d+\\/reading$/.test(cleanPath)) return { page_num: 0 } as T"
    replacement = "    if (/^\\/documents\\/\\d+\\/reading$/.test(cleanPath)) {\n      const documentId = Number(cleanPath.split('/')[2])\n      let page_num = 0\n      try { page_num = Math.max(0, Number(localStorage.getItem(`prepza-reading-progress:${offlineUserId}:${documentId}`) || 0) || 0) } catch (_) {}\n      return { page_num } as T\n    }"
    if marker in s:
        s = s.replace(marker, replacement, 1)
    elif 'localStorage.getItem(`prepza-reading-progress:${offlineUserId}:${documentId}`)' not in s:
        raise SystemExit('offline reading gate anchor not found')
    return s


def patch_api_gate(s):
    marker = "    if (/^\\/documents\\/\\d+\\/reading$/.test(cleanPath)) return { page_num: 0 } as T"
    return patch_offline_reading_gate(s)


def main():
    s = APP.read_text()
    s = patch_study_hub(s)
    s = patch_native_reader(s)
    s = patch_offline_reading_gate(s)
    required = [
        'const [readingPage, setReadingPage] = useState(0)',
        'const [readerUserId, setReaderUserId] = useState<number | null>(null)',
        "X-Prepza-Offline-Queue':'true'",
        'prepza-reading-progress:',
        'prepza_user=',
        'localStorage.getItem(`prepza-reading-progress:${offlineUserId}:${documentId}`)',
    ]
    missing = [marker for marker in required if marker not in s]
    if missing:
        raise SystemExit(f'document study progress verification failed: {missing}')
    APP.write_text(s)
    print('document study progress patch applied and verified.')


if __name__ == '__main__':
    main()
