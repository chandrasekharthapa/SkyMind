'use client'
import { useState, useEffect } from 'react'
import Link from 'next/link'
import NavBar from '@/components/layout/NavBar'

export default function SuccessPage() {
  const [booking,  setBooking]  = useState<any>(null)
  const [payment,  setPayment]  = useState<any>(null)

  useEffect(() => {
    if (typeof window !== 'undefined') {
      const b = sessionStorage.getItem('booking_data')
      const p = sessionStorage.getItem('payment_data')
      if (b) setBooking(JSON.parse(b))
      if (p) setPayment(JSON.parse(p))
    }
  }, [])

  const ref   = booking?.booking_reference || 'SKY25J4R2X'
  const price = booking?.total_price ? `₹${Math.round(booking.total_price).toLocaleString('en-IN')}` : '₹4,299'
  const route = booking?.origin_code && booking?.destination_code ? `${booking.origin_code} → ${booking.destination_code}` : 'DEL → BOM'

  return (
    <div>
      <NavBar />
      <div style={{ paddingTop:'60px' }}>
        <div className="wrap">
          <div className="success-wrap">
            <div className="success-icon a1">
              <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.5"><polyline points="20 6 9 17 4 12"/></svg>
            </div>
            <h1 className="success-title">BOOKING<br/>CONFIRMED</h1>
            <p className="success-sub">Your flight has been booked and confirmed. A detailed itinerary has been sent to your email.</p>

            <div className="booking-detail">
              <div className="bd-row"><span className="bd-label">Booking reference</span><span className="bd-val" style={{ color:'var(--red)' }}>{ref}</span></div>
              <div className="bd-row"><span className="bd-label">Payment ID</span><span className="bd-val">{payment?.razorpay_payment_id || 'pay_demo_' + Date.now().toString(36)}</span></div>
              <div className="bd-row"><span className="bd-label">Amount paid</span><span className="bd-val" style={{ color:'#166534' }}>{price}</span></div>
              <div className="bd-row"><span className="bd-label">Route</span><span className="bd-val">{route}</span></div>
              <div className="bd-row" style={{ borderBottom:'none' }}><span className="bd-label">Status</span><span className="bd-val" style={{ color:'#166534' }}>Confirmed ✓</span></div>
            </div>

            <div className="success-btns">
              <Link href="/dashboard" className="btn btn-primary">View my trips →</Link>
              <Link href="/" className="btn btn-outline">Back to home</Link>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
