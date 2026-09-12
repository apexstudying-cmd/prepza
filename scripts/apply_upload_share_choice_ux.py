from pathlib import Path

p = Path("frontend/src/App.tsx")
s = p.read_text()

old_type = "  | 'home' | 'explore' | 'create-modal' | 'chats' | 'profile'\n"
new_type = old_type + "  | 'upload-share-choice'\n"
if "| 'upload-share-choice'" not in s:
    if old_type not in s:
        raise SystemExit("Screen type anchor not found")
    s = s.replace(old_type, new_type, 1)

old_upload = """      setActiveDocumentId(created.document_id)\n      setScreen('processing')\n"""
new_upload = """      setActiveDocumentId(created.document_id)\n      setScreen('upload-share-choice')\n"""
if old_upload in s:
    s = s.replace(old_upload, new_upload, 1)
elif new_upload not in s:
    raise SystemExit("upload completion navigation anchor not found")

marker = "// ─── PROCESSING ───────────────────────────────────────────────────────────────\n"
component = r'''// ─── POST-UPLOAD STUDYHUB / LIBRARY CHOICE ────────────────────────────────────
function UploadShareChoiceScreen({ setScreen, activeDocumentId }: { setScreen: (s: Screen) => void; activeDocumentId: number | null }) {
  const { tokens: T } = useTheme()
  const [doc, setDoc] = useState<DocumentDetail | null>(null)

  useEffect(() => {
    if (activeDocumentId == null) return
    api<DocumentDetail>(`/documents/${activeDocumentId}`)
      .then(setDoc)
      .catch(() => {})
  }, [activeDocumentId])

  const openStudyHub = () => setScreen('processing')
  const publish = () => setScreen('publish-library')

  return (
    <div style={{ flex: 1, overflowY: 'auto', background: T.pageBg }} className="scrollbar-hide">
      <div style={{ background: N.navy, padding: '0 18px 24px' }}>
        <TopBar title="Document added to StudyHub" onBack={openStudyHub} />
      </div>
      <div style={{ padding: '24px 18px 40px', display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center' }}>
        <div style={{ width: 72, height: 72, borderRadius: 22, background: `${N.gold}18`, border: `1px solid ${N.gold}40`, display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 18, fontSize: 34 }}>✓</div>
        <div style={{ fontWeight: 850, fontSize: 21, color: T.text, marginBottom: 8 }}>Your document is in StudyHub</div>
        <div style={{ fontSize: 13, color: T.textMuted, lineHeight: 1.65, maxWidth: 360, marginBottom: 8 }}>
          {doc?.title ? <><strong style={{ color: T.text }}>{doc.title}</strong> is safely in your personal StudyHub.</> : 'Your document is safely in your personal StudyHub.'}
        </div>
        <div style={{ fontSize: 12, color: T.textMuted, lineHeight: 1.6, maxWidth: 360, marginBottom: 26 }}>
          It is private by default. Sharing to Library is optional and requires your explicit choice.
        </div>

        <div style={{ width: '100%', maxWidth: 420, display: 'flex', flexDirection: 'column', gap: 10 }}>
          <button onClick={publish} style={{ width: '100%', background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, border: 'none', borderRadius: 16, padding: '15px 16px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 850, fontSize: 14, boxShadow: `0 6px 22px ${N.gold}35` }}>
            Share to Prepza Library
            <span style={{ display: 'block', fontSize: 11, fontWeight: 600, opacity: 0.7, marginTop: 3 }}>Help other students · Earn XP on approval</span>
          </button>
          <button onClick={openStudyHub} style={{ width: '100%', background: T.card, color: T.text, border: `1px solid ${T.border}`, borderRadius: 16, padding: '14px 16px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 750, fontSize: 14 }}>
            Study my document
          </button>
          <button onClick={openStudyHub} style={{ background: 'none', border: 'none', color: T.textMuted, padding: '10px 8px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 650, fontSize: 12 }}>
            Maybe later
          </button>
        </div>
      </div>
    </div>
  )
}

'''
if component not in s:
    if marker not in s:
        raise SystemExit("Processing component marker not found")
    s = s.replace(marker, component + marker, 1)

old_case = "      case 'upload':            return <UploadScreen setScreen={setScreen} setActiveDocumentId={setActiveDocumentId} />\n"
new_case = old_case + "      case 'upload-share-choice': return <UploadShareChoiceScreen setScreen={setScreen} activeDocumentId={activeDocumentId} />\n"
if "case 'upload-share-choice':" not in s:
    if old_case not in s:
        raise SystemExit("upload render case anchor not found")
    s = s.replace(old_case, new_case, 1)

old_no_nav = "  const noNav: Screen[] = ['splash','login','forgot-password','signup','check-email','complete-profile','reset-password','verify-confirm','processing','payment','payment-success','payment-failure']\n"
new_no_nav = "  const noNav: Screen[] = ['splash','login','forgot-password','signup','check-email','complete-profile','reset-password','verify-confirm','processing','upload-share-choice','payment','payment-success','payment-failure']\n"
if old_no_nav in s:
    s = s.replace(old_no_nav, new_no_nav, 1)
elif new_no_nav not in s:
    raise SystemExit("noNav anchor not found")

p.write_text(s)
print("post-upload StudyHub/Library choice UX patch applied")
