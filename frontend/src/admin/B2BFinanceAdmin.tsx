import { useEffect, useState } from 'react'

type Props = { tokens: any }
type Placement = { id:number; placement_key:string; label:string; is_active:boolean; allowed_billing_modes:string[]; cpm_amount_minor:number|null; cpc_amount_minor:number|null; inventory_limit:number|null }
type Overview = { campaigns:number; active_campaigns:number; exhausted_campaigns:number; campaign_funding_kes:number; ledger_net_balance_kes:number; paid_campaign_value_kes:number; customer_processing_fees_kes:number; refunded_campaign_value_kes:number; processing_fees_are_customer_costs:boolean }
type Campaign = { id:number; organisation_id:number; name:string; placement:string; status:string; budget_kes:number; bid_type:string; bid_kes:number; funding_status:string; funded_amount_minor:number; delivered_impressions:number; delivered_clicks:number; push_delivered:number; created_at:string|null }
type Payment = { id:number; organisation_id:number; campaign_id:number|null; provider_reference:string; customer_amount_minor:number; campaign_amount_minor:number; processing_fee_minor:number; status:string; funding_status:string|null; created_at:string }
type Recon = { payment_id:number; provider_reference:string; campaign_id:number; status:string; campaign_amount_minor:number; funding_amount_minor:number; ledger_funding_minor:number; reconciliation_status:string }
type KycDoc = { id:number; organisation_id:number; document_type:string; file_name:string|null; status:string; admin_notes:string|null; created_at:string }
type Invoice = { id:number; organisation_id:number; campaign_id:number|null; invoice_number:string; subtotal_minor:number; processing_fee_minor:number; total_minor:number; status:string; payment_method:string; due_at:string|null; paid_at:string|null; created_at:string }
type Pricing = { config_key:string; value_json:Record<string,number>; currency:string; version:string; updated_by_user_id:number|null; updated_at:string|null }

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
  const [kyc,setKyc]=useState<KycDoc[]>([])
  const [invoices,setInvoices]=useState<Invoice[]>([])
  const [pricing,setPricing]=useState<Pricing[]>([])
  const [settling,setSettling]=useState<number|null>(null)
  const [savingPricing,setSavingPricing]=useState<string|null>(null)
  const [loading,setLoading]=useState(true)
  const [error,setError]=useState('')
  const [saving,setSaving]=useState<number|null>(null)
  const [tab,setTab]=useState<'overview'|'placements'|'campaigns'|'payments'|'reconciliation'|'verification'|'invoices'>('overview')

  const load=async()=>{
    setLoading(true);setError('')
    try{
      const [me,o,p,c,pm,r,k,i,pr]=await Promise.all([
        req<{csrf_token:string}>('/me'),req<Overview>('/api/admin/b2b/overview'),
        req<{placements:Placement[]}>('/api/admin/b2b/placements'),
        req<{campaigns:Campaign[]}>('/api/admin/b2b/campaigns'),
        req<{payments:Payment[]}>('/api/admin/b2b/payments'),
        req<{reconciliation:Recon[]}>('/api/admin/b2b/reconciliation'),
        req<{documents:KycDoc[]}>('/api/admin/b2b/kyc'),
        req<{invoices:Invoice[]}>('/api/admin/b2b/invoices'),
        req<{pricing:Pricing[]}>('/api/admin/b2b/pricing')
      ])
      setCsrf(me.csrf_token);setOverview(o);setPlacements(p.placements);setCampaigns(c.campaigns);setPayments(pm.payments);setRecon(r.reconciliation);setKyc(k.documents);setInvoices(i.invoices);setPricing(pr.pricing)
    }catch(e){setError(e instanceof Error?e.message:'Could not load B2B finance.')}
    finally{setLoading(false)}
  }
  useEffect(()=>{void load()},[])

  const savePricing=async(item:Pricing, amount:number)=>{
    setSavingPricing(item.config_key);setError('')
    try{
      const value={...item.value_json,amount_kes:amount}
      await req('/api/admin/b2b/pricing/'+encodeURIComponent(item.config_key),{method:'PATCH',headers:{'X-CSRF-Token':csrf},body:JSON.stringify({value})})
      await load()
    }catch(e){setError(e instanceof Error?e.message:'Could not save pricing.')}
    finally{setSavingPricing(null)}
  }

  const savePlacement=async(p:Placement)=>{
    setSaving(p.id);setError('')
    try{
      await req('/api/admin/b2b/placements/'+p.id,{method:'PATCH',headers:{'X-CSRF-Token':csrf},body:JSON.stringify({
        label:p.label,is_active:p.is_active,allowed_billing_modes:p.allowed_billing_modes,
        inventory_limit:p.inventory_limit
      })})
      await load()
    }catch(e){setError(e instanceof Error?e.message:'Could not save placement.')}
    finally{setSaving(null)}
  }

  if(loading)return <div style={{padding:30,color:T.textMuted}}>Loading B2B finance…</div>
  const card={background:T.card,borderRadius:14,padding:16,border:'1px solid '+T.border}
  const tabs=['overview','pricing','placements','campaigns','payments','reconciliation','verification','invoices'] as const

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

    {tab==='pricing'&&<div style={{display:'flex',flexDirection:'column',gap:10}}>
      <div style={card}><b>Canonical B2B pricing</b><div style={{fontSize:11,color:T.textMuted,marginTop:6}}>These values are the single live commercial source for new sponsored campaigns and delivery metering. Changes do not rewrite existing campaign pricing snapshots.</div></div>
      {pricing.map(item=><div key={item.config_key} style={card}>
        <div style={{display:'flex',gap:12,alignItems:'center',flexWrap:'wrap'}}>
          <div style={{flex:1,minWidth:220}}><b>{item.config_key}</b><div style={{fontSize:10,color:T.textMuted}}>Version {item.version} · {item.updated_at||'—'}</div></div>
          {'amount_kes' in item.value_json&&<label style={{fontSize:11}}>KES <input type="number" value={Number(item.value_json.amount_kes||0)} onChange={e=>setPricing(v=>v.map(x=>x.config_key===item.config_key?{...x,value_json:{...x.value_json,amount_kes:Number(e.target.value)}}:x))} style={{width:110,padding:7}}/></label>}
          <button disabled={savingPricing===item.config_key||!('amount_kes' in item.value_json)} onClick={()=>savePricing(item,Number(item.value_json.amount_kes||0))} style={{background:'#C9A84C',color:'#0B1437',border:0,borderRadius:8,padding:'8px 12px',fontWeight:800}}>{savingPricing===item.config_key?'Saving…':'Save'}</button>
        </div>
      </div>)}
    </div>

    {tab==='placements'&&<div style={{display:'flex',flexDirection:'column',gap:10}}>
      <div style={{...card,fontSize:12,color:T.textMuted}}>Placement inventory and commercial rates are admin-controlled. Campaigns should use the frozen pricing snapshot created at purchase; changing these settings affects future campaigns, not already-funded campaigns.</div>
      {placements.map(p=><div key={p.id} style={card}>
        <div style={{display:'flex',gap:12,alignItems:'center',flexWrap:'wrap'}}>
          <div style={{flex:1,minWidth:220}}><input value={p.label} onChange={e=>setPlacements(v=>v.map(x=>x.id===p.id?{...x,label:e.target.value}:x))} style={{width:'100%',boxSizing:'border-box',padding:9,border:'1px solid '+T.border,borderRadius:8,background:T.card,color:T.text}}/><div style={{fontSize:10,color:T.textMuted,marginTop:4}}>{p.placement_key}</div></div>
          <label style={{fontSize:11}}><input type="checkbox" checked={p.is_active} onChange={e=>setPlacements(v=>v.map(x=>x.id===p.id?{...x,is_active:e.target.checked}:x))}/> Active</label>
          <div style={{fontSize:11,color:T.textMuted}}>Pricing: use the Canonical Pricing tab</div>
          <button disabled={saving===p.id} onClick={()=>savePlacement(p)} style={{background:'#C9A84C',color:'#0B1437',border:0,borderRadius:8,padding:'8px 12px',fontWeight:800}}>{saving===p.id?'Saving…':'Save'}</button>
        </div>
        <div style={{fontSize:10,color:T.textMuted,marginTop:8}}>Placement settings control inventory and availability. Commercial rates are maintained only in the Canonical Pricing tab.</div>
      </div>)}
    </div>}

    {tab==='campaigns'&&<div style={card}><div style={{fontWeight:800,marginBottom:10}}>Campaign ledger overview</div><div style={{overflowX:'auto'}}><table style={{width:'100%',fontSize:11,borderCollapse:'collapse'}}><thead><tr>{['ID','Org','Campaign','Placement','Status','Funding','Budget','Funded','Impressions','Clicks'].map(x=><th key={x} style={{textAlign:'left',padding:7,borderBottom:'1px solid '+T.border}}>{x}</th>)}</tr></thead><tbody>{campaigns.map(c=><tr key={c.id}>{[c.id,c.organisation_id,c.name,c.placement,c.status,c.funding_status,`KES ${Number(c.budget_kes).toLocaleString()}`,kes(c.funded_amount_minor),c.delivered_impressions,c.delivered_clicks].map((x,i)=><td key={i} style={{padding:7,borderBottom:'1px solid '+T.border,color:T.text}}>{x}</td>)}</tr>)}</tbody></table></div></div>}

    {tab==='payments'&&<div style={card}><div style={{fontWeight:800,marginBottom:10}}>B2B payments</div><div style={{overflowX:'auto'}}><table style={{width:'100%',fontSize:11,borderCollapse:'collapse'}}><thead><tr>{['Reference','Campaign','Customer paid','Campaign value','Processing fee','Status','Funding'].map(x=><th key={x} style={{textAlign:'left',padding:7,borderBottom:'1px solid '+T.border}}>{x}</th>)}</tr></thead><tbody>{payments.map(p=><tr key={p.id}>{[p.provider_reference,p.campaign_id??'—',kes(p.customer_amount_minor),kes(p.campaign_amount_minor),kes(p.processing_fee_minor),p.status,p.funding_status??'—'].map((x,i)=><td key={i} style={{padding:7,borderBottom:'1px solid '+T.border,color:T.text}}>{x}</td>)}</tr>)}</tbody></table></div></div>}

    {tab==='verification'&&<div style={{display:'flex',flexDirection:'column',gap:10}}>
      <div style={card}><b>Organisation verification</b><div style={{fontSize:11,color:T.textMuted,marginTop:6}}>Review submitted documents here. Approving a document marks the organisation verified and unlocks paid sponsorship creation.</div></div>
      {kyc.map(d=><div key={d.id} style={card}><div style={{display:'flex',gap:10,alignItems:'center',flexWrap:'wrap'}}>
        <div style={{flex:1,minWidth:220}}><b>{d.file_name||'KYC document'}</b><div style={{fontSize:10,color:T.textMuted}}>Organisation #{d.organisation_id} · {d.document_type}</div></div>
        <a href={'/api/admin/b2b/kyc/'+d.id+'/download'} target="_blank" rel="noreferrer" style={{fontSize:11,fontWeight:800,color:'#5570B7'}}>Open document</a>
        <select value={d.status} onChange={e=>setKyc(v=>v.map(x=>x.id===d.id?{...x,status:e.target.value}:x))} style={{padding:7,border:'1px solid '+T.border,borderRadius:8,background:T.card,color:T.text}}>
          <option value="pending">Pending</option><option value="approved">Approved</option><option value="rejected">Rejected</option>
        </select>
        <button onClick={async()=>{try{await req('/api/admin/b2b/kyc/'+d.id,{method:'PATCH',headers:{'X-CSRF-Token':csrf},body:JSON.stringify({status:d.status,admin_notes:d.admin_notes||''})});await load()}catch(e){setError(e instanceof Error?e.message:'Could not update verification.')}}} style={{background:'#C9A84C',color:'#0B1437',border:0,borderRadius:8,padding:'8px 12px',fontWeight:800}}>Save</button>
      </div></div>)}
      {!kyc.length&&<div style={card}>No verification documents are awaiting review.</div>}
    </div>}
    {tab==='invoices'&&<div style={{display:'flex',flexDirection:'column',gap:10}}>
      <div style={card}><b>Pro-forma invoices & bank settlement</b><div style={{fontSize:11,color:T.textMuted,marginTop:6}}>Only settle after the bank funds have actually landed. Enter the bank reference and exact amount received; the system then creates the payment, funding and ledger records atomically.</div></div>
      {invoices.map(i=><div key={i.id} style={card}><div style={{display:'flex',gap:10,alignItems:'center',flexWrap:'wrap'}}>
        <div style={{flex:1,minWidth:220}}><b>{i.invoice_number}</b><div style={{fontSize:10,color:T.textMuted}}>Organisation #{i.organisation_id} · Campaign #{i.campaign_id??'—'} · {i.status}</div></div>
        <strong>{kes(i.total_minor)}</strong>
        {i.status!=='paid'&&<button disabled={settling===i.id} onClick={async()=>{const ref=window.prompt('Bank payment reference');if(!ref)return;const amount=window.prompt('Exact amount received in KES',String(Number(i.total_minor)/100));if(!amount)return;setSettling(i.id);try{await req('/api/admin/b2b/invoices/'+i.id+'/mark-paid',{method:'POST',headers:{'X-CSRF-Token':csrf},body:JSON.stringify({payment_reference:ref,received_amount_minor:Math.round(Number(amount)*100)})});await load()}catch(e){setError(e instanceof Error?e.message:'Could not settle invoice.')}finally{setSettling(null)}}} style={{background:'#C9A84C',color:'#0B1437',border:0,borderRadius:8,padding:'8px 12px',fontWeight:800}}>{settling===i.id?'Saving…':'Mark bank payment received'}</button>}
        <a href={'/api/organisations/'+i.organisation_id+'/billing/invoices/'+i.id+'/receipt.pdf'} target="_blank" rel="noreferrer" style={{fontSize:11,fontWeight:800,color:'#5570B7'}}>PDF</a>
      </div></div>)}
      {!invoices.length&&<div style={card}>No organisation invoices yet.</div>}
    </div>}

{tab==='reconciliation'&&<div style={card}><div style={{fontWeight:800,marginBottom:10}}>Payment → funding → ledger reconciliation</div><div style={{overflowX:'auto'}}><table style={{width:'100%',fontSize:11,borderCollapse:'collapse'}}><thead><tr>{['Reference','Payment','Campaign value','Funding','Ledger','Result'].map(x=><th key={x} style={{textAlign:'left',padding:7,borderBottom:'1px solid '+T.border}}>{x}</th>)}</tr></thead><tbody>{recon.map(r=><tr key={r.payment_id}><td style={{padding:7}}>{r.provider_reference}</td><td style={{padding:7}}>{r.status}</td><td style={{padding:7}}>{kes(r.campaign_amount_minor)}</td><td style={{padding:7}}>{kes(r.funding_amount_minor)}</td><td style={{padding:7}}>{kes(r.ledger_funding_minor)}</td><td style={{padding:7,fontWeight:800,color:r.reconciliation_status==='matched'?'#16A34A':'#DC2626'}}>{r.reconciliation_status}</td></tr>)}</tbody></table></div></div>}
  </div>
}
