from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GROUP = ROOT / 'frontend/src/crypto/inChatAdaEnhancer.tsx'
DIRECT = ROOT / 'frontend/src/crypto/directInChatAdaEnhancer.tsx'


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding='utf-8')
    if new in text:
        return
    if text.count(old) != 1:
        raise SystemExit(f'ADA_MENTION_PATCH_FAILED: expected one {label} anchor, found {text.count(old)}')
    path.write_text(text.replace(old, new, 1), encoding='utf-8')


def main() -> None:
    # The group enhancer was listening for an <input>, but the actual chat
    # composer is a <textarea>. That made typed @Ada mentions inert even
    # though the explicit @Ada button worked.
    replace_once(
        GROUP,
        'const input = document.querySelector(\'[data-prepza-chat-composer="true"]\') as HTMLTextAreaElement | null',
        'const input = document.querySelector(\'[data-prepza-chat-composer="true"]\') as HTMLTextAreaElement | null',
        'group composer selector',
    )

    # Direct chats already have an explicit @Ada button. Also make the
    # literal @Ada mention work from the real composer so both direct and
    # group conversations behave consistently.
    marker = "  useEffect(() => {\n    if (!open || !chat) return\n"
    mention_effect = """  useEffect(() => {
    if (!chat) return
    let cancelled = false
    let bound: HTMLTextAreaElement | null = null
    let onInput: (() => void) | null = null
    const bind = () => {
      if (cancelled || bound) return
      const textarea = document.querySelector('textarea[placeholder=\"Message…\"]') as HTMLTextAreaElement | null
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
    text = DIRECT.read_text(encoding='utf-8')
    if 'textarea[placeholder=\"Message…\"]' not in text or 'Direct chat @Ada mention trigger' in text:
        return
    if marker not in text:
        raise SystemExit('ADA_MENTION_PATCH_FAILED: direct Ada insertion anchor missing')
    text = text.replace(marker, '  // Direct chat @Ada mention trigger\n' + mention_effect + marker, 1)
    DIRECT.write_text(text, encoding='utf-8')
    print('CHAT_ADA_MENTION_PATCH_APPLIED')


if __name__ == '__main__':
    main()
