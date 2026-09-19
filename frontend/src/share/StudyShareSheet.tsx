import React, { useEffect, useMemo, useState } from 'react'

type ShareSheetProps = { onClose: () => void }

type Stats = { currentStreak:number; longestStreak:number; totalSeconds:number; period:'week'|'month'|'day' }

const N = { navy:'#0B1437', navy2:'#132046', navy3:'#1A2A5E', gold:'#C9A84C', goldL:'#E8C97E', bg:'#F8F9FC' }

async function api<T>(path:string, options:RequestInit={}) {
  const r=await fetch(path,{credentials:'include',...options,headers:{'Content-Type':'application/json',...(options.headers||{})}})
  const b=await r.json().catch(()=>null)
  if(!r.ok) throw new Error(b?.error||'Request failed')
  return b as T
}

function formatTime(seconds:number){
  const mins=Math.round(seconds/60)
  if(mins<60)return `${mins} min`
  const h=Math.floor(mins/60), m=mins%60
  return m ? `${h}h ${m}m` : `${h}h`
}

function svgCard(stats:Stats,name:string,ref:string){
  const streak=stats.currentStreak
  const time=formatTime(stats.totalSeconds)
  const safe=(v:string)=>v.replace(/[<>&"]/g,'')
  const width=1080,height=1920
  const headline=streak>0?`${streak} day study streak`:'Building my study streak'
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#0B1437"/><stop offset="1" stop-color="#1A2A5E"/></linearGradient>
    <linearGradient id="gold" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#C9A84C"/><stop offset="1" stop-color="#E8C97E"/></linearGradient>
  </defs>
  <rect width="1080" height="1920" fill="url(#bg)"/>
  <circle cx="930" cy="150" r="270" fill="#C9A84C" opacity=".08"/><circle cx="120" cy="1760" r="340" fill="#E8C97E" opacity=".06"/>
  <text x="88" y="130" font-family="Arial,sans-serif" font-size="42" font-weight="800" fill="#E8C97E">PREPZA</text>
  <text x="88" y="220" font-family="Arial,sans-serif" font-size="25" fill="#FFFFFF" opacity=".65">MY STUDY STATS</text>
  <text x="88" y="500" font-family="Arial,sans-serif" font-size="94" font-weight="800" fill="#FFFFFF">${safe(headline)}</text>
  <text x="88" y="580" font-family="Arial,sans-serif" font-size="38" fill="#FFFFFF" opacity=".65">${safe(name)} is studying with Prepza.</text>
  <rect x="88" y="700" width="904" height="290" rx="38" fill="#FFFFFF" opacity=".08"/>
  <text x="140" y="805" font-family="Arial,sans-serif" font-size="34" fill="#FFFFFF" opacity=".58">CURRENT STREAK</text>
  <text x="140" y="930" font-family="Arial,sans-serif" font-size="104" font-weight="800" fill="url(#gold)">${streak}</text>
  <text x="310" y="925" font-family="Arial,sans-serif" font-size="40" fill="#FFFFFF">days</text>
  <rect x="88" y="1040" width="904" height="290" rx="38" fill="#FFFFFF" opacity=".08"/>
  <text x="140" y="1145" font-family="Arial,sans-serif" font-size="34" fill="#FFFFFF" opacity=".58">STUDIED THIS ${stats.period.toUpperCase()}</text>
  <text x="140" y="1270" font-family="Arial,sans-serif" font-size="88" font-weight="800" fill="#FFFFFF">${safe(time)}</text>
  <text x="88" y="1515" font-family="Arial,sans-serif" font-size="34" fill="#FFFFFF" opacity=".65">Keep learning. Keep moving.</text>
  <rect x="88" y="1600" width="300" height="8" rx="4" fill="url(#gold)"/>
  <text x="88" y="1705" font-family="Arial,sans-serif" font-size="30" fill="#FFFFFF">prepza.app</text>
  <text x="88" y="1760" font-family="Arial,sans-serif" font-size="24" fill="#FFFFFF" opacity=".5">Study smarter. Together.</text>
  </svg>`
}

async function svgToPng(svg:string){
  const blob=new Blob([svg],{type:'image/svg+xml;charset=utf-8'})
  const url=URL.createObjectURL(blob)
  try{
    const img=new Image()
    img.src=url
    await new Promise<void>((resolve,reject)=>{img.onload=()=>resolve();img.onerror=()=>reject(new Error('Image render failed'))})
    const canvas=document.createElement('canvas'); canvas.width=1080; canvas.height=1920
    const ctx=canvas.getContext('2d'); if(!ctx) throw new Error('Canvas unavailable')
    ctx.drawImage(img,0,0)
    return await new Promise<Blob>((resolve,reject)=>canvas.toBlob(b=>b?resolve(b):reject(new Error('PNG export failed')),'image/png',.94))
  }finally{URL.revokeObjectURL(url)}
}

export default function ShareSheet({onClose}:ShareSheetProps){
  const [period,setPeriod]=useState<'week'|'month'>('week')
  const [name,setName]=useState('Prepza student')
  const [stats,setStats]=useState<Stats>({currentStreak:0,longestStreak:0,totalSeconds:0,period:'week'})
  const [busy,setBusy]=useState(true)
  const [message,setMessage]=useState('')
  const origin=typeof window!=='undefined'?window.location.origin:'https://prepza.app'
  const joinUrl=useMemo(()=>origin+'/signup?source=study-share',[origin])

  useEffect(()=>{
    let dead=false
    Promise.all([
      api<any>('/me'),
      api<any>('/streak'),
      api<any>('/study-time?period='+period)
    ]).then(([me,streak,time])=>{
      if(dead)return
      setName(me.display_name||me.name||'Prepza student')
      setStats({currentStreak:streak.current_streak||0,longestStreak:streak.longest_streak||0,totalSeconds:time.total_seconds||0,period})
    }).catch(()=>setMessage('Could not load your study stats.')).finally(()=>{if(!dead)setBusy(false)})
    return()=>{dead=true}
  },[period])

  const share=async()=>{
    setMessage('')
    try{
      const svg=svgCard(stats,name,joinUrl)
      const png=await svgToPng(svg)
      const file=new File([png],`prepza-${period}-study-stats.png`,{type:'image/png'})
      const shareText=stats.currentStreak>0
        ? `I'm on a ${stats.currentStreak}-day study streak on Prepza. Join me: ${joinUrl}`
        : `I'm studying with Prepza. Join me: ${joinUrl}`
      const nav:any=navigator
      if(nav.share && (!nav.canShare || nav.canShare({files:[file]}))){
        await nav.share({title:'My Prepza study stats',text:shareText,files:[file]})
        return
      }
      const a=document.createElement('a');a.href=URL.createObjectURL(png);a.download=file.name;a.click();URL.revokeObjectURL(a.href)
      await navigator.clipboard?.writeText(shareText)
      setMessage('Image saved and invite text copied.')
    }catch(e:any){ if(e?.name!=='AbortError') setMessage('Sharing was cancelled or unavailable.') }
  }

  const copy=async()=>{await navigator.clipboard?.writeText(joinUrl);setMessage('Join link copied.')}

  return <div style={{position:'fixed',inset:0,zIndex:1000,background:'rgba(0,0,0,.48)',display:'flex',alignItems:'flex-end',justifyContent:'center'}}>
    <div style={{width:'100%',maxWidth:520,maxHeight:'92vh',overflowY:'auto',background:'#fff',borderRadius:'26px 26px 0 0',padding:'14px 18px 28px',boxSizing:'border-box'}}>
      <div style={{width:42,height:4,borderRadius:99,background:'#D1D5DB',margin:'0 auto 16px'}}/>
      <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',marginBottom:14}}>
        <div><div style={{fontSize:18,fontWeight:800,color:N.navy}}>Share your progress</div><div style={{fontSize:11,color:'#9CA3AF',marginTop:3}}>A clean Prepza card made for social sharing.</div></div>
        <button onClick={onClose} aria-label="Close" style={{width:36,height:36,border:0,borderRadius:12,background:'#F3F4F6',color:N.navy,fontSize:20,cursor:'pointer'}}>×</button>
      </div>
      <div style={{display:'flex',gap:8,marginBottom:14}}>
        {(['week','month'] as const).map(p=><button key={p} onClick={()=>setPeriod(p)} style={{flex:1,padding:10,borderRadius:11,border:`1px solid ${period===p?N.gold:'#E5E7EB'}`,background:period===p?'#FFF9EA':'#fff',color:N.navy,fontWeight:800,cursor:'pointer'}}>{p==='week'?'This week':'This month'}</button>)}
      </div>
      <div style={{background:'linear-gradient(135deg,#0B1437,#1A2A5E)',borderRadius:22,padding:20,color:'#fff',aspectRatio:'9/15.9',display:'flex',flexDirection:'column',justifyContent:'space-between',boxSizing:'border-box'}}>
        <div><div style={{fontSize:11,letterSpacing:1.5,color:N.goldL,fontWeight:800}}>PREPZA</div><div style={{fontSize:11,letterSpacing:1,color:'rgba(255,255,255,.55)',marginTop:8}}>MY STUDY STATS</div></div>
        <div><div style={{fontSize:31,fontWeight:800,lineHeight:1.15}}>{stats.currentStreak} day study streak</div><div style={{fontSize:12,color:'rgba(255,255,255,.65)',marginTop:8}}>{name} is studying with Prepza.</div></div>
        <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:9}}><div style={{background:'rgba(255,255,255,.08)',borderRadius:14,padding:12}}><div style={{fontSize:9,color:'rgba(255,255,255,.55)'}}>STREAK</div><div style={{fontSize:25,fontWeight:800,color:N.goldL,marginTop:5}}>{stats.currentStreak}</div><div style={{fontSize:9,color:'rgba(255,255,255,.55)'}}>days</div></div><div style={{background:'rgba(255,255,255,.08)',borderRadius:14,padding:12}}><div style={{fontSize:9,color:'rgba(255,255,255,.55)'}}>STUDIED</div><div style={{fontSize:21,fontWeight:800,marginTop:8}}>{formatTime(stats.totalSeconds)}</div><div style={{fontSize:9,color:'rgba(255,255,255,.55)'}}>this {period}</div></div></div>
        <div><div style={{height:2,width:72,background:N.goldL,marginBottom:9}}/><div style={{fontSize:10,color:'rgba(255,255,255,.55)'}}>prepza.app · Study smarter. Together.</div></div>
      </div>
      <button onClick={share} disabled={busy} style={{width:'100%',marginTop:14,padding:14,border:0,borderRadius:14,background:`linear-gradient(135deg,${N.gold},${N.goldL})`,color:N.navy,fontWeight:800,fontSize:14,cursor:'pointer'}}>{busy?'Preparing…':'Share image'}</button>
      <button onClick={copy} style={{width:'100%',marginTop:8,padding:12,border:`1px solid ${N.navy}20`,borderRadius:14,background:'#fff',color:N.navy,fontWeight:700,cursor:'pointer'}}>Copy join link</button>
      {message&&<div style={{fontSize:11,color:'#6B7280',textAlign:'center',marginTop:10}}>{message}</div>}
      <div style={{fontSize:10,color:'#9CA3AF',textAlign:'center',marginTop:12}}>The image carries the story; the accompanying join link takes friends to Prepza.</div>
    </div>
  </div>
}
