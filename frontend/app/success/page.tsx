"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import NavBar from "@/components/layout/NavBar";

export default function SuccessPage() {
  const [booking, setBooking] = useState<any>(null);
  const [payment, setPayment] = useState<any>(null);

  useEffect(() => {
    if (typeof window !== "undefined") {
      const b = sessionStorage.getItem("booking_data");
      const p = sessionStorage.getItem("payment_data");
      if (b) { try { setBooking(JSON.parse(b)); } catch { /* ignore */ } }
      if (p) { try { setPayment(JSON.parse(p)); } catch { /* ignore */ } }
    }
  }, []);

  const ref = booking?.booking_reference || "SKY-DEMO-123";
  const price = booking?.total_price
    ? `INR ${Math.round(booking.total_price).toLocaleString("en-IN")}`
    : "INR 0";

  let route = "DEL to BOM";
  try {
    const fd = booking?.flight_offer_data || booking?.flight_data || {};
    const segs = fd?.itineraries?.[0]?.segments || [];
    if (segs.length > 0) {
      const first = segs[0];
      const last = segs[segs.length - 1];
      route = `${first?.origin || first?.departure?.iataCode || "DEL"} to ${last?.destination || last?.arrival?.iataCode || "BOM"}`;
    }
  } catch { /* keep default */ }

  const paymentId = payment?.razorpay_payment_id || `pay_v2_${Date.now().toString(36)}`;

  return (
    <div style={{ background:"var(--off)", minHeight:"100vh" }}>
      <NavBar />
      <div style={{ paddingTop: 100, paddingBottom: 100 }}>
        <div className="wrap">
          <div style={{ maxWidth:540, margin:"0 auto", textAlign:"center" }}>
            
            {/* Cinematic Icon */}
            <div style={{ 
              width:80, height:80, background:"var(--red)", borderRadius:"50%", 
              display:"flex", alignItems:"center", justifyContent:"center", 
              margin:"0 auto 32px", boxShadow:"0 12px 32px var(--red-mist)",
              animation:"fadeUp 0.6s cubic-bezier(0.4, 0, 0.2, 1) both"
            }}>
              <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="3">
                <polyline points="20 6 9 17 4 12" />
              </svg>
            </div>

            <h1 style={{ fontFamily:"var(--fd)", fontSize:"4rem", lineHeight:.9, marginBottom:16, animation:"fadeUp 0.6s 0.1s both" }}>
              TICKET<br/><span style={{ color:"var(--red)" }}>SECURED.</span>
            </h1>
            
            <p style={{ color:"var(--grey4)", fontSize:"1rem", lineHeight:1.6, marginBottom:40, animation:"fadeUp 0.6s 0.2s both" }}>
              Your journey with SkyMind has been confirmed. A digital itinerary and boarding instructions have been sent to your registered email.
            </p>

            {/* Boarding Pass Style Card */}
            <div style={{ 
              background:"var(--white)", borderRadius:24, overflow:"hidden", 
              boxShadow:"var(--shadow-lg)", border:"1px solid var(--grey1)",
              textAlign:"left", animation:"fadeUp 0.6s 0.3s both"
            }}>
              <div style={{ background:"var(--black)", padding:"20px 32px", display:"flex", justifyContent:"space-between", alignItems:"center" }}>
                <span className="label" style={{ color:"rgba(255,255,255,.4)" }}>CONFIRMATION PASS</span>
                <span style={{ fontFamily:"var(--fm)", fontSize:".7rem", color:"var(--red)", fontWeight:700 }}>SKY-INTEL v4</span>
              </div>
              
              <div style={{ padding:32 }}>
                <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:32 }}>
                  <div>
                    <div className="label" style={{ color:"var(--grey3)", marginBottom:8 }}>REFERENCE</div>
                    <div style={{ fontFamily:"var(--fd)", fontSize:"1.8rem", color:"var(--red)" }}>{ref}</div>
                  </div>
                  <div>
                    <div className="label" style={{ color:"var(--grey3)", marginBottom:8 }}>STATUS</div>
                    <div style={{ fontFamily:"var(--fd)", fontSize:"1.8rem", color:"var(--green)" }}>VERIFIED</div>
                  </div>
                </div>

                <div style={{ marginTop:32, paddingTop:32, borderTop:"1px dashed var(--grey2)", display:"grid", gridTemplateColumns:"1fr 1fr", gap:32 }}>
                  <div>
                    <div className="label" style={{ color:"var(--grey3)", marginBottom:6 }}>ROUTE</div>
                    <div style={{ fontWeight:700, fontSize:".95rem" }}>{route}</div>
                  </div>
                  <div>
                    <div className="label" style={{ color:"var(--grey3)", marginBottom:6 }}>AMOUNT PAID</div>
                    <div style={{ fontWeight:700, fontSize:".95rem" }}>{price}</div>
                  </div>
                </div>
                
                <div style={{ marginTop:24 }}>
                  <div className="label" style={{ color:"var(--grey3)", marginBottom:6 }}>PAYMENT ID</div>
                  <div style={{ fontFamily:"var(--fm)", fontSize:".65rem", color:"var(--grey4)" }}>{paymentId}</div>
                </div>
              </div>
              
              {/* Barcode-ish footer */}
              <div style={{ background:"var(--off)", padding:24, borderTop:"1px solid var(--grey1)", display:"flex", justifyContent:"center" }}>
                <div style={{ height:32, width:"100%", background:"repeating-linear-gradient(90deg, #131210, #131210 2px, transparent 2px, transparent 4px)", opacity:.2 }} />
              </div>
            </div>

            <div style={{ marginTop:48, display:"flex", gap:16, justifyContent:"center", animation:"fadeUp 0.6s 0.4s both" }}>
              <Link href="/dashboard" className="btn-red-full" style={{ padding:"14px 32px" }}>VIEW MY TRIPS</Link>
              <Link href="/" className="btn-outline" style={{ padding:"14px 32px" }}>GO HOME</Link>
            </div>

          </div>
        </div>
      </div>
    </div>
  );
}
