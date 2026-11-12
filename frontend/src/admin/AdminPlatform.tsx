import { useState } from 'react'
import { N, useTheme } from '../theme/theme'
import AdminSection from './AdminSection'

export const PAYMENT_STATUS_META: Record<string, { icon: string; color: string; label: string }> = {
  success: { icon: '✅', color: '#4CC97B', label: 'Success' },
  pending: { icon: '⏳', color: '#D97706', label: 'Pending' },
  failed: { icon: '❌', color: '#C94C4C', label: 'Failed' },
  refunded: { icon: '↩️', color: '#6B7280', label: 'Refunded' },
}

const adminNavGroups = [
  { key:'dashboard', label:'Dashboard', icon:'dashboard', items:[{key:'dashboard',label:'Overview'}] },
  { key:'users', label:'Users', icon:'users', items:[{key:'users',label:'Students'},{key:'groups',label:'Groups'},{key:'moderation',label:'Moderation'}] },
  { key:'payments', label:'Payments', icon:'payments', items:[{key:'payments',label:'Student payments'},{key:'b2b-finance',label:'B2B finance'},{key:'ambassadors',label:'Ambassadors'}] },
  { key:'organisations', label:'Organizations', icon:'org', items:[{key:'organisations',label:'Organizations'},{key:'opportunities',label:'Opportunities'},{key:'promotions',label:'Promotions'}] },
  { key:'content', label:'Content', icon:'content', items:[{key:'content',label:'Library & review'},{key:'universities',label:'Universities'}] },
  { key:'communications', label:'Communications', icon:'communications', items:[{key:'communications',label:'Announcements'}] },
  { key:'system', label:'System', icon:'system', items:[{key:'operations',label:'Operations'},{key:'system',label:'Infrastructure'},{key:'ai-usage',label:'AI & usage'},{key:'analytics',label:'Analytics'},{key:'settings',label:'Settings'}] },
] as const

function AdminNavIcon({name}:{name:string}) {
  const common={viewBox:'0 0 24 24',fill:'none',stroke:'currentColor',strokeWidth:1.8,strokeLinecap:'round' as const,strokeLinejoin:'round' as const,"aria-hidden":true}
  if(name==='dashboard') return <svg width="18" height="18" {...common}><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>
  if(name==='users') return <svg width="18" height="18" {...common}><circle cx="9" cy="8" r="3"/><path d="M3 20c0-3 2.7-5 6-5s6 2 6 5"/><path d="M16 6.5a2.5 2.5 0 0 1 0 4.8M18 15c1.9.7 3 2.1 3 4"/></svg>
  if(name==='payments') return <svg width="18" height="18" {...common}><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 9h18M7 14h4"/></svg>
  if(name==='org') return <svg width="18" height="18" {...common}><path d="M4 21V5l8-3 8 3v16M8 9h2M14 9h2M8 13h2M14 13h2M8 17h2M14 17h2"/></svg>
  if(name==='content') return <svg width="18" height="18" {...common}><path d="M5 3h10l4 4v14H5z"/><path d="M15 3v5h5M8 12h8M8 16h6"/></svg>
  if(name==='communications') return <svg width="18" height="18" {...common}><path d="M4 5h16v11H8l-4 4z"/><path d="M8 9h8M8 12h5"/></svg>
  return <svg width="18" height="18" {...common}><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-1.8 1.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6V20h-2.6v-.1a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1-1.8-1.8.1-.1A1.7 1.7 0 0 0 8 15a1.7 1.7 0 0 0-1.6-1H6v-2.6h.4A1.7 1.7 0 0 0 8 10a1.7 1.7 0 0 0-.3-1.9l-.1-.1 1.8-1.8.1.1a1.7 1.7 0 0 0 1.9.3 1.7 1.7 0 0 0 1-1.6V5H15v.1a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1 1.8 1.8-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.1v2.6H21a1.7 1.7 0 0 0-1.6 1z"/></svg>
}

export default function AdminPlatform({ onExit }: { onExit: () => void }) {
  const { mode, tokens: T } = useTheme()
  const [section, setSection] = useState('dashboard')
  const [adminExpanded, setAdminExpanded] = useState<Record<string, boolean>>({})
  const sectionLabels: Record<string, string> = { dashboard: 'Dashboard', users: 'Users', content: 'Content', universities: 'Universities', community: 'Community', opportunities: 'Opportunities', promotions: 'Promotions', organisations: 'Organisations', 'ai-usage': 'AI & Usage', payments: 'Payments', 'b2b-finance': 'B2B Finance', communications: 'Communications', analytics: 'Analytics', moderation: 'Moderation', system: 'System', operations: 'Operations', settings: 'Settings', groups: 'Groups' }

  return (
    <div style={{ display: 'flex', width: '100vw', height: '100vh', background: T.pageBg, fontFamily: 'Plus Jakarta Sans', overflow: 'hidden' }}>
      {/* Sidebar */}
      <div style={{ width: 220, background: N.navy, display: 'flex', flexDirection: 'column', flexShrink: 0, overflowY: 'auto' }} className="scrollbar-hide">
        <div style={{ padding: '20px 16px 14px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <img src="/icon-192.png" alt="Prepza" style={{ width: 32, height: 32, borderRadius: 9 }} />
            <div>
              <div style={{ fontWeight: 800, fontSize: 14, color: '#fff', letterSpacing: '-0.3px' }}>PREPZA</div>
              <div style={{ fontSize: 10, color: N.gold, fontWeight: 600 }}>Admin Platform</div>
            </div>
          </div>
        </div>
        <div style={{ height: 1, background: 'rgba(255,255,255,0.08)', margin: '0 14px 10px' }} />
        <div style={{ flex: 1, padding: '0 8px' }}>
          {adminNavGroups.map(group => {
            const open = Boolean(adminExpanded[group.key])
            const activeGroup = group.items.some(item => item.key === section)
            return <div key={group.key} style={{marginBottom:3}}>
              <button type="button" onClick={()=>setAdminExpanded(v=>({...v,[group.key]:!open}))} style={{width:'100%',display:'flex',alignItems:'center',gap:10,padding:'9px 12px',borderRadius:10,background:activeGroup?'rgba(201,168,76,0.10)':'transparent',border:'1px solid transparent',cursor:'pointer',color:activeGroup?N.gold:'rgba(255,255,255,.78)'}}>
                <AdminNavIcon name={group.icon}/><span style={{flex:1,fontSize:13,fontWeight:activeGroup?750:600,textAlign:'left'}}>{group.label}</span><span style={{fontSize:12,opacity:.55}}>{open?'−':'+'}</span>
              </button>
              {open && <div style={{padding:'2px 0 5px 28px'}}>
                {group.items.map(item=><button type="button" key={item.key} onClick={()=>setSection(item.key)} style={{width:'100%',display:'flex',alignItems:'center',padding:'7px 10px',border:0,borderLeft:`2px solid ${section===item.key?N.gold:'rgba(255,255,255,.08)'}`,background:'transparent',color:section===item.key?N.gold:'rgba(255,255,255,.52)',fontSize:11,cursor:'pointer',textAlign:'left'}}>{item.label}</button>)}
              </div>}
            </div>
          })}
        </div>
        <div style={{ padding: '10px 8px 20px' }}>
          <div style={{ height: 1, background: 'rgba(255,255,255,0.08)', margin: '0 6px 10px' }} />
          <div style={{ padding: '10px 12px', display: 'flex', gap: 10, alignItems: 'center' }}>
            <div style={{ width: 32, height: 32, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: 13, color: N.navy, flexShrink: 0 }}>PA</div>
            <div style={{ flex: 1 }}><div style={{ fontSize: 12, fontWeight: 700, color: '#fff' }}>Prepza Admin</div><div style={{ fontSize: 10, color: 'rgba(255,255,255,0.4)' }}>Super Admin</div></div>
          </div>
          <button onClick={onExit} style={{ width: '100%', display: 'flex', alignItems: 'center', gap: 10, padding: '9px 12px', borderRadius: 10, background: 'transparent', border: '1px solid rgba(255,255,255,0.1)', cursor: 'pointer', marginTop: 6 }}>
            <span style={{ fontSize: 14 }}>📱</span>
            <span style={{ fontSize: 12, fontWeight: 600, color: 'rgba(255,255,255,0.5)' }}>Student App</span>
          </button>
        </div>
      </div>

      {/* Main */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, overflow: 'hidden' }}>
        {/* Top bar */}
        <div style={{ background: T.card, borderBottom: `1px solid ${T.border}`, padding: '0 24px', height: 60, display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexShrink: 0 }}>
          <div>
            <div style={{ fontWeight: 800, fontSize: 18, color: T.text }}>{sectionLabels[section]}</div>
            <div style={{ fontSize: 11, color: T.textMuted }}>Prepza Admin · {new Date().toLocaleDateString('en-KE', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}</div>
          </div>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
            <div style={{ display: 'flex', gap: 6, alignItems: 'center', background: '#F0FDF4', border: '1px solid #BBF7D0', borderRadius: 99, padding: '4px 12px' }}>
              <div style={{ width: 7, height: 7, borderRadius: '50%', background: '#16A34A' }} />
              <span style={{ fontSize: 11, fontWeight: 600, color: '#16A34A' }}>All Systems Operational</span>
            </div>
            <button style={{ width: 36, height: 36, background: (mode === 'dark' ? 'rgba(255,255,255,0.08)' : '#F3F4F6'), border: 'none', borderRadius: 10, cursor: 'pointer', fontSize: 16 }}>🔔</button>
            <div style={{ width: 36, height: 36, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: 13, color: N.navy }}>PA</div>
          </div>
        </div>

        {/* Content */}
        <div style={{ flex: 1, overflowY: 'auto', padding: 24 }} className="scrollbar-hide">
          <AdminSection section={section} setSection={setSection} />
        </div>
      </div>
    </div>
  )
}

// ─── APP SHELL ────────────────────────────────────────────────────────────────
// ─── AMBASSADOR PROGRAM ────────────────────────────────────────────────────
// Wired to the live Chunk 9 backend endpoints:
//   GET  /ambassador/status              -> { enrolled, status, referral_code, rejection_reason }
//   GET  /ambassador/dashboard           -> tier/earnings/funnel snapshot
//   GET  /ambassador/referrals           -> { referrals: [...] }
//   GET  /ambassador/payouts             -> { payouts: [...] }
//   POST /ambassador/apply               -> { id, status, referral_code }
//   POST /ambassador/payouts/request     -> { id, amount, status }
// Follows this file's existing per-screen CSRF pattern (fetch /me once on
// mount, store csrf_token in local state, attach it to mutating calls).
