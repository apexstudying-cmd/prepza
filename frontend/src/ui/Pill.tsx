import { N } from '../theme/theme'

export default function Pill({ text, color = N.gold, bg }: { text: string; color?: string; bg?: string }) {
  return <span style={{ background: bg ?? color + '20', color, border: `1px solid ${color}33`, borderRadius: 99, fontSize: 10, fontWeight: 700, padding: '2px 9px', letterSpacing: 0.3, whiteSpace: 'nowrap' }}>{text}</span>
}
