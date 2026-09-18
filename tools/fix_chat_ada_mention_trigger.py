from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GROUP = ROOT / 'frontend/src/crypto/inChatAdaEnhancer.tsx'
DIRECT = ROOT / 'frontend/src/crypto/directInChatAdaEnhancer.tsx'

def main() -> None:
    # The group enhancer already targets the shared textarea marker in the
    # current chat architecture. Keep this step idempotent; never rewrite the
    # composer through brittle string matching.
    group_text = GROUP.read_text(encoding='utf-8')
    if 'data-prepza-chat-composer="true"' not in group_text:
        raise SystemExit('ADA_MENTION_PATCH_FAILED: group composer marker missing')

    text = DIRECT.read_text(encoding='utf-8')
    if 'textarea[placeholder="Message…"]' not in text or 'Direct chat @Ada mention trigger' in text:
        print('CHAT_ADA_MENTION_PATCH_ALREADY_READY')
        return

    marker = "  useEffect(() => {\n    if (!open || !chat) return\n"
    mention_effect = """  useEffect(() => {
    if (!chat) return
    let cancelled = false
    let bound: HTMLTextAreaElement | null = null
    let onInput: (() => void) | null = null
    const bind = () => {
      if (cancelled || bound) return
      const textarea = document.querySelector('[data-prepza-chat-composer="true"]') as HTMLTextAreaElement | null
      if (!textarea) return
      bound = textarea
      onInput = () => { if (/(^|\\s)@ada\\b/i.test(textarea.value)) setOpen(true) }
      textarea.addEventListener('input', onInput)
      onInput()
    }
    bind()
    const observer = new MutationObserver(bind)
    observer.observe(document.body, { childList: true, subtree: true })
    const timer = window.setInterval(bind, 350)
    return () => {
      cancelled = true
      observer.disconnect()
      window.clearInterval(timer)
      if (bound && onInput) bound.removeEventListener('input', onInput)
    }
  }, [chat?.conversationId])
"""
    if marker not in text:
        raise SystemExit('ADA_MENTION_PATCH_FAILED: direct Ada insertion anchor missing')
    DIRECT.write_text(text.replace(marker, '  // Direct chat @Ada mention trigger\n' + mention_effect + marker, 1), encoding='utf-8')
    print('CHAT_ADA_MENTION_PATCH_APPLIED')

if __name__ == '__main__':
    main()
