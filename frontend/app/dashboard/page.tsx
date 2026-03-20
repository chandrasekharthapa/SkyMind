'use client'
import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import NavBar from '@/components/layout/NavBar'
import { supabase } from '@/lib/supabase'

export default function DashboardPage() {
  const router = useRouter()
  const [bookings,  setBookings]  = useState<any[]>([])
  const [alerts,    setAlerts]    = useState<any[]>([])
  const [loading,   setLoading]   = useState(true)

  useEffect(() => {
    const load = async () => {
      setLoading(true)
      try {
        const [{ data: bk }, { data: al }] = await Promise.all([
          supabase.from('bookings').select('*').order('created_at',{ascending:false}).limit(10),
          supabase.from('price_alerts').select('*').eq('is_active',true).limit(5),
        ])
        setBookings(bk || [])
        setAlerts(al || [])
      } catch(e) {}
      setLoading(false)
    }
    load()
  }, [])

  const PLANE = <svg width="12" height="12" viewBox="0 0 24 24" fill="var(--red)"><path d="M17.8 19.2L16 11l3.5-3.5C21 6 21 4 19.5 2.5S18 2 16.5 3.5L13 7 4.8 6.2c-.5-.1-.9.1-1.1.5L2 8.9c-.2.4-.1.9.2 1.2l4.6 4.1-1.5 6.4 2.8 2.8 5.3-3.2 4.1 4.6c.3.4.8.5 1.2.2l1.1-1.2c.4-.2.6-.6.5-1.1z"/></svg>

  const statusClass = (s:string) => s==='CONFIRMED'?'badge-green':s==='PENDING'?'badge-amber':'badge-off'

  // Fallback demo data if DB empty
  const displayBookings = bookings.length ? bookings : [
    { id:'1', booking_reference:'SKY25J4R2X', status:'CONFIRMED', origin_code:'DEL', destination_code:'DXB', contact_email:'rohan@gmail.com', total_price:28450, created_at:new Date().toISOString() },
    { id:'2', booking_reference:'SKY25K1M7P', status:'PENDING',   origin_code:'BOM', destination_code:'LHR', contact_email:'rohan@gmail.com', total_price:52300, created_at:new Date().toISOString() },
  ]
  const displayAlerts = alerts.length ? alerts : [
    { id:'1', origin_code:'DEL', destination_code:'DXB', departure_date:'2025-05-15', target_price:26000, last_price:24100, is_triggered:true },
    { id:'2', origin_code:'BOM', destination_code:'SIN', departure_date:'2025-07-10', target_price:18000, last_price:22400, is_triggered:false },
  ]

  return (
    <div>
      <NavBar />
      <div style={{ paddingTop:'60px' }}>
        <div className="dash-header">
          <div className="wrap">
            <div className="dash-title-row">
              <div>
                <div style={{ fontFamily:'var(--fm)', fontSize:'.65rem', fontWeight:500, letterSpacing:'.14em', textTransform:'uppercase', color:'var(--grey3)', marginBottom:'10px' }}>Dashboard · My Account</div>
                <div className="dash-title">WELCOME<br/>BACK,<em>Traveller.</em></div>
                <div className="dash-tier">
                  <span className="tier-badge gold">Gold Member</span>
                  <span className="points">12,840 pts</span>
                </div>
              </div>
              <Link href="/flights" className="btn btn-primary">+ New booking</Link>
            </div>
          </div>
        </div>

        <div className="wrap">
          <div style={{ marginTop:'28px' }}>
            <div className="dash-stats">
              {[
                { icon:<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M17.8 19.2L16 11l3.5-3.5C21 6 21 4 19.5 2.5S18 2 16.5 3.5L13 7 4.8 6.2c-.5-.1-.9.1-1.1.5L2 8.9c-.2.4-.1.9.2 1.2l4.6 4.1-1.5 6.4 2.8 2.8 5.3-3.2 4.1 4.6c.3.4.8.5 1.2.2l1.1-1.2c.4-.2.6-.6.5-1.1z"/></svg>, val: String(displayBookings.length), label:'Total flights' },
                { icon:<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6"/></svg>, val:`₹${(displayBookings.reduce((a,b)=>a+(b.total_price||0),0)/1000).toFixed(1)}k`, label:'Total spent' },
                { icon:<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 01-3.46 0"/></svg>, val: String(displayAlerts.length), label:'Active alerts' },
                { icon:<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="8" r="6"/><path d="M15.477 12.89L17 22l-5-3-5 3 1.523-9.11"/></svg>, val:'12.8K', label:'Points' },
              ].map(s => (
                <div key={s.label} className="dash-stat">
                  <div className="ds-icon">{s.icon}</div>
                  <div className="ds-val">{s.val}</div>
                  <div className="ds-label">{s.label}</div>
                </div>
              ))}
            </div>
          </div>

          <div className="dash-content">
            <div className="dash-grid">
              <div>
                <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:'14px' }}>
                  <h2 style={{ fontFamily:'var(--fd)', fontSize:'1.3rem', letterSpacing:'.04em', color:'var(--black)' }}>MY TRIPS</h2>
                  <span style={{ fontSize:'.75rem', color:'var(--grey3)', fontFamily:'var(--fm)' }}>{displayBookings.length} bookings</span>
                </div>

                {loading && [0,1].map(i=>(
                  <div key={i} className="booking-card" style={{ padding:'16px', marginBottom:'10px' }}>
                    <div className="skel" style={{ height:'14px', width:'40%', marginBottom:'10px' }}/>
                    <div className="skel" style={{ height:'40px', marginBottom:'10px' }}/>
                    <div className="skel" style={{ height:'14px', width:'70%' }}/>
                  </div>
                ))}

                {!loading && displayBookings.map((b,i) => (
                  <div key={b.id} className="booking-card" style={{ borderColor:i===0?'var(--black)':undefined }} onClick={()=>router.push('/booking')}>
                    <div className="bk-head">
                      <div style={{ display:'flex', alignItems:'center', gap:'10px' }}>
                        <span className="bk-ref">{b.booking_reference}</span>
                        <span className={`badge ${statusClass(b.status)}`}>{b.status}</span>
                      </div>
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--grey3)" strokeWidth="2"><path d="M9 18l6-6-6-6"/></svg>
                    </div>
                    <div className="bk-body">
                      <div className="bk-route">
                        <div><div className="bk-airport">{b.origin_code||'DEL'}</div></div>
                        <div className="fline" style={{ flex:1, margin:'0 12px' }}>
                          <div className="fline-dot"/><div className="fline-track" style={{ flex:1 }}><div className="fline-plane">{PLANE}</div></div><div className="fline-dot"/>
                        </div>
                        <div style={{ textAlign:'right' }}><div className="bk-airport">{b.destination_code||'BOM'}</div></div>
                      </div>
                      <div className="bk-foot">
                        <span style={{ color:'var(--grey3)', fontFamily:'var(--fm)', fontSize:'.72rem' }}>{b.created_at ? new Date(b.created_at).toLocaleDateString('en-IN') : '--'}</span>
                        <span style={{ fontFamily:'var(--fd)', fontSize:'1.1rem', letterSpacing:'.03em' }}>₹{Math.round(b.total_price||0).toLocaleString('en-IN')}</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>

              <div>
                <div className="sidebar-card">
                  <div className="sidebar-head">
                    <span className="sidebar-title">Price Alerts</span>
                    <span className="badge badge-red">{displayAlerts.length} active</span>
                  </div>
                  {displayAlerts.map(a => (
                    <div key={a.id} className="alert-item">
                      <div className="alert-route">
                        {a.origin_code} <span style={{color:'var(--grey3)'}}>→</span> {a.destination_code}
                        <span style={{ marginLeft:'auto', width:'6px', height:'6px', borderRadius:'50%', background:a.is_triggered?'#22c55e':'#f59e0b', display:'inline-block', animation:'blink 2s infinite' }}/>
                      </div>
                      <div className="alert-date" style={{ fontFamily:'var(--fm)', fontSize:'.72rem', color:'var(--grey3)' }}>{a.departure_date}</div>
                      <div className="alert-prices">
                        <span>Target: <strong>₹{Math.round(a.target_price||0).toLocaleString('en-IN')}</strong></span>
                        {a.last_price && <span style={{ color:a.is_triggered?'#166534':'var(--grey3)' }}>Now: ₹{Math.round(a.last_price).toLocaleString('en-IN')}</span>}
                      </div>
                      {a.is_triggered && <div className="alert-hit">✓ Target reached — book now!</div>}
                    </div>
                  ))}
                  <div style={{ padding:'12px 16px' }}>
                    <Link href="/predict" className="btn btn-outline" style={{ width:'100%', justifyContent:'center', fontSize:'.78rem', padding:'9px' }}>+ Add alert</Link>
                  </div>
                </div>

                <div className="sidebar-card">
                  <div className="sidebar-head"><span className="sidebar-title">Quick Actions</span></div>
                  {[
                    { label:'Search flights',  href:'/flights',   icon:<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg> },
                    { label:'Price prediction',href:'/predict',   icon:<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg> },
                    { label:'Set price alert', href:'/predict',   icon:<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9"/></svg> },
                    { label:'Hidden routes',   href:'/predict',   icon:<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="5" cy="5" r="2"/><circle cx="19" cy="5" r="2"/><circle cx="19" cy="19" r="2"/><circle cx="5" cy="19" r="2"/><path d="M7 5h10M19 7v10M5 7v10M7 19h10"/></svg> },
                  ].map((q,i) => (
                    <Link key={q.label} href={q.href} className="qa-item" style={{ borderBottom:i<3?undefined:'none' }}>
                      <div className="qa-icon-box">{q.icon}</div>{q.label}
                    </Link>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
