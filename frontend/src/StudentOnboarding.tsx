import { useEffect, useState } from 'react'

type Props = { screen:string; setScreen:(screen:any)=>void }

const STEPS = [
  { title:'Welcome to Prepza', body:'This is your study home. Your main study tools and recent activity start here.', screen:'home' },
  { title:'Study Hub', body:'Study Hub is where you keep your course documents and offline study copies. Start here when you want your materials available without internet.', screen:'home' },
  { title:'Library', body:'Library is where you discover course materials for your university, programme, year and semester.', screen:'library' },
  { title:'Podcasts and study materials', body:'From your study documents you can create summaries, flashcards, mind maps, quizzes and podcasts. Existing generated materials are reused when they match exactly.', screen:'home' },
  { title:'Ada', body:'Ada is your study tutor. Ask questions about what you are learning and use it to work through difficult concepts.', screen:'ai-tutor' },
  { title:'Chat', body:'Chat lets you study with classmates through private chats and groups.', screen:'chats' },
  { title:'Streaks and activity', body:'Your study activity and streaks help you keep track of consistent study time.', screen:'study-streak' },
]

export default function StudentOnboarding({screen,setScreen}:Props) {
  const [open,setOpen]=useState(false)
  const [step,setStep]=useState(0)
  const [ready,setReady]=useState(false)
  useEffect(()=>{
    if (screen !== 'home' || localStorage.getItem('prepza_onboarding_v1_done') === '1') return
    let cancelled=false
    fetch('/me',{credentials:'include'}).then(r=>r.ok?r.json():null).then(me=>{
      if (!cancelled && me?.user_id && !me?.is_admin) setOpen(true)
    }).catch(()=>{}).finally(()=>{if(!cancelled)setReady(true)})
    return ()=>{cancelled=true}
  },[screen])
  const finish=()=>{localStorage.setItem('prepza_onboarding_v1_done','1');setOpen(false)}
  if (!ready || !open) return null
  const current=STEPS[step]
  const isLast=step===STEPS.length-1
  const go=(direction:1|-1)=>{
    if(direction===1 && !isLast){const next=step+1;setStep(next);if(STEPS[next].screen!==screen)setScreen(STEPS[next].screen)}
    if(direction===-1 && step>0){const prev=step-1;setStep(prev);if(STEPS[prev].screen!==screen)setScreen(STEPS[prev].screen)}
  }
  return <div style={{position:'fixed',inset:0,zIndex:9999,pointerEvents:'none'}}>
    <div style={{position:'absolute',inset:0,background:'rgba(7,15,40,.48)'}}/>
    <div style={{position:'absolute',left:'50%',bottom:24,transform:'translateX(-50%)',width:'min(92vw,430px)',background:'var(--prepza-card,#fff)',borderRadius:18,padding:20,boxShadow:'0 18px 50px rgba(0,0,0,.28)',pointerEvents:'auto'}}>
      <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:12}}><div style={{fontSize:10,fontWeight:800,letterSpacing:.8,textTransform:'uppercase',opacity:.55}}>Prepza guide</div><button onClick={finish} style={{border:0,background:'transparent',fontSize:12,fontWeight:700,cursor:'pointer'}}>Skip tour</button></div>
      <div style={{display:'flex',gap:5,marginBottom:14}}>{STEPS.map((_,i)=><div key={i} style={{height:4,flex:1,borderRadius:99,background:i<=step?'#C9A84C':'rgba(127,127,127,.2)'}}/>)}</div>
      <div style={{fontSize:20,fontWeight:850,marginBottom:7}}>{current.title}</div><div style={{fontSize:13,lineHeight:1.65,opacity:.72}}>{current.body}</div>
      <div style={{display:'flex',gap:8,marginTop:18}}>{step>0&&<button onClick={()=>go(-1)} style={{flex:1,padding:'11px 0',borderRadius:11,border:'1px solid rgba(127,127,127,.25)',background:'transparent',fontWeight:700,cursor:'pointer'}}>Back</button>}<button onClick={()=>isLast?finish():go(1)} style={{flex:2,padding:'11px 0',border:0,borderRadius:11,background:'#0B1437',color:'#fff',fontWeight:800,cursor:'pointer'}}>{isLast?'Finish':'Next'}</button></div>
      <div style={{marginTop:9,textAlign:'center',fontSize:10,opacity:.5}}>You can skip this guide at any time.</div>
    </div>
  </div>
}
