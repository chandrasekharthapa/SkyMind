'use client'
import { useState, useEffect, Suspense } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import NavBar from '@/components/layout/NavBar'
import { createBooking, createRazorpayOrder, formatDuration } from '@/lib/api'
import type { FlightOffer } from '@/lib/api'

function BookingContent() {
  const router = useRouter()
  const [flight, setFlight]   = useState<FlightOffer|null>(null)
  const [loading, setLoading] = useState(false)
  const [form, setForm] = useState({
    email:'rohan@gmail.com', phone:'+91 98765 43210',
    first_name:'Rohan', last_name:'Kumar',
    dob:'1995-03-14', passport:'P1234567',
    meal:'Standard', baggage:'15',
  })

  useEffect(() => {
    if (typeof window !== 'undefined') {
      const saved = sessionStorage.getItem('selected_flight')
      if (saved) setFlight(JSON.parse(saved))
    }
  }, [])

  const seg      = flight?.itineraries[0]?.segments[0]
  const lastSeg  = flight?.itineraries[0]?.segments[flight?.itineraries[0].segments.length-1]
  const dur      = formatDuration(flight?.itineraries[0]?.duration || '')
  const dep      = seg?.departure_time ? new Date(seg.departure_time).toLocaleTimeString('en-IN',{hour:'2-digit',minute:'2-digit',hour12:false}) : '06:30'
  const arr      = lastSeg?.arrival_time ? new Date(lastSeg.arrival_time).toLocaleTimeString('en-IN',{hour:'2-digit',minute:'2-digit',hour12:false}) : '08:40'
  const price    = flight ? Math.round(flight.price.total) : 4299
  const base     = flight ? Math.round(flight.price.base) : 3540
  const taxes    = price - base

  const handleProceed = async () => {
    setLoading(true)
    try {
      const booking: any = await createBooking({
        flight_offer_id: flight?.id || 'demo',
        flight_data: flight as FlightOffer || {} as FlightOffer,
        passengers: [{ type:'ADULT', first_name:form.first_name, last_name:form.last_name, date_of_birth:form.dob, passport_number:form.passport, meal_preference:form.meal, baggage_allowance:Number(form.baggage) }],
        contact_email: form.email,
        contact_phone: form.phone,
        cabin_class: 'ECONOMY',
      })
      if (typeof window !== 'undefined') {
        sessionStorage.setItem('booking_data', JSON.stringify(booking.booking || booking))
      }
      router.push('/checkout')
    } catch(e:any) {
      // Still navigate — booking endpoint may not be wired to DB yet
      router.push('/checkout')
    }
    setLoading(false)
  }

  const PLANE = <svg width="12" height="12" viewBox="0 0 24 24" fill="var(--red)"><path d="M17.8 19.2L16 11l3.5-3.5C21 6 21 4 19.5 2.5S18 2 16.5 3.5L13 7 4.8 6.2c-.5-.1-.9.1-1.1.5L2 8.9c-.2.4-.1.9.2 1.2l4.6 4.1-1.5 6.4 2.8 2.8 5.3-3.2 4.1 4.6c.3.4.8.5 1.2.2l1.1-1.2c.4-.2.6-.6.5-1.1z"/></svg>

  return (
    <div>
      <NavBar />
      <div style={{ paddingTop:'60px' }}>
        <div className="booking-subnav">
          <div className="wrap">
            <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', flexWrap:'wrap', gap:'12px' }}>
              <button onClick={()=>router.push('/flights')} style={{ display:'flex', alignItems:'center', gap:'6px', fontSize:'.78rem', color:'var(--grey4)', background:'none', border:'none', cursor:'pointer', fontFamily:'var(--fb)', fontWeight:500 }}>
                <svg width="13" height="13" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path d="M15 18l-6-6 6-6"/></svg>
                Back to results
              </button>
              <div className="steps">
                <div className="step active"><div className="step-num">1</div>Passenger details</div>
                <div className="step-sep"/>
                <div className="step"><div className="step-num">2</div>Payment</div>
              </div>
            </div>
          </div>
        </div>

        <div className="wrap">
          <div className="booking-body">
            <div className="booking-layout">
              <div>
                {/* Flight summary */}
                <div className="fsummary" style={{ marginBottom:'14px' }}>
                  <div className="fsummary-head">
                    <span style={{ fontFamily:'var(--fm)', fontSize:'.68rem', fontWeight:600, letterSpacing:'.10em', textTransform:'uppercase', color:'var(--grey3)' }}>Your flight</span>
                    <span className="badge badge-green">Confirmed</span>
                  </div>
                  <div style={{ padding:'18px', display:'flex', alignItems:'center', gap:'14px' }}>
                    <div style={{ textAlign:'center' }}>
                      <div style={{ fontFamily:'var(--fd)', fontSize:'1.9rem', letterSpacing:'.02em' }}>{dep}</div>
                      <div style={{ fontFamily:'var(--fm)', fontSize:'.75rem', fontWeight:700, color:'var(--grey4)', marginTop:'3px' }}>{seg?.origin || 'DEL'}</div>
                    </div>
                    <div className="fline" style={{ flex:1 }}>
                      <div className="fline-dot"/>
                      <div className="fline-track" style={{ flex:1 }}>
                        <div style={{ position:'absolute', top:'50%', left:'50%', transform:'translate(-50%,-50%)', background:'white', padding:'0 4px', fontSize:'.7rem', color:'var(--grey3)', fontFamily:'var(--fm)', whiteSpace:'nowrap' }}>
                          {dur} · {seg?.flight_number||'6E-214'}
                        </div>
                      </div>
                      <div className="fline-dot"/>
                    </div>
                    <div style={{ textAlign:'right' }}>
                      <div style={{ fontFamily:'var(--fd)', fontSize:'1.9rem', letterSpacing:'.02em' }}>{arr}</div>
                      <div style={{ fontFamily:'var(--fm)', fontSize:'.75rem', fontWeight:700, color:'var(--grey4)', marginTop:'3px' }}>{lastSeg?.destination || 'BOM'}</div>
                    </div>
                  </div>
                </div>

                {/* Contact */}
                <div className="form-block">
                  <div className="form-block-head"><div className="form-block-num">A</div><div className="form-block-title">Contact details</div></div>
                  <div className="form-block-body">
                    <div className="form-2">
                      <div><label className="field-label">Email *</label><input className="inp" type="email" value={form.email} onChange={e=>setForm(f=>({...f,email:e.target.value}))}/></div>
                      <div><label className="field-label">Phone *</label><input className="inp" type="tel" value={form.phone} onChange={e=>setForm(f=>({...f,phone:e.target.value}))}/></div>
                    </div>
                  </div>
                </div>

                {/* Passenger */}
                <div className="form-block">
                  <div className="form-block-head"><div className="form-block-num">B</div><div className="form-block-title">Passenger 1 — Adult</div></div>
                  <div className="form-block-body">
                    <div className="form-2">
                      <div><label className="field-label">First name *</label><input className="inp" value={form.first_name} onChange={e=>setForm(f=>({...f,first_name:e.target.value}))}/></div>
                      <div><label className="field-label">Last name *</label><input className="inp" value={form.last_name} onChange={e=>setForm(f=>({...f,last_name:e.target.value}))}/></div>
                      <div><label className="field-label">Date of birth</label><input type="date" className="inp" value={form.dob} onChange={e=>setForm(f=>({...f,dob:e.target.value}))}/></div>
                      <div><label className="field-label">Passport number</label><input className="inp" value={form.passport} onChange={e=>setForm(f=>({...f,passport:e.target.value}))}/></div>
                      <div><label className="field-label">Meal preference</label>
                        <select className="inp" value={form.meal} onChange={e=>setForm(f=>({...f,meal:e.target.value}))}>
                          <option>Standard</option><option>Vegetarian</option><option>Vegan</option><option>Halal</option>
                        </select>
                      </div>
                      <div><label className="field-label">Baggage</label>
                        <select className="inp" value={form.baggage} onChange={e=>setForm(f=>({...f,baggage:e.target.value}))}>
                          <option value="15">15 kg (included)</option>
                          <option value="20">20 kg (+₹800)</option>
                          <option value="25">25 kg (+₹1,500)</option>
                        </select>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {/* Price panel */}
              <div>
                <div className="price-panel">
                  <div className="price-panel-head"><div className="price-panel-head-label">Price summary</div></div>
                  <div className="price-panel-body">
                    <div className="price-row"><span className="price-row-label">Base fare ×1</span><span className="price-row-val">₹{base.toLocaleString('en-IN')}</span></div>
                    <div className="price-row"><span className="price-row-label">Taxes & fees</span><span className="price-row-val">₹{taxes.toLocaleString('en-IN')}</span></div>
                    <div className="price-row" style={{ borderBottom:'none' }}><span className="price-row-label">Convenience</span><span className="price-row-val">₹0</span></div>
                    <div className="price-total-row"><span className="price-total-label">Total</span><span className="price-total-val">₹{price.toLocaleString('en-IN')}</span></div>
                    <div className="refund-note">
                      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ flexShrink:0,marginTop:'1px' }}><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
                      Free cancellation within 24 hours of booking.
                    </div>
                    <button className="pay-btn" onClick={handleProceed} disabled={loading}>
                      {loading ? 'SAVING...' : 'PROCEED TO PAYMENT'}
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M9 18l6-6-6-6"/></svg>
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default function BookingPage() {
  return <Suspense fallback={null}><BookingContent /></Suspense>
}
