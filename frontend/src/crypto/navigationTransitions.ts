let installed = false

function isPrimaryNavButton(button: HTMLElement): boolean {
  const rect = button.getBoundingClientRect()
  if (rect.width < 35 || rect.height < 35) return false
  if (rect.bottom < window.innerHeight - 120) return false
  return Boolean(button.querySelector('svg'))
}

function animate(direction: 'left' | 'right') {
  const root = document.getElementById('root')
  if (!root) return
  root.animate(
    direction === 'left'
      ? [{ transform: 'translateX(0)', opacity: 1 }, { transform: 'translateX(-18px)', opacity: .92 }, { transform: 'translateX(0)', opacity: 1 }]
      : [{ transform: 'translateX(0)', opacity: 1 }, { transform: 'translateX(18px)', opacity: .92 }, { transform: 'translateX(0)', opacity: 1 }],
    { duration: 220, easing: 'cubic-bezier(.22,.61,.36,1)' },
  )
}

export function installNavigationTransitions(): void {
  if (installed || typeof document === 'undefined') return
  installed = true

  document.addEventListener('click', event => {
    const target = event.target instanceof HTMLElement ? event.target.closest('button') as HTMLElement | null : null
    if (!target || !isPrimaryNavButton(target)) return

    const buttons = Array.from(document.querySelectorAll<HTMLButtonElement>('button')).filter(isPrimaryNavButton)
    const unique = buttons.filter((button, index) => buttons.findIndex(item => Math.abs(item.getBoundingClientRect().left - button.getBoundingClientRect().left) < 2) === index)
    const index = unique.findIndex(button => button === target)
    if (index < 0) return

    const active = unique.findIndex(button => {
      const style = getComputedStyle(button)
      return style.fontWeight === '800' || style.fontWeight === '700' || button.getAttribute('aria-current') === 'page'
    })
    if (active < 0 || active === index) return
    animate(index > active ? 'left' : 'right')
  }, true)
}
