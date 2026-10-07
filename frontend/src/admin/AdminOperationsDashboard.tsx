import { useEffect, useState } from 'react'

type OperationsData = {
  generated_at: string
  checks: { key:string; label:string; status:string }[]
  students: {
    total:number; active_today:number; active_7d:number;
    studied_today:number; qualifying_today:number;
    study_seconds_today:number; study_seconds_7d:number;
    study_top_students: {
      id:number; display_name:string|null; email:string|null;
      last_active_at:string|null; study_seconds_today:number; study_seconds_7d:number;
    }[];
  }
  database: { ok:boolean; size_bytes:number|null; active_connections:number|null; connection_limit:number|null }
  supabase: { management_billing:string; message:string }
  ai: { queued:number; processing:number; completed:number; failed:number; podcast_queued_or_processing:number; spend_7d_usd:number }
  b2b: { active_campaigns:number; events_24h:number; delivery_spend_24h_minor:number }
  render: { configured:boolean; status:string; service_id:string|null; service:any; cpu_percent:any; memory_percent:any; http_requests:any; bandwidth_gb:any; instance_count:any; error?:string|null }
  release: { main_branch:string; provider_plan_changes_automatic:boolean; message:string }
}

function fmtSeconds(seconds:number) {
  const s = Math.max(0, Math.floor(seconds || 0))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  if (h) return m ? h+'h '+m+'m' : h+'h'
  return m ? m+'m' : s+'s'
}

function fmtBytes(n:number|null) {
  if (n == null) return '—'
  if (n >= 1e9) return (n/1e9).toFixed(2)+' GB'
  if (n >= 1e6) return (n/1e6).toFixed(1)+' MB'
  return (n/1e3).toFixed(0)+' KB'
}
function fmtMetric(v:any, suffix='') {
  if (v == null) return '—'
  if (typeof v === 'object' && v.error) return 'Unavailable'
  return Number(v).toLocaleString()+suffix
}
function tone(status:string) {
  if (status === 'ok') return {bg:'#DCFCE7',fg:'#166534'}
  if (status === 'attention') return {bg:'#FEF3C7',fg:'#92400E'}
  if (status === 'error' || status === 'suspended') return {bg:'#FEE2E2',fg:'#991B1B'}
  return {bg:'#F3F4F6',fg:'#4B5563'}
}
function Card({title,children}:{title:string;children:any}) {
  return <div style={{background:'var(--prepza-card,#fff)',border:'1px solid var(--prepza-border,#E5E7EB)',borderRadius:14,padding:18}}>
    <div style={{fontWeight:800,fontSize:14,marginBottom:14}}>{title}</div>{children}
  </div>
}
function Metric({label,value,sub}:{label:string;value:any;sub?:string}) {
  return <div style={{background:'rgba(127,127,127,.07)',borderRadius:10,padding:'12px 14px'}}>
    <div style={{fontSize:10,textTransform:'uppercase',letterSpacing:.4,opacity:.6}}>{label}</div>
    <div style={{fontSize:21,fontWeight:800,marginTop:3}}>{value}</div>
    {sub && <div style={{fontSize:10,opacity:.6,marginTop:3}}>{sub}</div>}
  </div>
}

export default function AdminOperationsDashboard() {
  const [data,setData]=useState<OperationsData|null>(null)
  const [loading,setLoading]=useState(true)
  const [error,setError]=useState('')
  const load=()=>{setLoading(true);setError('');fetch('/admin/operations',{credentials:'include'}).then(async r=>{const body=await r.json();if(!r.ok)throw new Error(body.error||'Could not load operations');return body}).then(setData).catch(e=>setError(e.message||'Could not load operations')).finally(()=>setLoading(false))}
  useEffect(()=>{load()},[])

  if (loading) return <div style={{padding:24,textAlign:'center',opacity:.65}}>Loading operations…</div>
  if (error) return <Card title="Operations"><div style={{color:'#B91C1C',fontSize:13}}>{error}</div><button onClick={load} style={{marginTop:12,padding:'8px 12px',border:0,borderRadius:8,cursor:'pointer'}}>Retry</button></Card>
  if (!data) return null

  const renderTone=tone(data.render.status)
  return <div style={{display:'flex',flexDirection:'column',gap:14}}>
    <div style={{display:'flex',justifyContent:'space-between',alignItems:'center'}}>
      <div><div style={{fontSize:20,fontWeight:850}}>Operations</div><div style={{fontSize:11,opacity:.6}}>One place to see what is actually running before you spend more money.</div></div>
      <button onClick={load} style={{padding:'8px 12px',border:'1px solid var(--prepza-border,#E5E7EB)',background:'transparent',borderRadius:9,cursor:'pointer'}}>Refresh</button>
    </div>

    <div style={{display:'grid',gridTemplateColumns:'repeat(5,minmax(0,1fr))',gap:10}}>
      {data.checks.map(c=>{const t=tone(c.status);return <div key={c.key} style={{background:t.bg,color:t.fg,borderRadius:11,padding:12}}>
        <div style={{fontSize:10,fontWeight:800,textTransform:'uppercase'}}>Status</div><div style={{fontSize:13,fontWeight:800,marginTop:4}}>{c.label}</div><div style={{fontSize:10,marginTop:2}}>{c.status}</div>
      </div>})}
    </div>

    <div style={{display:'grid',gridTemplateColumns:'repeat(2,minmax(0,1fr))',gap:14}}>
      <Card title="Student study time">
        <div style={{display:'grid',gridTemplateColumns:'repeat(3,1fr)',gap:8}}>
          <Metric label="Studied today" value={data.students.studied_today.toLocaleString()} sub="Study Hub time > 0"/>
          <Metric label="10m+ today" value={data.students.qualifying_today.toLocaleString()} sub="streak-qualified"/>
          <Metric label="Study time today" value={fmtSeconds(data.students.study_seconds_today)} sub="server-authoritative"/>
          <Metric label="Study time / 7d" value={fmtSeconds(data.students.study_seconds_7d)} sub="all students"/>
          <Metric label="Active today" value={data.students.active_today.toLocaleString()} sub="any authenticated activity"/>
          <Metric label="Active / 7d" value={data.students.active_7d.toLocaleString()} sub="any authenticated activity"/>
        </div>
      </Card>
      <Card title="Active / studying students">
        <div style={{overflowX:'auto'}}>
          <table style={{width:'100%',borderCollapse:'collapse',fontSize:11}}>
            <thead><tr style={{textAlign:'left',opacity:.55}}>
              <th style={{padding:'5px 6px'}}>Student</th><th style={{padding:'5px 6px'}}>Today</th>
              <th style={{padding:'5px 6px'}}>7d</th><th style={{padding:'5px 6px'}}>Last active</th>
            </tr></thead>
            <tbody>{data.students.study_top_students.map(s=><tr key={s.id}>
              <td style={{padding:'7px 6px',borderTop:'1px solid var(--prepza-border,#E5E7EB)'}}>
                <div style={{fontWeight:750}}>{s.display_name || s.email || 'Student #'+s.id}</div>
                {s.display_name && s.email && <div style={{opacity:.55,fontSize:10}}>{s.email}</div>}
              </td>
              <td style={{padding:'7px 6px',borderTop:'1px solid var(--prepza-border,#E5E7EB)',fontWeight:750}}>{fmtSeconds(s.study_seconds_today)}</td>
              <td style={{padding:'7px 6px',borderTop:'1px solid var(--prepza-border,#E5E7EB)'}}>{fmtSeconds(s.study_seconds_7d)}</td>
              <td style={{padding:'7px 6px',borderTop:'1px solid var(--prepza-border,#E5E7EB)',whiteSpace:'nowrap'}}>{s.last_active_at ? new Date(s.last_active_at).toLocaleString() : '—'}</td>
            </tr>)}</tbody>
          </table>
        </div>
        {data.students.study_top_students.length === 0 && <div style={{fontSize:12,opacity:.65}}>No studying or recently active students in the current window.</div>}
      </Card>
    </div>

    <div style={{display:'grid',gridTemplateColumns:'repeat(3,minmax(0,1fr))',gap:14}}>
      <Card title="Students"><div style={{display:'grid',gridTemplateColumns:'repeat(3,1fr)',gap:8}}>
        <Metric label="Total" value={data.students.total.toLocaleString()}/><Metric label="Today" value={data.students.active_today.toLocaleString()}/><Metric label="7 days" value={data.students.active_7d.toLocaleString()}/>
      </div></Card>
      <Card title="AI + Podcast"><div style={{display:'grid',gridTemplateColumns:'repeat(2,1fr)',gap:8}}>
        <Metric label="Queued" value={data.ai.queued}/><Metric label="Processing" value={data.ai.processing}/><Metric label="Podcast waiting" value={data.ai.podcast_queued_or_processing}/><Metric label="7d AI spend" value={'$'+data.ai.spend_7d_usd.toFixed(2)}/>
      </div>{data.ai.failed>0 && <div style={{marginTop:10,color:'#991B1B',fontSize:11}}>AI failures currently recorded: {data.ai.failed}</div>}</Card>
      <Card title="B2B delivery"><div style={{display:'grid',gridTemplateColumns:'repeat(3,1fr)',gap:8}}>
        <Metric label="Active campaigns" value={data.b2b.active_campaigns}/><Metric label="Events / 24h" value={data.b2b.events_24h}/><Metric label="Spend / 24h" value={'KES '+(data.b2b.delivery_spend_24h_minor/100).toFixed(2)}/>
      </div></Card>
    </div>

    <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:14}}>
      <Card title="Render">
        <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:12}}>
          <span style={{background:renderTone.bg,color:renderTone.fg,borderRadius:99,padding:'4px 9px',fontSize:10,fontWeight:800}}>{data.render.configured?data.render.status:'Not connected'}</span>
          {data.render.service?.dashboard_url && <a href={data.render.service.dashboard_url} target="_blank" rel="noreferrer" style={{fontSize:11}}>Open Render service</a>}
        </div>
        {data.render.configured ? <div style={{display:'grid',gridTemplateColumns:'repeat(3,1fr)',gap:8}}>
          <Metric label="CPU (15m)" value={fmtMetric(data.render.cpu_percent,'%')}/><Metric label="Memory (15m)" value={fmtMetric(data.render.memory_percent,'%')}/><Metric label="Instances" value={fmtMetric(data.render.instance_count)}/><Metric label="HTTP requests" value={fmtMetric(data.render.http_requests)}/><Metric label="Bandwidth" value={fmtMetric(data.render.bandwidth_gb,' GB')}/><Metric label="Plan" value={data.render.service?.plan||'—'} sub={data.render.service?.region||''}/>
        </div> : <div style={{fontSize:12,opacity:.7,lineHeight:1.6}}>Add RENDER_API_KEY and RENDER_SERVICE_ID to the server environment. The secret stays server-side; the browser only receives measurements.</div>}
        {data.render.error && <div style={{marginTop:10,color:'#991B1B',fontSize:11}}>{data.render.error}</div>}
      </Card>
      <Card title="Supabase / Postgres">
        <div style={{display:'grid',gridTemplateColumns:'repeat(2,1fr)',gap:8}}>
          <Metric label="Database size" value={fmtBytes(data.database.size_bytes)}/><Metric label="Connections" value={(data.database.active_connections??'—')+' / '+(data.database.connection_limit??'—')}/><Metric label="Database" value={data.database.ok?'Healthy':'Unavailable'}/><Metric label="Billing telemetry" value={data.supabase.management_billing==='connected'?'Connected':'Provider dashboard'}/>
        </div>
        <div style={{marginTop:10,fontSize:11,opacity:.65,lineHeight:1.5}}>{data.supabase.message}</div>
      </Card>
    </div>
    <Card title="Release / spending rule">
      <div style={{fontSize:12,lineHeight:1.6}}>{data.release.message}</div>
      <div style={{display:'flex',gap:10,flexWrap:'wrap',marginTop:10}}>
        <span style={{background:'#F3F4F6',borderRadius:8,padding:'7px 10px',fontSize:11}}>Branch: {data.release.main_branch}</span><span style={{background:'#F3F4F6',borderRadius:8,padding:'7px 10px',fontSize:11}}>No automatic provider upgrades</span><span style={{background:'#F3F4F6',borderRadius:8,padding:'7px 10px',fontSize:11}}>Last refresh: {new Date(data.generated_at).toLocaleString()}</span>
      </div>
    </Card>
  </div>
}
