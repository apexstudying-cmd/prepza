import { useEffect, useMemo, useState } from 'react'

type Props = { orgId: number; isOwner: boolean }

type Campaign = {
  id:number; name:string; objective:string; placement:string; status:string; budget_kes:number
  bid_type:string; bid_kes:number; delivered_impressions:number; delivered_clicks:number
  delivered_applications:number; push_delivered:number
}

type Option = { id:number; name:string }

async function req<T>(path:string, options:RequestInit = {}):Promise<T> {
  const res = await fetch(path, {
    credentials:'include',
    ...options,
    headers:{'Content-Type':'application/json', ...(options.headers || {})},
  })
  const body:any = await res.json().catch(()=>null)
  if (!res.ok) throw new Error(body?.error || 'Request failed')
  return body
}

const gold='#C9A84C', navy='#0B1437'

export default function OrgDiscoveryTab({orgId,isOwner}:Props) {
  const [csrf,setCsrf]=useState('')
  const [campaigns,setCampaigns]=useState<Campaign[]>([])
  const [universities,setUniversities]=useState<Option[]>([])
  const [programs,setPrograms]=useState<Option[]>([])
  const [selectedUniversities,setSelectedUniversities]=useState<number[]>([])
  const [selectedPrograms,setSelectedPrograms]=useState<number[]>([])
  const [years,setYears]=useState<number[]>([])
  const [audience,setAudience]=useState<number|null>(null)
  const [summary,setSummary]=useState<any>(null)
  const [loading,setLoading]=useState(true)
  const [creating,setCreating]=useState(false)
  const [error,setError]=useState('')
  const [form,setForm]=useState({
    name:'', objective:'reach', placement:'feed', bid_type:'cpm', budget_kes:'5000',
    active_days:'30',
  })

  const load=async()=>{
    setLoading(true); setError('')
    try {
      const [me,c,u,p,s]=await Promise.all([
        req<{csrf_token:string}>('/me'),
        req<{campaigns:Campaign[]}>(`/api/organisations/${orgId}/discovery/campaigns`),
        req<Option[]>('/universities'),
        req<any>('/api/organisations/'+orgId+'/discovery/pricing'),
        req<any>('/api/organisations/'+orgId+'/discovery/summary'),
      ])
      setCsrf(me.csrf_token); setCampaigns(c.campaigns); setUniversities(u)
      setSummary(s)
      void p
    } catch(e){setError(e instanceof Error?e.message:'Could not load Discovery.')}
    finally{setLoading(false)}
  }
  useEffect(()=>{void load()},[orgId])

  useEffect(()=>{
    if(selectedUniversities.length!==1){setPrograms([]);return}
    req<any[]>(`/universities/${selectedUniversities[0]}/programs`).then(setPrograms).catch(()=>setPrograms([]))
  },[selectedUniversities])

  const estimated = useMemo(()=>audience ?? 0,[audience])
  const bid = form.placement==='push' ? 1500 : form.bid_type==='cpc' ? 20 : 350

  const estimate=async()=>{
    setError('')
    try{
      const target={university_ids:selectedUniversities,program_ids:selectedPrograms,years,active_days:Number(form.active_days),discoverable:true}
      const r=await req<any>(`/api/organisations/${orgId}/discovery/campaigns`,{
        method:'POST',headers:{'X-CSRF-Token':csrf},
        body:JSON.stringify({name:form.name.trim()||'Audience estimate',objective:form.objective,placement:form.placement,bid_type:form.placement==='push'?'cpm':form.bid_type,budget_kes:Math.max(5000,Number(form.budget_kes)||5000),target})
      })
      setAudience(r.audience_estimate)
      // Keep it as a draft; the same endpoint intentionally creates the campaign.
      await load()
    }catch(e){setError(e instanceof Error?e.message:'Could not estimate audience.')}
  }

  const create=async()=>{
    if(!form.name.trim()||creating)return
    setCreating(true);setError('')
    try{
      const target={university_ids:selectedUniversities,program_ids:selectedPrograms,years,active_days:Number(form.active_days),discoverable:true}
      await req(`/api/organisations/${orgId}/discovery/campaigns`,{
        method:'POST',headers:{'X-CSRF-Token':csrf},
        body:JSON.stringify({name:form.name.trim(),objective:form.objective,placement:form.placement,bid_type:form.placement==='push'?'cpm':form.bid_type,budget_kes:Number(form.budget_kes)||5000,target})
      })
      setForm(f=>({...f,name:''}));setAudience(null);await load()
    }catch(e){setError(e instanceof Error?e.message:'Could not create campaign.')}
    finally{setCreating(false)}
  }

  const setStatus=async(id:number,status:string)=>{
    try{
      await req(`/api/organisations/${orgId}/discovery/campaigns/${id}`,{
        method:'PATCH',headers:{'X-CSRF-Token':csrf},body:JSON.stringify({status})
      });await load()
    }catch(e){setError(e instanceof Error?e.message:'Could not update campaign.')}
  }

  const sendPush=async(id:number)=>{
    try{
      const r=await req<any>(`/api/organisations/${orgId}/discovery/campaigns/${id}/push`,{method:'POST',headers:{'X-CSRF-Token':csrf}})
      alert(`Eligible: ${r.eligible_recipients} · queued: ${r.queued} · sent: ${r.sent}`)
      await load()
    }catch(e){setError(e instanceof Error?e.message:'Could not send push campaign.')}
  }

  if(!isOwner)return <div style={{padding:20,color:'#6B7280',fontSize:13}}>Only the organisation owner can create or activate Discovery campaigns.</div>
  if(loading)return <div style={{padding:30,textAlign:'center',color:'#9CA3AF'}}>Loading Discovery…</div>

  return <div style={{padding:16,display:'flex',flexDirection:'column',gap:14}}>
    {error&&<div style={{background:'#FEE2E2',color:'#991B1B',borderRadius:12,padding:'10px 12px',fontSize:12}}>{error}</div>}
    <div style={{background:`linear-gradient(135deg,${navy},#1A2A5E)`,borderRadius:18,padding:18,color:'#fff'}}>
      <div style={{fontSize:11,opacity:.55,marginBottom:4}}>PREPZA DISCOVERY</div>
      <div style={{fontSize:20,fontWeight:800,marginBottom:5}}>Reach the right students.</div>
      <div style={{fontSize:12,lineHeight:1.6,opacity:.72}}>Target by university, course and year. Prepza selects the audience internally; organisations never receive the student list.</div>
    </div>

    <div style={{background:'#fff',borderRadius:16,padding:16,boxShadow:'0 2px 8px rgba(0,0,0,.04)'}}>
      <div style={{fontWeight:800,fontSize:14,color:navy,marginBottom:12}}>Create campaign</div>
      <input value={form.name} onChange={e=>setForm(f=>({...f,name:e.target.value}))} placeholder="Campaign name" style={input}/>
      <div style={grid}>
        <select value={form.objective} onChange={e=>setForm(f=>({...f,objective:e.target.value}))} style={input}><option value="reach">Reach</option><option value="traffic">Traffic</option><option value="applications">Applications</option></select>
        <select value={form.placement} onChange={e=>setForm(f=>({...f,placement:e.target.value}))} style={input}><option value="feed">Discovery Feed</option><option value="push">Targeted Push</option><option value="feed_push">Feed + Push</option></select>
      </div>
      {form.placement!=='push'&&<select value={form.bid_type} onChange={e=>setForm(f=>({...f,bid_type:e.target.value}))} style={input}><option value="cpm">Pay per 1,000 impressions · KES 350 CPM</option><option value="cpc">Pay per click · KES 20 CPC</option></select>}
      <div style={grid}>
        <input type="number" min="5000" step="500" value={form.budget_kes} onChange={e=>setForm(f=>({...f,budget_kes:e.target.value}))} style={input} placeholder="Budget (KES)"/>
        <select value={form.active_days} onChange={e=>setForm(f=>({...f,active_days:e.target.value}))} style={input}><option value="7">Active students · 7 days</option><option value="30">Active students · 30 days</option><option value="90">Active students · 90 days</option></select>
      </div>
      <div style={{fontSize:11,fontWeight:700,color:'#6B7280',margin:'6px 0'}}>University</div>
      <select multiple value={selectedUniversities.map(String)} onChange={e=>setSelectedUniversities(Array.from(e.target.selectedOptions).map(x=>Number(x.value)))} style={{...input,minHeight:82}}>
        {universities.map(u=><option key={u.id} value={u.id}>{u.name}</option>)}
      </select>
      {programs.length>0&&<><div style={{fontSize:11,fontWeight:700,color:'#6B7280',margin:'8px 0 6px'}}>Course</div><select multiple value={selectedPrograms.map(String)} onChange={e=>setSelectedPrograms(Array.from(e.target.selectedOptions).map(x=>Number(x.value)))} style={{...input,minHeight:82}}>{programs.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></>}
      <div style={{fontSize:11,fontWeight:700,color:'#6B7280',margin:'8px 0 6px'}}>Year</div>
      <div style={{display:'flex',gap:6,flexWrap:'wrap'}}>{[1,2,3,4].map(y=><button key={y} type="button" onClick={()=>setYears(v=>v.includes(y)?v.filter(x=>x!==y):[...v,y])} style={{border:`1px solid ${years.includes(y)?gold:'#E5E7EB'}`,background:years.includes(y)?gold+'18':'#fff',color:years.includes(y)?navy:'#6B7280',borderRadius:9,padding:'7px 11px',fontWeight:700,cursor:'pointer'}}>Year {y}</button>)}</div>
      <div style={{display:'flex',gap:8,marginTop:12}}>
        <button onClick={estimate} disabled={!form.name.trim()} style={buttonSecondary}>Estimate audience</button>
        <button onClick={create} disabled={creating||!form.name.trim()} style={buttonPrimary}>{creating?'Creating…':'Create draft'}</button>
      </div>
      {audience!==null&&<div style={{marginTop:12,background:'#F8F5EC',borderRadius:12,padding:12,fontSize:12,color:'#6B4F00'}}><strong>{estimated.toLocaleString()}</strong> eligible students matched. Targeting is internal and aggregate.</div>}
      <div style={{fontSize:10,color:'#9CA3AF',marginTop:10}}>Minimum campaign budget: KES 5,000. Usage is metered against verified delivery and capped by your campaign budget.</div>
    </div>

    <div style={{display:'grid',gridTemplateColumns:'repeat(3,1fr)',gap:8}}>
      <Metric label="Impressions" value={summary?.campaigns?.reduce((s:number,c:Campaign)=>s+c.delivered_impressions,0)||0}/>
      <Metric label="Clicks" value={summary?.campaigns?.reduce((s:number,c:Campaign)=>s+c.delivered_clicks,0)||0}/>
      <Metric label="Push delivered" value={summary?.campaigns?.reduce((s:number,c:Campaign)=>s+c.push_delivered,0)||0}/>
    </div>

    <div style={{fontWeight:800,fontSize:14,color:navy}}>Campaigns</div>
    {campaigns.map(c=><div key={c.id} style={{background:'#fff',borderRadius:14,padding:14,boxShadow:'0 2px 7px rgba(0,0,0,.04)'}}>
      <div style={{display:'flex',alignItems:'center',gap:10}}>
        <div style={{flex:1}}><div style={{fontWeight:800,fontSize:13,color:navy}}>{c.name}</div><div style={{fontSize:10,color:'#9CA3AF',marginTop:3}}>{c.placement} · {c.bid_type.toUpperCase()} · KES {c.bid_kes.toLocaleString()}</div></div>
        <span style={{fontSize:10,fontWeight:800,color:c.status==='active'?'#16A34A':gold}}>{c.status}</span>
      </div>
      <div style={{display:'grid',gridTemplateColumns:'repeat(4,1fr)',gap:6,marginTop:10}}>
        <Metric label="Impr." value={c.delivered_impressions}/><Metric label="Clicks" value={c.delivered_clicks}/><Metric label="Apps" value={c.delivered_applications}/><Metric label="Push" value={c.push_delivered}/>
      </div>
      <div style={{fontSize:11,color:'#6B7280',marginTop:8}}>Budget KES {c.budget_kes.toLocaleString()} · estimated billed usage updates from verified events.</div>
      <div style={{display:'flex',gap:6,marginTop:10}}>
        {c.status==='draft'&&<button onClick={()=>setStatus(c.id,'active')} style={buttonPrimary}>Activate</button>}
        {c.status==='active'&&c.placement!=='feed'&&<button onClick={()=>sendPush(c.id)} style={buttonSecondary}>Send targeted push</button>}
        {c.status==='active'&&<button onClick={()=>setStatus(c.id,'paused')} style={buttonSecondary}>Pause</button>}
        {c.status==='paused'&&<button onClick={()=>setStatus(c.id,'active')} style={buttonPrimary}>Resume</button>}
      </div>
    </div>)}
    {campaigns.length===0&&<div style={{textAlign:'center',padding:28,color:'#9CA3AF',fontSize:12}}>No campaigns yet.</div>}
  </div>
}

const input:React.CSSProperties={width:'100%',boxSizing:'border-box',border:'1px solid #E5E7EB',borderRadius:11,padding:'10px 12px',fontSize:12,marginBottom:9,background:'#fff',color:navy,fontFamily:'Plus Jakarta Sans'}
const grid:React.CSSProperties={display:'grid',gridTemplateColumns:'1fr 1fr',gap:8}
const buttonPrimary:React.CSSProperties={background:`linear-gradient(135deg,${gold},#E8C97E)`,color:navy,border:'none',borderRadius:11,padding:'10px 13px',fontWeight:800,cursor:'pointer'}
const buttonSecondary:React.CSSProperties={background:'#F3F4F6',color:navy,border:'none',borderRadius:11,padding:'10px 13px',fontWeight:700,cursor:'pointer'}
function Metric({label,value}:{label:string;value:number}){return <div style={{background:'#fff',borderRadius:12,padding:10,textAlign:'center',boxShadow:'0 2px 5px rgba(0,0,0,.04)'}}><div style={{fontWeight:800,fontSize:16,color:navy}}>{Number(value||0).toLocaleString()}</div><div style={{fontSize:9,color:'#9CA3AF'}}>{label}</div></div>}
