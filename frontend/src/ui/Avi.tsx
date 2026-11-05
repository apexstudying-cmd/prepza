import { N } from '../theme/theme'

export default function Avi({ name, size = 38, emoji }: { name: string; size?: number; emoji?: string }) {
  return (
    <div style={{ width: size, height: size, background: `linear-gradient(135deg,${N.navy2},${N.navy3})`, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: emoji ? size * 0.45 : size * 0.33, fontWeight: 800, color: N.gold, flexShrink: 0, fontFamily: 'Plus Jakarta Sans' }}>
      {emoji ?? name}
    </div>
  )
}

