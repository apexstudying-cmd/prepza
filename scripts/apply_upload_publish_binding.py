from pathlib import Path

p = Path("frontend/src/App.tsx")
s = p.read_text()

old_type = "type PublishableDoc = { id: number; title: string; file_type: string | null; page_count: number | null }"
new_type = "type PublishableDoc = { id: number; title: string; status: string; file_type: string | null; page_count: number | null }"
if old_type in s:
    s = s.replace(old_type, new_type, 1)
elif new_type not in s:
    raise SystemExit("PublishableDoc type anchor not found")

old_signature = "function PublishLibraryScreen({ setScreen }: { setScreen: (s: Screen) => void }) {"
new_signature = "function PublishLibraryScreen({ setScreen, activeDocumentId }: { setScreen: (s: Screen) => void; activeDocumentId: number | null }) {"
if old_signature in s:
    s = s.replace(old_signature, new_signature, 1)
elif new_signature not in s:
    raise SystemExit("PublishLibraryScreen signature anchor not found")

old_fetch = '''  useEffect(() => {
    api<{ csrf_token: string }>('/me').then(me => setCsrfToken(me.csrf_token)).catch(() => {})
    api<{ documents: { id: number; title: string; status: string; file_type: string | null; page_count: number | null }[] }>('/documents')
      .then(res => setDocs(res.documents.filter(d => d.status === 'ready')))
      .catch(() => setDocsError('Could not load your documents - check your connection and try again.'))
      .finally(() => setDocsLoading(false))
  }, [])

  const canProceed1 = selectedDocId != null && title.trim().length > 0
'''
new_fetch = '''  useEffect(() => {
    api<{ csrf_token: string }>('/me').then(me => setCsrfToken(me.csrf_token)).catch(() => {})
    api<{ documents: { id: number; title: string; status: string; file_type: string | null; page_count: number | null }[] }>('/documents')
      .then(res => {
        const available = res.documents.filter(d => d.status === 'ready' || d.id === activeDocumentId)
        setDocs(available)
        const uploaded = activeDocumentId == null ? null : available.find(d => d.id === activeDocumentId)
        if (uploaded) {
          setSelectedDocId(uploaded.id)
          setTitle(uploaded.title)
        }
      })
      .catch(() => setDocsError('Could not load your documents - check your connection and try again.'))
      .finally(() => setDocsLoading(false))
  }, [activeDocumentId])

  const selectedDoc = selectedDocId == null ? null : docs.find(d => d.id === selectedDocId) || null
  const canProceed1 = selectedDocId != null && title.trim().length > 0 && selectedDoc?.status === 'ready'
'''
if old_fetch in s:
    s = s.replace(old_fetch, new_fetch, 1)
elif new_fetch not in s:
    raise SystemExit("publish document-loading anchor not found")

old_selected_card = """                <div style={{ fontSize: 11, color: T.textMuted, marginTop: 2 }}>{(d.file_type || '').toUpperCase()}{d.page_count != null ? ` · ${d.page_count} pages` : ''}</div>
"""
new_selected_card = """                <div style={{ fontSize: 11, color: T.textMuted, marginTop: 2 }}>
                  {(d.file_type || '').toUpperCase()}{d.page_count != null ? ` · ${d.page_count} pages` : ''}{d.status !== 'ready' ? ` · ${d.status === 'processing' ? 'Preparing…' : d.status}` : ''}
                </div>
"""
if old_selected_card in s:
    s = s.replace(old_selected_card, new_selected_card, 1)
elif new_selected_card not in s:
    raise SystemExit("publish document card metadata anchor not found")

old_continue = """            Continue
          </button>
        </div>
      )}
"""
new_continue = """            {selectedDoc?.status === 'ready' ? 'Continue' : 'Document still preparing…'}
          </button>
        </div>
      )}
"""
if old_continue in s:
    s = s.replace(old_continue, new_continue, 1)
elif new_continue not in s:
    raise SystemExit("publish step 1 continue button anchor not found")

old_case = "      case 'publish-library':   return <PublishLibraryScreen setScreen={setScreen} />\n"
new_case = "      case 'publish-library':   return <PublishLibraryScreen setScreen={setScreen} activeDocumentId={activeDocumentId} />\n"
if old_case in s:
    s = s.replace(old_case, new_case, 1)
elif new_case not in s:
    raise SystemExit("publish-library render case anchor not found")

p.write_text(s)
print("uploaded document publishing binding patch applied")
