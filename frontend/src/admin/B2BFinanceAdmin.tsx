import { useEffect, useState } from 'react'

type Props = { tokens: any }
type Placement = { id:number; placement_key:string; label:string; is_active:boolean; allowed_billing_modes:string[]; cpm_amount_minor:number|null; cpc_amount_minor:number|null; inventory_limit:number|null }
type Overview = { campaigns:number; active_campaigns:number; exhausted_campaigns:number; campaign_funding_kes:number; ledger_net_balance_kes:number; paid_campaign_value_kes:number; customer_processing_fees_kes:number; refunded_campaign_value_kes:number; processing_fees_are_customer_costs:boolean }
type Campaign = { id:number; organisation_id:number; name:string; placement:string; status:string; budget_kes:number; bid_type:string; bid_kes:number; funding_status:string; funded_amount_minor:number; delivered_impressions:number; delivered_clicks:number; push_delivered:number; created_at:string|null }
type Payment = { id:number; organisation_id:number; campaign_id:number|null; provider_reference:string; customer_amount_minor:number; campaign_amount_minor:number; processing_fee_minor:number; status:string; funding_status:string|null; created_at:string }
type Recon = { payment_id:number; provider_reference:string; campaign_id:number; status:string; campaign_amount_minor:number; funding_amount_minor:number; ledger_funding_minor:number; reconciliation_status:string }

async function req<T>(path:string, options:RequestInit={}):Promise<T>{
  const r=await fetch(path,{credentials:'include',...options,headers:{'Content-Type':'application/json',...(options.headers||{})}})
  const b:any=await r.json().catch(()=>null)
  if(!r.ok) throw new Error(b?.error||'Request failed')
  return b
}
const kes=(minor:number|null|undefined)=>`KES ${((Number(minor||0))/100).toLocaleString('en-KE',{maximumFractionDigits:2})}`

export default function B2BFinanceAdmin({tokens:T}:Props){
  const [csrf,setCsrf]=useState('')
  const [overview,setOverview]=useState<Overview|null>(null)
  const [placements,setPlacements]=useState<Placement[]>([])
  const [campaigns,setCampaigns]=useState<Campaign[]>([])
  const [payments,setPayments]=useState<Payment[]>([])
  const [recon,setRecon]=useState<Recon[]>([])
  const [loading,setLoading]=useState(true)
  const [error,setError]=useState('')
  const [saving,setSaving]=useState<number|null>(null)
  const [tab,setTab]=useState<'overview'|'placements'|'campaigns'|'payments'|'reconciliation'>('overview')

  const load=async()=>{
    setLoading(true);setError('')
    try{
      const [me,o,p,c,pm,r]=await Promise.all([
        req<{csrf_token:string}>('/me'),req<Overview>('/api/admin/b2b/overview'),
        req<{placements:Placement[]}>('/api/admin/b2b/placements'),
        req<{campaigns:Campaign[]}>('/api/admin/b2b/campaigns'),
        req<{payments:Payment[]}>('/api/admin/b2b/payments'),
        req<{reconciliation:Recon[]}>('/api/admin/b2b/reconciliation')
      ])
      setCsrf(me.csrf_token);setOverview(o);setPlacements(p.placements);setCampaigns(c.campaigns);setPayments(pm.payments);setRecon(r.reconciliation)
    }catch(e){setError(e instanceof Error?e.message:'Could not load B2B finance.')}
    finally{setLoading(false)}
  }
  useEffect(()=>{void load()},[])

  const savePlacement=async(p:Placement)=>{
    setSaving(p.id);setError('')
    try{
      await req('/api/admin/b2b/placements/'+p.id,{method:'PATCH',headers:{'X-CSRF-Token':csrf},body:JSON.stringify({
        label:p.label,is_active:p.is_active,allowed_billing_modes:p.allowed_billing_modes,
        cpm_amount_minor:p.cpm_amount_minor,cpc_amount_minor:p.cpc_amount_minor,inventory_limit:p.inventory_limit
      })})
      await load()
    }catch(e){setError(e instanceof Error?e.message:'Could not save placement.')}
    finally{setSaving(null)}
  }

  if(loading)return <div style={{padding:30,color:T.textMuted}}>Loading B2B finance…</div>
  const card={background:T.card,borderRadius:14,padding:16,border:'1px solid '+T.border}
  const tabs=['overview','placements','campaigns','payments','reconciliation'] as const

  return <div style={{display:'flex',flexDirection:'column',gap:14}}>
    {error&&<div style={{background:'#FEE2E2',color:'#991B1B',borderRadius:10,padding:10,fontSize:12}}>{error}</div>}
    <div style={{display:'flex',gap:6,flexWrap:'wrap'}}>
      {tabs.map(x=><button key={x} onClick={()=>setTab(x)} style={{padding:'8px 13px',border:0,borderRadius:9,background:tab===x?'#0B1437':'#F3F4F6',color:tab===x?'#fff':T.text,fontWeight:700,fontSize:12,cursor:'pointer'}}>{x[0].toUpperCase()+x.slice(1)}</button>)}
    </div>

    {tab==='overview'&&overview&&<>
      <div style={{display:'grid',gridTemplateColumns:'repeat(4,1fr)',gap:10}}>
        {[
          ['Campaigns',overview.campaigns.toLocaleString(),''],
          ['Active',overview.active_campaigns.toLocaleString(),''],
          ['Prepaid funded',`KES ${overview.campaign_funding_kes.toLocaleString()}`,''],
          ['Spent / ledger net',`KES ${overview.ledger_net_balance_kes.toLocaleString()}`,'']
        ].map(x=><div key={x[0]} style={card}><div style={{fontSize:11,color:T.textMuted}}>{x[0]}</div><div style={{fontSize:22,fontWeight:800,color:T.text,marginTop:5}}>{x[1]}</div></div>)}
      </div>
      <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:12}}>
        <div style={card}><b>Revenue & customer charges</b><div style={{marginTop:12,fontSize:13,lineHeight:1.9}}>
          <div>Paid campaign value: <strong>KES {overview.paid_campaign_value_kes.toLocaleString()}</strong></div>
          <div>Refunded campaign value: <strong>KES {overview.refunded_campaign_value_kes.toLocaleString()}</strong></div>
          <div>Payment-processing fees charged to customers: <strong>KES {overview.customer_processing_fees_kes.toLocaleString()}</strong></div>
        </div></div>
        <div style={card}><b>Accounting boundary</b><div style={{fontSize:12,color:T.textMuted,lineHeight:1.6,marginTop:10}}>
          Campaign funding is prepaid customer money. Delivery spend is tracked in the campaign ledger. Payment-processing fees are recorded separately as customer costs, not Prepza delivery costs. Revenue recognition and tax treatment should be finalized with the accountant.
        </div></div>
      </div>
      <div style={card}><b>Operational controls</b><div style={{fontSize:12,color:T.textMuted,lineHeight:1.6,marginTop:8}}>Exhausted campaigns: {overview.exhausted_campaigns}. Reconciliation flags payment/funding/ledger mismatches for review. No student-level audience list is exposed here.</div></div>
    </>}

    {tab==='placements'&&<div style={{display:'flex',flexDirection:'column',gap:10}}>
      <div style={{...card,fontSize:12,color:T.textMuted}}>Placement inventory and commercial rates are admin-controlled. Campaigns should use the frozen pricing snapshot created at purchase; changing these settings affects future campaigns, not already-funded campaigns.</div>
      {placements.map(p=><div key={p.id} style={card}>
        <div style={{display:'flex',gap:12,alignItems:'center',flexWrap:'wrap'}}>
          <div style={{flex:1,minWidth:220}}><input value={p.label} onChange={e=>setPlacements(v=>v.map(x=>x.id===p.id?{...x,label:e.target.value}:x))} style={{width:'100%',boxSizing:'border-box',padding:9,border:'1px solid '+T.border,borderRadius:8,background:T.card,color:T.text}}/><div style={{fontSize:10,color:T.textMuted,marginTop:4}}>{p.placement_key}</div></div>
          <label style={{fontSize:11}}><input type="checkbox" checked={p.is_active} onChange={e=>setPlacements(v=>v.map(x=>x.id===p.id?{...x,is_active:e.target.checked}:x))}/> Active</label>
          <label style={{fontSize:11}}>CPM <input type="number" value={p.cpm_amount_minor??0} onChange={e=>setPlacements(v=>v.map(x=>x.id===p.id?{...x,cpm_amount_minor:Number(e.target.value)}:x))} style={{width:90,padding:7}}/></label>
          <label style={{fontSize:11}}>CPC <input type="number" value={p.cpc_amount_minor??0} onChange={e=>setPlacements(v=>v.map(x=>x.id===p.id?{...x,cpc_amount_minor:Number(e.target.value)}:x))} style={{width:90,padding:7}}/></label>
          <button disabled={saving===p.id} onClick={()=>savePlacement(p)} style={{background:'#C9A84C',color:'#0B1437',border:0,borderRadius:8,padding:'8px 12px',fontWeight:800}}>{saving===p.id?'Saving…':'Save'}</button>
        </div>
        <div style={{fontSize:10,color:T.textMuted,marginTop:8}}>Rates are stored in minor units. Current launch values correspond to KES 350 CPM and KES 20 CPC.</div>
      </div>)}
    </div>}

    {tab==='campaigns'&&<div style={card}><div style={{fontWeight:800,marginBottom:10}}>Campaign ledger overview</div><div style={{overflowX:'auto'}}><table style={{width:'100%',fontSize:11,borderCollapse:'collapse'}}><thead><tr>{['ID','Org','Campaign','Placement','Status','Funding','Budget','Funded','Impressions','Clicks'].map(x=><th key={x} style={{textAlign:'left',padding:7,borderBottom:'1px solid '+T.border}}>{x}</th>)}</tr></thead><tbody>{campaigns.map(c=><tr key={c.id}>{[c.id,c.organisation_id,c.name,c.placement,c.status,c.funding_status,`KES ${Number(c.budget_kes).toLocaleString()}`,kes(c.funded_amount_minor),c.delivered_impressions,c.delivered_clicks].map((x,i)=><td key={i} style={{padding:7,borderBottom:'1px solid '+T.border,color:T.text}}>{x}</td>)}</tr>)}</tbody></table></div></div>}

    {tab==='payments'&&<div style={card}><div style={{fontWeight:800,marginBottom:10}}>B2B payments</div><div style={{overflowX:'auto'}}><table style={{width:'100%',fontSize:11,borderCollapse:'collapse'}}><thead><tr>{['Reference','Campaign','Customer paid','Campaign value','Processing fee','Status','Funding'].map(x=><th key={x} style={{textAlign:'left',padding:7,borderBottom:'1px solid '+T.border}}>{x}</th>)}</tr></thead><tbody>{payments.map(p=><tr key={p.id}>{[p.provider_reference,p.campaign_id??'—',kes(p.customer_amount_minor),kes(p.campaign_amount_minor),kes(p.processing_fee_minor),p.status,p.funding_status??'—'].map((x,i)=><td key={i} style={{padding:7,borderBottom:'1px solid '+T.border,color:T.text}}>{x}</td>)}</tr>)}</tbody></table></div></div>}

    {tab==='reconciliation'&&<div style={card}><div style={{fontWeight:800,marginBottom:10}}>Payment → funding → ledger reconciliation</div><div style={{overflowX:'auto'}}><table style={{width:'100%',fontSize:11,borderCollapse:'collapse'}}><thead><tr>{['Reference','Payment','Campaign value','Funding','Ledger','Result'].map(x=><th key={x} style={{textAlign:'left',padding:7,borderBottom:'1px solid '+T.border}}>{x}</th>)}</tr></thead><tbody>{recon.map(r=><tr key={r.payment_id}><td style={{padding:7}}>{r.provider_reference}</td><td style={{padding:7}}>{r.status}</td><td style={{padding:7}}>{kes(r.campaign_amount_minor)}</td><td style={{padding:7}}>{kes(r.funding_amount_minor)}</td><td style={{padding:7}}>{kes(r.ledger_funding_minor)}</td><td style={{padding:7,fontWeight:800,color:r.reconciliation_status==='matched'?'#16A34A':'#DC2626'}}>{r.reconciliation_status}</td></tr>)}</tbody></table></div></div>}
  </div>
}
