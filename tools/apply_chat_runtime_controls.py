from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHAT = ROOT / 'frontend' / 'src' / 'crypto' / 'WhatsAppChatExperience.tsx'
s = CHAT.read_text(encoding='utf-8')

MARK = 'PREPZA_RUNTIME_CHAT_CONTROLS'
if MARK in s:
    print(f'{MARK}_ALREADY_PRESENT')
else:
    anchor = "  useEffect(() => { csrfTokenRef.current = csrfToken }, [csrfToken])"
    if anchor not in s:
        raise SystemExit('Runtime chat controls: stable csrf effect anchor missing')

    effect = r'''  // PREPZA_RUNTIME_CHAT_CONTROLS
  // Runtime fallback: anchor controls to the actual visible composer, not to a
  // particular header class. This keeps voice/call controls visible even when
  // the chat shell changes its layout or the header is temporarily absent.
  useEffect(() => {
    const requestVoice = () => window.dispatchEvent(new CustomEvent('prepza-request-voice-recording'))
    const requestCall = (kind: 'voice' | 'video') => window.dispatchEvent(new CustomEvent('prepza-request-call', { detail: { kind } }))

    const addControls = () => {
      const textarea = Array.from(document.querySelectorAll('textarea')).find((node) => {
        const element = node as HTMLTextAreaElement
        return element.offsetParent !== null && !element.disabled
      }) as HTMLTextAreaElement | undefined
      if (!textarea) return

      const composer = textarea.parentElement as HTMLElement | null
      if (composer && !document.querySelector('[data-prepza-runtime-voice]')) {
        const button = document.createElement('button')
        button.type = 'button'
        button.dataset.prepzaRuntimeVoice = 'true'
        button.setAttribute('aria-label', 'Record voice note')
        button.title = 'Record voice note'
        button.textContent = '◉'
        button.style.cssText = 'width:40px;height:40px;flex:0 0 40px;border:0;border-radius:12px;background:#f1f2f4;color:#5e6470;font-weight:900;font-size:18px;cursor:pointer;margin-right:7px;align-self:center;'
        button.addEventListener('click', requestVoice)
        composer.insertBefore(button, textarea)
      }

      const callHost = (document.querySelector('.prepza-wa-head') as HTMLElement | null) || composer
      if (callHost && !callHost.querySelector('[data-prepza-runtime-call]') && !document.querySelector('[data-prepza-runtime-call]')) {
        const wrap = document.createElement('div')
        wrap.dataset.prepzaRuntimeCall = 'true'
        wrap.style.cssText = 'display:flex;gap:7px;margin-left:7px;flex:0 0 auto;align-items:center;'
        for (const [kind, label, glyph] of [['voice', 'Start voice call', '☎'], ['video', 'Start video call', '▣']] as const) {
          const button = document.createElement('button')
          button.type = 'button'
          button.setAttribute('aria-label', label)
          button.title = label.replace('Start ', '')
          button.textContent = glyph
          button.style.cssText = 'width:34px;height:34px;border:0;border-radius:10px;background:#f1f2f4;color:#5e6470;cursor:pointer;font-size:16px;'
          button.addEventListener('click', () => requestCall(kind))
          wrap.appendChild(button)
        }
        callHost.appendChild(wrap)
      }
    }

    addControls()
    const observer = new MutationObserver(addControls)
    observer.observe(document.body, { childList: true, subtree: true })
    const timer = window.setInterval(addControls, 500)
    return () => { observer.disconnect(); window.clearInterval(timer) }
  }, [])

  useEffect(() => {
    const onVoice = () => { void startVoiceRecording() }
    const onCall = (event: Event) => {
      const kind = (event as CustomEvent<{ kind?: 'voice' | 'video' }>).detail?.kind
      if (!kind || !detail || detail.is_group || !selectedId || !meId) return
      const peer = detail.participants.find(item => item.user_id !== meId)
      if (!peer) return
      window.dispatchEvent(new CustomEvent('prepza-start-call', { detail: { conversationId: selectedId, peerId: peer.user_id, peerName: peer.display_name, kind } }))
    }
    window.addEventListener('prepza-request-voice-recording', onVoice)
    window.addEventListener('prepza-request-call', onCall)
    return () => { window.removeEventListener('prepza-request-voice-recording', onVoice); window.removeEventListener('prepza-request-call', onCall) }
  }, [detail, selectedId, meId])
'''
    s = s.replace(anchor, anchor + '\n' + effect, 1)
    CHAT.write_text(s, encoding='utf-8')
    print(f'{MARK}_APPLIED')