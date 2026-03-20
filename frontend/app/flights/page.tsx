'use client'
import { useState, useEffect, Suspense } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import Link from 'next/link'
import NavBar from '@/components/layout/NavBar'
import { searchFlights, formatDuration, formatPrice } from '@/lib/api'
import type { FlightOffer, FlightSearchParams } from '@/lib/api'
import { format, addDays } from 'date-fns'

function FlightsContent() {
  const router = useRouter()
  const params = useSearchParams()
  const tomorrow = format(addDays(new Date(), 1), 'yyyy-MM-dd')

  const [form, setForm] = useState({
    origin:         params.get('origin') || 'DEL',
    destination:    params.get('destination') || 'BOM',
    departure_date: params.get('departure_date') || tomorrow,
    adults:         params.get('adults') || '1',
    cabin_class:    params.get('cabin_class') || 'ECONOMY',
  })

  const [flights, setFlights]   = useState<FlightOffer[]>([])
  const [loading, setLoading]   = useState(false)
  const [error, setError]       = useState('')
  const [sort, setSort]         = useState('Price')
  const [searched, setSearched] = useState(false)

  const doSearch = async () => {
    setLoading(true); setError(''); setSearched(true)
    try {
      const res = await searchFlights({
        origin: form.origin, destination: form.destination,
        departure_date: form.departure_date, adults: Number(form.adults),
        cabin_class: form.cabin_class,
      })
      let sorted = [...(res.flights || [])]
      if (sort === 'Price')     sorted.sort((a,b) => a.price.total - b.price.total)
      if (sort === 'Duration')  sorted.sort((a,b) => (a.itineraries[0]?.duration||'').localeCompare(b.itineraries[0]?.duration||''))
      if (sort === 'Departure') sorted.sort((a,b) => (a.itineraries[0]?.segments[0]?.departure_time||'').localeCompare(b.itineraries[0]?.segments[0]?.departure_time||''))
      setFlights(sorted)
    } catch(e: any) {
      setError(e.message || 'Search failed. Check backend is running.')
      setFlights([])
    }
    setLoading(false)
  }

  useEffect(() => { doSearch() }, [])

  const recColor = (rec?: string) => {
    if (rec === 'BOOK_NOW')  return 'badge-red'
    if (rec === 'BOOK_SOON') return 'badge-black'
    return 'badge-off'
  }
  const recLabel = (rec?: string) => {
    if (rec === 'BOOK_NOW')  return 'BOOK NOW'
    if (rec === 'BOOK_SOON') return 'BOOK SOON'
    if (rec === 'WAIT')      return 'WAIT'
    if (rec === 'LAST_MINUTE') return 'LAST MIN'
    return rec || ''
  }

  return (
    <div>
      <NavBar />
      <div style={{ paddingTop: '60px' }}>

        {/* Search strip */}
        <div className="search-strip">
          <div className="wrap">
            <div className="strip-grid">
              <div>
                <label className="field-label">From</label>
                <input className="inp" value={form.origin} onChange={e=>setForm(f=>({...f,origin:e.target.value.toUpperCase()}))} maxLength={3} style={{ fontFamily:'var(--fm)', fontWeight:700, letterSpacing:'.08em' }}/>
              </div>
              <button className="swap-btn" style={{ alignSelf:'end' }} onClick={()=>setForm(f=>({...f,origin:f.destination,destination:f.origin}))}>
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M7 16V4m0 0L3 8m4-4l4 4M17 8v12m0 0l4-4m-4 4l-4-4"/></svg>
              </button>
              <div>
                <label className="field-label">To</label>
                <input className="inp" value={form.destination} onChange={e=>setForm(f=>({...f,destination:e.target.value.toUpperCase()}))} maxLength={3} style={{ fontFamily:'var(--fm)', fontWeight:700, letterSpacing:'.08em' }}/>
              </div>
              <div>
                <label className="field-label">Date</label>
                <input type="date" className="inp" value={form.departure_date} min={tomorrow} onChange={e=>setForm(f=>({...f,departure_date:e.target.value}))}/>
              </div>
              <div>
                <label className="field-label">Passengers</label>
                <select className="inp" value={form.adults} onChange={e=>setForm(f=>({...f,adults:e.target.value}))}>
                  {[1,2,3,4,5].map(n=><option key={n} value={n}>{n} {n===1?'Adult':'Adults'}</option>)}
                </select>
              </div>
              <div className="strip-hide">
                <label className="field-label">Class</label>
                <select className="inp" value={form.cabin_class} onChange={e=>setForm(f=>({...f,cabin_class:e.target.value}))}>
                  <option value="ECONOMY">Economy</option>
                  <option value="BUSINESS">Business</option>
                  <option value="FIRST">First</option>
                </select>
              </div>
              <button className="btn btn-red-full" onClick={doSearch}>Search</button>
            </div>
          </div>
        </div>

        <div className="wrap" style={{ paddingTop:'28px', paddingBottom:'60px' }}>

          {/* Results bar */}
          <div className="results-bar">
            <div>
              <div className="results-title">
                <span style={{ fontFamily:'var(--fm)', fontWeight:700 }}>{form.origin}</span>
                <span style={{ color:'var(--grey3)', fontSize:'1.2rem', fontFamily:'var(--fm)' }}> — </span>
                <span style={{ fontFamily:'var(--fm)', fontWeight:700 }}>{form.destination}</span>
                <span className="badge badge-black" style={{ marginLeft:'4px' }}>{form.departure_date}</span>
              </div>
              <div className="results-count" style={{ marginTop:'4px' }}>
                {loading ? 'Searching live fares...' : searched ? `${flights.length} flights found · AI-scored · sorted by ${sort.toLowerCase()}` : ''}
              </div>
            </div>
            <div className="sort-strip">
              {['Price','Duration','Departure'].map(s => (
                <button key={s} className={`sort-btn${sort===s?' active':''}`} onClick={()=>setSort(s)}>{s}</button>
              ))}
            </div>
          </div>

          {/* Error */}
          {error && (
            <div style={{ border:'1px solid var(--red)', padding:'20px', background:'rgba(232,25,26,.04)', marginBottom:'16px' }}>
              <div style={{ fontWeight:600, color:'var(--red)', marginBottom:'4px' }}>Search failed</div>
              <div style={{ fontSize:'.85rem', color:'var(--grey4)' }}>{error}</div>
              <div style={{ fontSize:'.78rem', color:'var(--grey3)', marginTop:'8px', fontFamily:'var(--fm)' }}>Make sure uvicorn is running on port 8000 and your Amadeus keys are set in backend/.env</div>
            </div>
          )}

          {/* Loading skeletons */}
          {loading && [1,2,3].map(i => (
            <div key={i} className="flight-card" style={{ padding:'20px', marginBottom:'8px' }}>
              <div style={{ display:'grid', gridTemplateColumns:'180px 1fr 160px', gap:'0' }}>
                <div style={{ paddingRight:'20px' }}>
                  <div className="skel" style={{ height:'42px', width:'42px', marginBottom:'8px' }}/>
                  <div className="skel" style={{ height:'14px', width:'80%', marginBottom:'4px' }}/>
                  <div className="skel" style={{ height:'10px', width:'60%' }}/>
                </div>
                <div style={{ padding:'0 24px' }}>
                  <div style={{ display:'flex', gap:'20px', alignItems:'center' }}>
                    <div className="skel" style={{ height:'32px', width:'70px' }}/>
                    <div className="skel" style={{ height:'1px', flex:1 }}/>
                    <div className="skel" style={{ height:'32px', width:'70px' }}/>
                  </div>
                </div>
                <div style={{ paddingLeft:'20px' }}>
                  <div className="skel" style={{ height:'32px', width:'80%', marginBottom:'6px' }}/>
                  <div className="skel" style={{ height:'36px', width:'100%' }}/>
                </div>
              </div>
            </div>
          ))}

          {/* No results */}
          {!loading && searched && flights.length === 0 && !error && (
            <div style={{ border:'1px solid var(--grey1)', padding:'60px', textAlign:'center' }}>
              <div style={{ fontFamily:'var(--fd)', fontSize:'2rem', color:'var(--black)', marginBottom:'8px' }}>NO FLIGHTS FOUND</div>
              <div style={{ fontSize:'.875rem', color:'var(--grey4)', marginBottom:'20px' }}>Try a different date or route. Amadeus test API has limited coverage.</div>
              <button className="btn btn-primary" onClick={doSearch}>Try again</button>
            </div>
          )}

          {/* Flight cards */}
          {flights.map((f, i) => {
            const seg = f.itineraries[0]?.segments[0]
            const lastSeg = f.itineraries[0]?.segments[f.itineraries[0].segments.length-1]
            const stops = f.itineraries[0]?.segments.length - 1
            const dep = seg?.departure_time ? new Date(seg.departure_time).toLocaleTimeString('en-IN',{hour:'2-digit',minute:'2-digit',hour12:false}) : '--:--'
            const arr = lastSeg?.arrival_time ? new Date(lastSeg.arrival_time).toLocaleTimeString('en-IN',{hour:'2-digit',minute:'2-digit',hour12:false}) : '--:--'
            const dur = formatDuration(f.itineraries[0]?.duration || '')
            const rec = f.ai_insight?.recommendation
            const isFirst = i === 0

            return (
              <div key={f.id} className="flight-card"
                style={{ animation:`fadeUp .4s ${i*.06}s ease both`, borderColor: isFirst?'var(--black)':undefined }}
                onClick={()=> {
                  if (typeof window !== 'undefined') {
                    sessionStorage.setItem('selected_flight', JSON.stringify(f))
                    sessionStorage.setItem('search_params', JSON.stringify(form))
                  }
                  router.push('/booking')
                }}
              >
                {isFirst && <div className="best-tag">Best value</div>}
                <div className="flight-top" style={{ borderTop: isFirst?'2px solid var(--red)':undefined }}>

                  {/* Airline */}
                  <div className="flight-airline">
                    <div className="airline-logo-box">
                      {seg?.airline_code || f.validating_airlines?.[0] || '??'}
                    </div>
                    <div>
                      <div className="airline-name-txt">{seg?.airline_name || f.validating_airlines?.[0] || 'Airline'}</div>
                      <div className="airline-num-txt">{seg?.flight_number || '--'}</div>
                    </div>
                  </div>

                  {/* Timeline */}
                  <div className="flight-timeline">
                    <div>
                      <div className="t-time">{dep}</div>
                      <div className="t-iata">{seg?.origin || form.origin}</div>
                    </div>
                    <div className="t-mid">
                      <div className="t-dur">{dur}</div>
                      <div style={{ height:'1px', width:'100%', background:'var(--grey2)', position:'relative' }}>
                        <div style={{ position:'absolute', top:'50%', left:'50%', transform:'translate(-50%,-50%)', background:'white', padding:'0 5px', color:'var(--red)' }}>
                          <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M17.8 19.2L16 11l3.5-3.5C21 6 21 4 19.5 2.5S18 2 16.5 3.5L13 7 4.8 6.2c-.5-.1-.9.1-1.1.5L2 8.9c-.2.4-.1.9.2 1.2l4.6 4.1-1.5 6.4 2.8 2.8 5.3-3.2 4.1 4.6c.3.4.8.5 1.2.2l1.1-1.2c.4-.2.6-.6.5-1.1z"/></svg>
                        </div>
                      </div>
                      <div className={`t-stop ${stops===0?'direct':'one-stop'}`}>
                        {stops === 0 ? 'Non-stop' : `${stops} stop${stops>1?'s':''}`}
                      </div>
                    </div>
                    <div style={{ textAlign:'right' }}>
                      <div className="t-time">{arr}</div>
                      <div className="t-iata">{lastSeg?.destination || form.destination}</div>
                    </div>
                  </div>

                  {/* Price */}
                  <div className="flight-price-col">
                    <div>
                      <div className="f-price">₹{Math.round(f.price.total).toLocaleString('en-IN')}</div>
                      <div className="f-price-per">per person</div>
                      {f.seats_available && f.seats_available < 5 && (
                        <div className="f-seats">{f.seats_available} seats left</div>
                      )}
                    </div>
                    <button className="btn btn-primary" style={{ fontSize:'.78rem', padding:'9px 16px' }}>Select →</button>
                  </div>
                </div>

                {/* Bottom bar */}
                <div className="flight-bottom">
                  <div style={{ display:'flex', alignItems:'center', gap:'10px', flexWrap:'wrap' }}>
                    {rec && <span className={`badge ${recColor(rec)}`}>{recLabel(rec)}</span>}
                    {f.ai_insight?.reason && <span style={{ fontSize:'.75rem', color:'var(--grey4)' }}>{f.ai_insight.reason}</span>}
                    <Link href="/predict" onClick={e=>e.stopPropagation()} style={{ fontSize:'.75rem', color:'var(--red)', textDecoration:'underline', textUnderlineOffset:'2px' }}>
                      30-day forecast →
                    </Link>
                  </div>
                  <span style={{ fontSize:'.72rem', color:'var(--grey3)', fontFamily:'var(--fm)' }}>
                    {form.cabin_class} · 15kg bag · 7kg cabin
                  </span>
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

export default function FlightsPage() {
  return <Suspense fallback={<div style={{paddingTop:'120px',textAlign:'center',color:'var(--grey3)'}}>Loading...</div>}><FlightsContent /></Suspense>
}
