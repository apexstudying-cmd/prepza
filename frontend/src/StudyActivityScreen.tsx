import React, { useEffect, useMemo, useState } from 'react'

type Props = { setScreen: (s: any) => void }
type Day = { date: string; studied: boolean; is_future: boolean; study_seconds: number }
type MonthResponse = {
  current_streak: number
  longest_streak: number
  calendar_month: string
  calendar_start_weekday: number
  earliest_month: string
  calendar: Day[]
}

const N = { navy:'#0B1437', navy2:'#132046', navy3:'#1A2A5E', gold:'#C9A84C', goldL:'#E8C97E' }

async function api<T>(path: string): Promise<T> {
  const r = await fetch(path, { credentials:'include', headers:{'Content-Type':'application/json'} })
  const b = await r.json().catch(() => null)
  if (!r.ok) throw new Error(b?.error || 'Request failed')
  return b as T
}

function fmt(seconds:number) {
  const mins = Math.round(seconds / 60)
  if (mins < 60) return `${mins}m`
  const h = Math.floor(mins / 60), m = mins % 60
  return m ? `${h}h ${m}m` : `${h}h`
}

function monthKey(d:Date) {
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}`
}

function level(seconds:number) {
  if (!seconds) return 0
  if (seconds < 900) return 1
  if (seconds < 2700) return 2
  if (seconds < 5400) return 3
  return 4
}

export default function StudyActivityScreen({ setScreen }: Props) {
  const [months, setMonths] = useState<MonthResponse[]>([])
  const [week, setWeek] = useState(0)
  const [monthTotal, setMonthTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let dead = false
    const now = new Date()
    const keys = Array.from({length: 6}, (_, i) => {
      const d = new Date(now.getFullYear(), now.getMonth() - i, 1)
      return monthKey(d)
    })
    Promise.all([
      ...keys.map(k => api<MonthResponse>(`/streak?month=${k}`)),
      api<any>('/study-time?period=week'),
      api<any>('/study-time?period=month')
    ]).then(results => {
      if (dead) return
      setMonths(results.slice(0,6) as MonthResponse[])
      setWeek(results[6]?.total_seconds || 0)
      setMonthTotal(results[7]?.total_seconds || 0)
    }).catch(e => { if (!dead) setError(e?.message || 'Could not load study activity.') })
      .finally(() => { if (!dead) setLoading(false) })
    return () => { dead = true }
  }, [])

  const latest = months[0]
  const current = latest?.current_streak || 0
  const longest = latest?.longest_streak || 0

  const activity = useMemo(() => {
    const map = new Map<string, number>()
    months.forEach(m => m.calendar.forEach(d => map.set(d.date, d.study_seconds || 0)))
    const now = new Date()
    const end = new Date(now.getFullYear(), now.getMonth(), now.getDate())
    const start = new Date(end)
    start.setDate(start.getDate() - 181)
    while (start.getDay() !== 0) start.setDate(start.getDate() - 1)
    const cells: {date:string; seconds:number; future:boolean}[] = []
    for (let d = new Date(start); d <= end || d.getDay() !== 0; d.setDate(d.getDate()+1)) {
      const key = `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`
      cells.push({ date:key, seconds:map.get(key)||0, future:d>end })
    }
    return cells
  }, [months])

  const weeks = useMemo(() => {
    const out: typeof activity[] = []
    for (let i=0; i<activity.length; i+=7) out.push(activity.slice(i,i+7))
    return out
  }, [activity])

  const monthLabels = useMemo(() => {
    const labels:{label:string; col:number}[] = []
    let last = ''
    weeks.forEach((w, i) => {
      const d = w[0]?.date
      if (!d) return
      const month = new Date(d+'T00:00:00').toLocaleDateString('en-US',{month:'short'})
      if (month !== last) { labels.push({label:month,col:i}); last=month }
    })
    return labels
  }, [weeks])

  if (loading) return (
    <div style={{flex:1,background:'#F8F9FC',display:'flex',flexDirection:'column'}}>
      <div style={{background:N.navy,padding:'18px 18px 24px',color:'#fff'}}>
        <button onClick={()=>setScreen('profile')} style={{width:34,height:34,border:0,borderRadius:10,background:'rgba(255,255,255,.1)',color:'#fff',cursor:'pointer'}}>‹</button>
        <div style={{fontWeight:800,fontSize:20,marginTop:18}}>Study</div>
      </div>
      <div style={{padding:20,color:'#8A92A6',fontSize:13}}>Loading your study activity…</div>
    </div>
  )

  if (error) return (
    <div style={{flex:1,background:'#F8F9FC',padding:20}}>
      <button onClick={()=>setScreen('profile')} style={{border:0,background:'none',fontSize:26,color:N.navy,cursor:'pointer'}}>‹</button>
      <div style={{marginTop:30,color:'#B91C1C',fontSize:13}}>{error}</div>
    </div>
  )

  return (
    <div style={{flex:1,overflowY:'auto',background:'#F8F9FC',fontFamily:'Plus Jakarta Sans, sans-serif'}}>
      <div style={{background:`linear-gradient(180deg,${N.navy},${N.navy3})`,color:'#fff',padding:'16px 18px 24px'}}>
        <div style={{display:'flex',alignItems:'center',gap:12}}>
          <button onClick={()=>setScreen('profile')} aria-label="Back" style={{width:34,height:34,border:0,borderRadius:10,background:'rgba(255,255,255,.1)',color:'#fff',cursor:'pointer',fontSize:22}}>‹</button>
          <div style={{fontWeight:800,fontSize:19}}>Study</div>
        </div>
        <div style={{display:'grid',gridTemplateColumns:'1.15fr 1fr 1fr',gap:9,marginTop:20}}>
          <div style={{background:'rgba(255,255,255,.1)',border:'1px solid rgba(255,255,255,.1)',borderRadius:16,padding:'15px 14px'}}>
            <div style={{fontSize:10,color:'rgba(255,255,255,.58)',fontWeight:700,letterSpacing:.6}}>CURRENT STREAK</div>
            <div style={{fontSize:35,fontWeight:800,color:N.goldL,lineHeight:1,marginTop:7}}>{current}</div>
            <div style={{fontSize:10,color:'rgba(255,255,255,.55)',marginTop:4}}>days</div>
          </div>
          <div style={{background:'rgba(255,255,255,.08)',borderRadius:16,padding:'15px 12px'}}>
            <div style={{fontSize:10,color:'rgba(255,255,255,.58)',fontWeight:700}}>THIS WEEK</div>
            <div style={{fontSize:25,fontWeight:800,marginTop:12}}>{fmt(week)}</div>
          </div>
          <div style={{background:'rgba(255,255,255,.08)',borderRadius:16,padding:'15px 12px'}}>
            <div style={{fontSize:10,color:'rgba(255,255,255,.58)',fontWeight:700}}>LONGEST</div>
            <div style={{fontSize:25,fontWeight:800,marginTop:12}}>{longest}d</div>
          </div>
        </div>
      </div>

      <div style={{padding:'16px 14px 30px'}}>
        <div style={{background:'#fff',borderRadius:18,padding:'16px 14px',boxShadow:'0 3px 14px rgba(11,20,55,.06)'}}>
          <div style={{display:'flex',justifyContent:'space-between',alignItems:'flex-end',marginBottom:14}}>
            <div><div style={{fontWeight:800,fontSize:14,color:'#17203B'}}>Study activity</div><div style={{fontSize:11,color:'#9299A9',marginTop:3}}>Your last 6 months</div></div>
            <div style={{fontSize:11,color:'#9299A9'}}>{fmt(monthTotal)} this month</div>
          </div>
          <div style={{overflowX:'auto',paddingBottom:3}}>
            <div style={{minWidth:390,position:'relative',paddingTop:17}}>
              <div style={{position:'absolute',top:0,left:0,right:0,height:14}}>
                {monthLabels.map(m=><span key={m.label+m.col} style={{position:'absolute',left:`${m.col*13}px`,fontSize:9,color:'#9AA1B0'}}>{m.label}</span>)}
              </div>
              <div style={{display:'grid',gridTemplateColumns:`repeat(${weeks.length},10px)`,gridTemplateRows:'repeat(7,10px)',gridAutoFlow:'column',gap:3}}>
                {weeks.flatMap((w,wi)=>w.map((d,di)=><div key={d.date} title={d.future?'':d.date} style={{gridColumn:wi+1,gridRow:di+1,width:10,height:10,borderRadius:2,background:d.future?'transparent':(['#F0F1F4',`${N.gold}35`,`${N.gold}70`,`${N.gold}A8`,N.gold][level(d.seconds)]),border:d.future?'none':level(d.seconds)===0?'1px solid #E3E6EC':'none'}}/>))}
              </div>
            </div>
          </div>
          <div style={{display:'flex',alignItems:'center',justifyContent:'flex-end',gap:5,marginTop:12,fontSize:9,color:'#969DAE'}}>
            Less
            {[0,1,2,3,4].map(l=><span key={l} style={{width:10,height:10,borderRadius:2,background:['#F0F1F4',`${N.gold}35`,`${N.gold}70`,`${N.gold}A8`,N.gold][l],border:l===0?'1px solid #E3E6EC':'none'}}/>)} More
          </div>
        </div>

        <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:10,marginTop:10}}>
          <div style={{background:'#fff',borderRadius:16,padding:14,boxShadow:'0 3px 14px rgba(11,20,55,.05)'}}><div style={{fontSize:10,color:'#9299A9'}}>THIS MONTH</div><div style={{fontSize:22,fontWeight:800,color:N.navy,marginTop:6}}>{fmt(monthTotal)}</div></div>
          <div style={{background:'#fff',borderRadius:16,padding:14,boxShadow:'0 3px 14px rgba(11,20,55,.05)'}}><div style={{fontSize:10,color:'#9299A9'}}>BEST STREAK</div><div style={{fontSize:22,fontWeight:800,color:N.navy,marginTop:6}}>{longest} days</div></div>
        </div>

        <button onClick={()=>setScreen('share-sheet')} style={{width:'100%',marginTop:12,padding:14,border:0,borderRadius:15,background:`linear-gradient(135deg,${N.gold},${N.goldL})`,color:N.navy,fontWeight:800,fontSize:14,cursor:'pointer'}}>Share study progress</button>
      </div>
    </div>
  )
}
