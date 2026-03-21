'use client'
import { useState, useEffect, useRef } from 'react'
import { useRouter } from 'next/navigation'
import NavBar from '@/components/layout/NavBar'
import { getPricePrediction, getPriceForecast, getHiddenRoutes } from '@/lib/api'
import type { PricePrediction, PriceForecast } from '@/lib/api'
import { format, addDays } from 'date-fns'

function PriceChart({ forecast }: { forecast: { date:string; price:number; confidence_low:number; confidence_high:number }[] }) {
  const ref = useRef<SVGSVGElement>(null)
  useEffect(() => {
    if (!ref.current || !forecast.length) return
    const W=720,H=220,pl=52,pr=20,pt=20,pb=36
    const prices = forecast.map(d=>d.price)
    const lo     = forecast.map(d=>d.confidence_low)
    const hi     = forecast.map(d=>d.confidence_high)
    const n=prices.length, cw=W-pl-pr, ch=H-pt-pb
    const mn=Math.min(...lo)*0.95, mx=Math.max(...hi)*1.05
    const sx=(i:number)=>pl+(i/(n-1))*cw
    const sy=(v:number)=>pt+ch-((v-mn)/(mx-mn))*ch
    const linePts=prices.map((p,i)=>`${i?'L':'M'}${sx(i).toFixed(1)},${sy(p).toFixed(1)}`).join('')
    const loPts=lo.map((p,i)=>`${i?'L':'M'}${sx(i).toFixed(1)},${sy(p).toFixed(1)}`).join('')
    const hiPts=hi.map((p,i)=>`${i?'L':'M'}${sx(i).toFixed(1)},${sy(p).toFixed(1)}`).join('')
    const bandPath=hi.map((p,i)=>`${i?'L':'M'}${sx(i).toFixed(1)},${sy(p).toFixed(1)}`).join('')+lo.slice().reverse().map((p,i)=>`L${sx(n-1-i).toFixed(1)},${sy(p).toFixed(1)}`).join('')+'Z'
    const areaPath=linePts+`L${sx(n-1).toFixed(1)},${(pt+ch).toFixed(1)}L${pl.toFixed(1)},${(pt+ch).toFixed(1)}Z`
    const bestIdx=prices.indexOf(Math.min(...prices))
    const kSteps = [mn,mn+(mx-mn)/4,mn+(mx-mn)/2,mn+(mx-mn)*3/4,mx].map(v=>Math.round(v/1000))
    const gridLines=kSteps.map(k=>{const y=sy(k*1000);return`<line x1="${pl}" y1="${y.toFixed(1)}" x2="${W-pr}" y2="${y.toFixed(1)}" stroke="#efefed" stroke-width="1"/><text x="${pl-8}" y="${(y+4).toFixed(1)}" text-anchor="end" fill="#9b9890" font-size="9.5" font-family="Martian Mono,monospace">₹${k}k</text>`}).join('')
    const step=Math.floor(n/4)
    const dateLabels=[0,step,step*2,step*3,n-1].map(i=>`<text x="${sx(i).toFixed(1)}" y="${H-8}" text-anchor="middle" fill="#9b9890" font-size="9" font-family="Martian Mono,monospace">${forecast[i]?.date?.slice(5)||''}</text>`).join('')
    const bestPx=sy(prices[bestIdx]),bestX=sx(bestIdx)
    const bestKVal=Math.round(prices[bestIdx]/1000*10)/10
    ref.current.innerHTML=`${gridLines}${dateLabels}<path d="${bandPath}" fill="rgba(232,25,26,.04)"/><path d="${loPts}" stroke="#e8d8d8" stroke-width="1" fill="none" stroke-dasharray="4,4"/><path d="${hiPts}" stroke="#e8d8d8" stroke-width="1" fill="none" stroke-dasharray="4,4"/><path d="${areaPath}" fill="rgba(232,25,26,.04)"/><path d="${linePts}" stroke="#131210" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/><line x1="${bestX}" y1="${pt}" x2="${bestX}" y2="${pt+ch}" stroke="rgba(22,163,74,.3)" stroke-width="1" stroke-dasharray="4,3"/><circle cx="${bestX}" cy="${bestPx}" r="6" fill="#22c55e" stroke="white" stroke-width="2"/><rect x="${bestX-22}" y="${(bestPx-28).toFixed(0)}" width="44" height="18" fill="#131210" rx="2"/><text x="${bestX}" y="${(bestPx-15).toFixed(0)}" text-anchor="middle" fill="white" font-size="8.5" font-family="Martian Mono,monospace" font-weight="700">₹${bestKVal}k</text>${prices.map((p,i)=>`<circle cx="${sx(i).toFixed(1)}" cy="${sy(p).toFixed(1)}" r="2.5" fill="${i===bestIdx?'#22c55e':'#131210'}" opacity="${i===bestIdx?1:.55}"/>`).join('')}`
  }, [forecast])
  return <svg ref={ref} width="100%" height="220" viewBox="0 0 720 220" preserveAspectRatio="none" />
}

export default function PredictPage() {
  const router = useRouter()
  const [origin,      setOrigin]      = useState('DEL')
  const [destination, setDestination] = useState('DXB')
  const depDate = format(addDays(new Date(),32),'yyyy-MM-dd')

  const [prediction,    setPrediction]    = useState<PricePrediction|null>(null)
  const [forecast,      setForecast]      = useState<PriceForecast|null>(null)
  const [hiddenRoutes,  setHiddenRoutes]  = useState<any[]>([])
  const [loading,       setLoading]       = useState(false)
  const [error,         setError]         = useState('')

  const load = async (org=origin, dest=destination) => {
    setLoading(true); setError('')
    try {
      const [pred, fc] = await Promise.all([
        getPricePrediction(org, dest, depDate),
        getPriceForecast(org, dest),
      ])
      setPrediction(pred); setForecast(fc)
      if (pred.predicted_price) {
        const hr = await getHiddenRoutes(org, dest, depDate, pred.predicted_price) as any
        setHiddenRoutes(hr.hidden_routes || [])
      }
    } catch(e:any) {
      setError(e.message)
    }
    setLoading(false)
  }

  useEffect(() => { load() }, [])

  const recColor = (rec?:string) => rec==='BOOK_NOW'?'#e8191a':rec==='BOOK_SOON'?'#131210':'var(--grey4)'

  return (
    <div>
      <NavBar />
      <div style={{ paddingTop:'60px' }}>
        <div className="predict-hero">
          <div className="wrap">
            <div style={{ display:'flex', alignItems:'center', gap:'12px', marginBottom:'20px' }}>
              <span style={{ fontFamily:'var(--fm)', fontSize:'.65rem', fontWeight:500, letterSpacing:'.14em', textTransform:'uppercase', color:'rgba(255,255,255,.3)' }}>SkyMind AI</span>
              <div style={{ height:'1px', width:'32px', background:'rgba(255,255,255,.15)' }}/>
              <span className="badge badge-red">Prophet ML</span>
            </div>
            <div className="predict-title">PRICE<br/>FORECAST<em>& AI Prediction</em></div>
            <p style={{ color:'rgba(255,255,255,.5)', fontSize:'.9rem', marginTop:'16px', maxWidth:'480px', lineHeight:'1.7' }}>ML-powered 30-day price forecast with confidence intervals. Know exactly when to book and when to wait.</p>
          </div>
        </div>

        <div className="wrap">
          {error && (
            <div style={{ border:'1px solid var(--red)', padding:'16px', margin:'24px 0', background:'rgba(232,25,26,.04)', fontSize:'.875rem', color:'var(--red)' }}>
              {error} — Make sure uvicorn is running on port 8000.
            </div>
          )}

          <div className="predict-grid">
            {/* Sidebar */}
            <div className="rec-panel">
              <div style={{ display:'flex', gap:'10px', alignItems:'end', marginBottom:'14px' }}>
                <div style={{ flex:1 }}>
                  <label className="field-label">From</label>
                  <input className="inp" value={origin} onChange={e=>setOrigin(e.target.value.toUpperCase())} maxLength={3} style={{ fontFamily:'var(--fm)', fontWeight:700, textAlign:'center', fontSize:'1.1rem', letterSpacing:'.08em' }}/>
                </div>
                <div style={{ paddingBottom:'12px', color:'var(--grey3)' }}>—</div>
                <div style={{ flex:1 }}>
                  <label className="field-label">To</label>
                  <input className="inp" value={destination} onChange={e=>setDestination(e.target.value.toUpperCase())} maxLength={3} style={{ fontFamily:'var(--fm)', fontWeight:700, textAlign:'center', fontSize:'1.1rem', letterSpacing:'.08em' }}/>
                </div>
              </div>
              <button className="btn btn-primary" style={{ width:'100%', justifyContent:'center', marginBottom:'14px' }} onClick={()=>load(origin,destination)}>
                {loading ? 'Analyzing...' : 'Get AI Prediction'}
              </button>

              <div className="rec-card">
                <div className="rec-header">
                  <div className="rec-label">AI Recommendation</div>
                  <span className="badge badge-red" style={{ fontSize:'.58rem' }}>Live</span>
                </div>
                <div className="rec-body">
                  {loading ? (
                    <>
                      <div className="skel" style={{ height:'32px', width:'60%', marginBottom:'12px' }}/>
                      <div className="skel" style={{ height:'60px', marginBottom:'12px' }}/>
                    </>
                  ) : prediction ? (
                    <>
                      <div className="rec-rec" style={{ color: recColor(prediction.recommendation) }}>
                        {prediction.recommendation?.replace('_',' ') || 'ANALYSING'}
                      </div>
                      <div className="rec-reason">{prediction.reason}</div>
                      {[
                        { label:'Predicted price', val:`₹${Math.round(prediction.predicted_price).toLocaleString('en-IN')}` },
                        { label:'Rise probability', val:`${Math.round((prediction.probability_increase||0)*100)}%`, red: (prediction.probability_increase||0) > .6 },
                        { label:'Days to departure', val: String(prediction.days_until_departure||32) },
                        { label:'Price trend', val: prediction.price_trend?.replace('_',' ') || '--', red: prediction.price_trend?.includes('RISING') },
                        { label:'Confidence', val:`${Math.round((prediction.confidence||0)*100)}%` },
                      ].map(s => (
                        <div key={s.label} className="rec-stat">
                          <span className="rec-stat-label">{s.label}</span>
                          <span className="rec-stat-val" style={{ color:s.red?'var(--red)':undefined }}>{s.val}</span>
                        </div>
                      ))}
                    </>
                  ) : (
                    <div style={{ padding:'20px 0', fontSize:'.85rem', color:'var(--grey3)', textAlign:'center' }}>Enter route and click Get AI Prediction</div>
                  )}
                </div>
              </div>
            </div>

            {/* Main */}
            <div>
              {/* Stat trio */}
              <div className="stat-trio">
                {loading ? [0,1,2].map(i=>(
                  <div key={i} className="stat-trio-item">
                    <div className="skel" style={{ height:'12px', width:'60%', marginBottom:'8px' }}/>
                    <div className="skel" style={{ height:'24px', width:'40%' }}/>
                  </div>
                )) : forecast ? [
                  { label:'Best day to fly', val:`₹${Math.round(forecast.best_day?.price||0).toLocaleString('en-IN')}`, color:'#166534', sub: forecast.best_day?.date||'' },
                  { label:'Most expensive',  val:`₹${Math.round(forecast.worst_day?.price||0).toLocaleString('en-IN')}`, color:'var(--red)', sub: forecast.worst_day?.date||'' },
                  { label:'Potential savings', val:`₹${Math.round((forecast.worst_day?.price||0)-(forecast.best_day?.price||0)).toLocaleString('en-IN')}`, color:'var(--black)', sub:'Best vs worst date', subRed:true },
                ].map(s=>(
                  <div key={s.label} className="stat-trio-item">
                    <div className="sti-label">{s.label}</div>
                    <div className="sti-val" style={{ color:s.color }}>{s.val}</div>
                    <div className="sti-sub" style={{ color:s.subRed?'var(--red)':undefined }}>{s.sub}</div>
                  </div>
                )) : [
                  { label:'Best day to fly', val:'--', color:'var(--grey3)', sub:'Run prediction' },
                  { label:'Most expensive',  val:'--', color:'var(--grey3)', sub:'Run prediction' },
                  { label:'Potential savings',val:'--',color:'var(--grey3)', sub:'Run prediction' },
                ].map(s=>(
                  <div key={s.label} className="stat-trio-item">
                    <div className="sti-label">{s.label}</div>
                    <div className="sti-val" style={{ color:s.color }}>{s.val}</div>
                    <div className="sti-sub">{s.sub}</div>
                  </div>
                ))}
              </div>

              {/* Chart */}
              <div className="chart-area">
                <div className="chart-title">30-DAY PRICE FORECAST</div>
                <div className="chart-sub">{origin} → {destination} · Confidence interval ±15% · Prophet model</div>
                {loading && <div className="skel" style={{ height:'220px' }}/>}
                {!loading && forecast?.forecast && <PriceChart forecast={forecast.forecast} />}
                {!loading && !forecast && <div style={{ height:'220px', display:'flex', alignItems:'center', justifyContent:'center', color:'var(--grey3)', fontSize:'.875rem' }}>Run a prediction to see the chart</div>}
              </div>

              {/* Hidden routes */}
              <div className="hidden-section">
                <div className="hidden-header">
                  <div>
                    <div style={{ fontWeight:700, fontSize:'.9rem', color:'var(--black)' }}>HIDDEN ROUTES</div>
                    <div style={{ fontSize:'.75rem', color:'var(--grey3)', marginTop:'2px', fontFamily:'var(--fm)' }}>Dijkstra's algorithm · {hiddenRoutes.length} alternatives found</div>
                  </div>
                  {hiddenRoutes.length > 0 && <span className="badge badge-red">Save up to {Math.round(Math.max(...hiddenRoutes.map(r=>r.savings_percent||0)))}%</span>}
                </div>
                {hiddenRoutes.length === 0 && !loading && (
                  <div style={{ padding:'24px', fontSize:'.85rem', color:'var(--grey3)', textAlign:'center' }}>
                    {prediction ? 'No cheaper hidden routes found for this route.' : 'Run prediction to discover hidden routes.'}
                  </div>
                )}
                {hiddenRoutes.map((r,i) => (
                  <div key={i} className="hr-item" style={{ borderBottom:i<hiddenRoutes.length-1?'1px solid var(--grey1)':'none' }} onClick={()=>router.push(`/flights?origin=${origin}&destination=${destination}&departure_date=${depDate}`)}>
                    <div>
                      <div className="hr-path">
                        {(r.path||[origin,(r.via||'HUB'),destination]).map((p:string,j:number,arr:string[])=>[
                          <span key={p}>{p}</span>,
                          j<arr.length-1&&<span key={`arr${j}`} style={{color:'var(--grey3)'}}>→</span>
                        ])}
                      </div>
                      <div className="hr-via">1 stop · via {r.via||'hub'}</div>
                    </div>
                    <div>
                      <div className="hr-price">₹{Math.round(r.total_price||0).toLocaleString('en-IN')}</div>
                      <div className="hr-save">Save ₹{Math.round(r.savings_vs_direct||0).toLocaleString('en-IN')} ({r.savings_percent?.toFixed(1)}%)</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
