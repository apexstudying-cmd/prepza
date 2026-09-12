from pathlib import Path

APP = Path('frontend/src/App.tsx')


def main():
    s = APP.read_text()

    old_state = "  const [showCreate, setShowCreate] = useState(false)\n"
    new_state = "  const [showCreate, setShowCreate] = useState(false)\n  const [readingPage, setReadingPage] = useState(0)\n"
    if old_state in s and new_state not in s:
        s = s.replace(old_state, new_state, 1)
    elif new_state not in s:
        raise SystemExit('study hub state anchor not found')

    old_effect = '''    setLoading(true)\n    setError('')\n    api<DocumentDetail>(`/documents/${activeDocumentId}`)\n      .then(data => { if (!cancelled) setDocument(data) })\n      .catch(err => { if (!cancelled) setError(err instanceof ApiError ? err.message : 'Could not open this document.') })\n      .finally(() => { if (!cancelled) setLoading(false) })\n'''
    new_effect = '''    setLoading(true)\n    setError('')\n    Promise.all([\n      api<DocumentDetail>(`/documents/${activeDocumentId}`),\n      api<{ page_num: number }>(`/documents/${activeDocumentId}/reading`),\n    ])\n      .then(([data, progress]) => {\n        if (cancelled) return\n        setDocument(data)\n        setReadingPage(Math.max(0, progress.page_num || 0))\n      })\n      .catch(err => { if (!cancelled) setError(err instanceof ApiError ? err.message : 'Could not open this document.') })\n      .finally(() => { if (!cancelled) setLoading(false) })\n'''
    if old_effect in s:
        s = s.replace(old_effect, new_effect, 1)
    elif new_effect not in s:
        raise SystemExit('study hub loading effect not found')

    old_header = '''        <div style={{ color: '#fff', fontSize: 20, fontWeight: 850, lineHeight: 1.25 }} className="line-clamp-2">{document.title}</div>\n        <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: 11, marginTop: 6 }}>\n          {document.page_count ? `${document.page_count} pages` : 'Document'}{document.file_type ? ` · ${document.file_type.toUpperCase()}` : ''}\n        </div>\n'''
    new_header = '''        <div style={{ color: '#fff', fontSize: 20, fontWeight: 850, lineHeight: 1.25 }} className="line-clamp-2">{document.title}</div>\n        <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: 11, marginTop: 6 }}>\n          {document.page_count ? `${document.page_count} pages` : 'Document'}{document.file_type ? ` · ${document.file_type.toUpperCase()}` : ''}\n        </div>\n        {document.page_count ? (() => {\n          const studiedPercent = Math.min(100, Math.round((Math.min(readingPage + 1, document.page_count) / document.page_count) * 100))\n          return <div style={{ marginTop: 12 }}>\n            <div style={{ display: 'flex', justifyContent: 'space-between', color: 'rgba(255,255,255,0.62)', fontSize: 10, marginBottom: 5 }}>\n              <span>Study progress</span><span>{studiedPercent}%</span>\n            </div>\n            <div style={{ height: 5, borderRadius: 999, background: 'rgba(255,255,255,0.12)', overflow: 'hidden' }}>\n              <div style={{ height: '100%', width: `${studiedPercent}%`, background: N.gold, borderRadius: 999 }} />\n            </div>\n          </div>\n        })() : null}\n'''
    if old_header in s:
        s = s.replace(old_header, new_header, 1)
    elif new_header not in s:
        raise SystemExit('study hub header anchor not found')

    APP.write_text(s)
    print('document study progress patch applied')


if __name__ == '__main__':
    main()
