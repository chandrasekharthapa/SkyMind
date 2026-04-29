"use client";

import { useState, useEffect, Suspense } from "react";
import { useRouter } from "next/navigation";
import NavBar from "@/components/layout/NavBar";
import { createBooking, formatDuration } from "@/lib/api";
import type { FlightOffer, Passenger } from "@/types";

function BookingContent() {
  const router = useRouter();
  const [flight, setFlight] = useState<FlightOffer | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [form, setForm] = useState({
    email: "", phone: "",
    first_name: "", last_name: "",
    dob: "", passport: "",
    meal: "VEG", baggage: "15",
  });

  useEffect(() => {
    if (typeof window !== "undefined") {
      const saved = sessionStorage.getItem("selected_flight");
      if (saved) {
        try { setFlight(JSON.parse(saved)); } catch { /* ignore */ }
      }
    }
  }, []);

  const itin = flight?.itineraries?.[0];
  const segments = itin?.segments ?? [];
  const seg = segments[0];
  const lastSeg = segments[segments.length - 1];
  const dur = formatDuration(itin?.duration || "");

  const dep = seg?.departure_time
    ? new Date(seg.departure_time).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: false })
    : "--:--";
  const arr = lastSeg?.arrival_time
    ? new Date(lastSeg.arrival_time).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: false })
    : "--:--";
  const price = flight ? Math.round(flight.price?.total || 0) : 0;
  const base = flight?.price?.base ? Math.round(flight.price.base) : Math.round(price * 0.85);
  const taxes = Math.max(0, price - base);

  const handleProceed = async () => {
    if (!form.email || !form.phone || !form.first_name || !form.last_name) {
      setError("Please fill in all required fields.");
      return;
    }

    setLoading(true);
    setError("");

    try {
      const passenger: Passenger = {
        type: "ADULT",
        first_name: form.first_name,
        last_name: form.last_name,
        date_of_birth: form.dob || null,
        passport_number: form.passport || null,
        meal_preference: form.meal,
        baggage_allowance: Number(form.baggage),
      };

      const booking = await createBooking({
        flight_offer_id: flight?.id || "demo",
        flight_data: flight as FlightOffer || ({} as FlightOffer),
        passengers: [passenger],
        contact_email: form.email,
        contact_phone: form.phone,
        cabin_class: "ECONOMY",
      });

      if (typeof window !== "undefined") {
        const fullBooking = {
          ...booking,
          id: booking.booking_id,
          flight_offer_data: flight,
          passengers: [passenger],
          contact_email: form.email,
          contact_phone: form.phone,
          currency: "INR"
        };
        sessionStorage.setItem("booking_data", JSON.stringify(fullBooking));
      }
      router.push("/checkout");
    } catch (e: any) {
      setError(e.message || "Booking service unavailable. Please try again.");
    }
    setLoading(false);
  };

  if (!flight) return <div className="ui-page" style={{ display: "flex", alignItems: "center", justifyContent: "center" }}><div className="ui-label">DATA_LOAD_ERROR...</div></div>;

  return (
    <div className="ui-page" style={{ background: "var(--off)" }}>
      <NavBar />
      
      <div className="booking-subnav">
        <div className="ui-wrap ui-flex-between">
          <button onClick={() => router.back()} className="ui-btn ui-btn-white" style={{ height: "40px", padding: "0 16px", borderRadius: "8px" }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><path d="M15 18l-6-6 6-6"/></svg>
            BACK
          </button>
          <div className="steps">
            <div className="step active"><span className="step-num">1</span> DETAILS</div>
            <div className="step-sep" />
            <div className="step"><span className="step-num">2</span> PAYMENT</div>
          </div>
        </div>
      </div>

      <div className="ui-wrap" style={{ padding: "40px 0 100px" }}>
        <div className="booking-layout">
          
          <div style={{ display: "flex", flexDirection: "column", gap: "24px", flex: 1 }}>
            
            <div className="ui-card" style={{ padding: "clamp(20px, 5vw, 32px)" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "24px" }}>
                <div className="ui-label" style={{ color: "var(--grey3)" }}>SELECTED ITINERARY</div>
                <div className="badge badge-off" style={{ background: "var(--off)", color: "var(--black)" }}>{seg?.flight_number}</div>
              </div>
              <div className="ui-itinerary-grid">
                <div>
                  <div className="ui-title-lg" style={{ fontSize: "2.8rem", lineHeight: 1 }}>{dep}</div>
                  <div className="ui-label" style={{ color: "var(--grey4)", marginTop: 6 }}>{seg?.origin}</div>
                </div>
                
                <div className="min-w-plane" style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 8, minWidth: "160px" }}>
                  <div className="ui-label" style={{ fontSize: "10px", opacity: 0.6, textAlign: "center" }}>{dur}</div>
                  <div style={{ position: "relative", width: "100%", height: "1px", background: "var(--grey2)", margin: "4px 0" }}>
                    <div style={{ position: "absolute", left: "50%", top: "50%", transform: "translate(-50%, -50%)", background: "var(--white)", padding: "0 12px", display: "flex", alignItems: "center", justifyContent: "center" }}>
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="var(--red)"><path d="M21,16V14L13,9V3.5A1.5,1.5 0 0,0 11.5,2A1.5,1.5 0 0,0 10,3.5V9L2,14V16L10,13.5V19L8,20.5V22L11.5,21L15,22V20.5L13,19V13.5L21,16Z"/></svg>
                    </div>
                  </div>
                  <div className="ui-label-red" style={{ fontSize: "9px", textAlign: "center", fontWeight: 700, letterSpacing: "0.05em" }}>NON-STOP</div>
                </div>

                <div style={{ textAlign: "right" }}>
                  <div className="ui-title-lg" style={{ fontSize: "2.8rem", lineHeight: 1 }}>{arr}</div>
                  <div className="ui-label" style={{ color: "var(--grey4)", marginTop: 6 }}>{lastSeg?.destination}</div>
                </div>
              </div>
            </div>

            {error && <div className="ui-card" style={{ background: "var(--red-mist)", borderColor: "var(--red)", padding: "16px", color: "var(--red)", fontSize: "0.85rem" }}>{error}</div>}

            <div className="ui-card" style={{ padding: "clamp(24px, 5vw, 32px)" }}>
              <h2 className="ui-title-md" style={{ marginBottom: "32px", fontSize: "2rem" }}>PASSENGER DETAILS</h2>
              <div className="ui-form-grid">
                <div className="input-group">
                  <label className="ui-field-label">First Name</label>
                  <input className="ui-input" placeholder="e.g. John" value={form.first_name} onChange={e=>setForm(f=>({...f,first_name:e.target.value}))}/>
                </div>
                <div className="input-group">
                  <label className="ui-field-label">Last Name</label>
                  <input className="ui-input" placeholder="e.g. Doe" value={form.last_name} onChange={e=>setForm(f=>({...f,last_name:e.target.value}))}/>
                </div>
                <div className="input-group">
                  <label className="ui-field-label">Email Address</label>
                  <input className="ui-input" type="email" placeholder="john@example.com" value={form.email} onChange={e=>setForm(f=>({...f,email:e.target.value}))}/>
                </div>
                <div className="input-group">
                  <label className="ui-field-label">Phone Number</label>
                  <input className="ui-input" placeholder="+91 XXXXX XXXXX" value={form.phone} onChange={e=>setForm(f=>({...f,phone:e.target.value}))}/>
                </div>
              </div>
            </div>

            <div className="ui-card" style={{ padding: "clamp(24px, 5vw, 32px)" }}>
              <h2 className="ui-title-md" style={{ marginBottom: "32px", fontSize: "2rem" }}>TRAVEL PREFERENCES</h2>
              <div className="ui-form-grid">
                <div className="input-group">
                  <label className="ui-field-label">Meal Preference</label>
                  <select className="ui-input" value={form.meal} onChange={e=>setForm(f=>({...f,meal:e.target.value}))}>
                    <option value="VEG">Vegetarian</option>
                    <option value="NON_VEG">Non-Vegetarian</option>
                    <option value="VEGAN">Vegan</option>
                  </select>
                </div>
                <div className="input-group">
                  <label className="ui-field-label">Baggage Allowance</label>
                  <select className="ui-input" value={form.baggage} onChange={e=>setForm(f=>({...f,baggage:e.target.value}))}>
                    <option value="15">15 KG (INCLUDED)</option>
                    <option value="25">25 KG (+ ₹1,200)</option>
                  </select>
                </div>
              </div>
            </div>
          </div>

          <div className="price-panel">
            <div className="price-panel-head">
              <div className="price-panel-head-label">FARE SUMMARY</div>
            </div>
            <div className="price-panel-body" style={{ padding: "32px" }}>
              <div className="price-row" style={{ marginBottom: "20px" }}>
                <span className="price-row-label">Base Fare</span>
                <span className="price-row-val" style={{ fontSize: "0.9rem" }}>₹{base.toLocaleString("en-IN")}</span>
              </div>
              <div className="price-row" style={{ marginBottom: "32px" }}>
                <span className="price-row-label">Taxes & Fees</span>
                <span className="price-row-val" style={{ fontSize: "0.9rem" }}>₹{taxes.toLocaleString("en-IN")}</span>
              </div>
              
              <div className="price-total-row" style={{ borderTop: "1px solid rgba(255,255,255,0.1)", paddingTop: "24px", marginBottom: "32px" }}>
                <span className="price-total-label" style={{ fontSize: "1.2rem" }}>TOTAL</span>
                <span className="price-total-val" style={{ fontSize: "3.5rem" }}>₹{price.toLocaleString("en-IN")}</span>
              </div>

              <button className="pay-btn" onClick={handleProceed} disabled={loading} style={{ height: "64px", fontSize: "1rem" }}>
                {loading ? "PROCESSING..." : "PROCEED TO PAYMENT"}
              </button>
              
              <div style={{ marginTop: "24px", fontSize: "10px", color: "rgba(255,255,255,0.3)", textAlign: "center", lineHeight: 1.6, fontFamily: "var(--fm)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                Secure SSL Encrypted Payment <br/> Authorized by SkyMind Reserve
              </div>
            </div>
          </div>

        </div>
      </div>
    </div>
  );
}

export default function BookingPage() {
  return <Suspense fallback={null}><BookingContent /></Suspense>;
}
