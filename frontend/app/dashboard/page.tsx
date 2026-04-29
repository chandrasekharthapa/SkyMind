"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import NavBar from "@/components/layout/NavBar";

const PlaneIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M17.8 19.2L16 11l3.5-3.5C21 6 21 4 19.5 2.5S18 2 16.5 3.5L13 7 4.8 6.2c-.5-.1-.9.1-1.1.5L2 8.9c-.2.4-.1.9.2 1.2l4.6 4.1-1.5 6.4 2.8 2.8 5.3-3.2 4.1 4.6c.3.4.8.5 1.2.2l1.1-1.2c.4-.2.6-.6.5-1.1z"/>
  </svg>
);

const WalletIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6"/>
  </svg>
);

const BellIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 01-3.46 0"/>
  </svg>
);

const TrophyIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <circle cx="12" cy="8" r="6"/><path d="M15.477 12.89L17 22l-5-3-5 3 1.523-9.11"/>
  </svg>
);



export default function DashboardPage() {
  const router = useRouter();
  const [user, setUser] = useState<any>(null);
  const [profile, setProfile] = useState<any>(null);
  const [bookings, setBookings] = useState<any[]>([]);
  const [alerts, setAlerts] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { supabase } = await import("@/lib/supabase");
      const { data:{ session } } = await supabase.auth.getSession();
      
      if (session?.user) {
        setUser(session.user);
        const { data: prof } = await supabase.from("profiles").select("*").eq("id", session.user.id).single();
        setProfile(prof);

        const [bkRes, alRes] = await Promise.all([
          supabase.from("bookings").select("*").eq("user_id", session.user.id).order("created_at",{ascending:false}).limit(10),
          supabase.from("price_alerts").select("*").eq("user_id", session.user.id).eq("is_active",true).limit(5),
        ]);
        setBookings(!bkRes.error && bkRes.data ? bkRes.data : []);
        setAlerts(!alRes.error && alRes.data ? alRes.data : []);
      } else {
        setBookings([]); 
        setAlerts([]);
      }
    } catch {
      setBookings([]); setAlerts([]);
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const statusClass = (s:string) => s==="CONFIRMED"?"badge-green":s==="PENDING"?"badge-amber":"badge-off";
  const totalSpent = bookings.reduce((a,b)=>a+(b.total_price||0),0);
  const confirmedTrips = bookings.filter(b=>b.status==="CONFIRMED").length;

  return (
    <div style={{ background: "var(--off)", minHeight: "100vh" }}>
      <NavBar />
      <div style={{ paddingTop: 60 }}>

        {/* Header */}
        <div className="dash-head" style={{ background: "var(--white)", borderBottom: "1px solid var(--grey1)", padding: "60px 0 100px 0" }}>
          <div className="ui-wrap">
            <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", flexWrap: "wrap", gap: 32 }}>
              <div>
                <div style={{ fontFamily: "var(--fm)", fontSize: ".65rem", fontWeight: 600, letterSpacing: ".14em", textTransform: "uppercase", color: "var(--grey3)", marginBottom: 12 }}>
                  User Dashboard / Account
                </div>
                <h1 className="dash-title" style={{ fontFamily: "var(--fd)", fontSize: "clamp(2.8rem, 6vw, 4.5rem)", lineHeight: 0.9, textTransform: "uppercase" }}>
                  WELCOME<br />BACK, <em style={{ fontStyle: "normal", color: "var(--red)" }}>
                    {(profile?.display_name || user?.user_metadata?.full_name || user?.email?.split("@")[0] || user?.phone || "OPERATOR").split(" ")[0].toUpperCase()}.
                  </em>
                </h1>
                <div style={{ marginTop: 24, display: "flex", alignItems: "center", gap: 12 }}>
                  <span className="badge badge-black" style={{ padding: "6px 12px", background: "var(--black)", color: "#fff" }}>Gold Tier</span>
                  <span style={{ fontSize: "12px", fontWeight: 700, fontFamily: "var(--fm)", color: "var(--grey4)" }}>
                    {confirmedTrips * 1200} SkyMind Points
                  </span>
                </div>
              </div>
              <Link href="/flights" className="ui-btn ui-btn-red" style={{ padding: "16px 32px", fontSize: "0.95rem" }}>+ Plan New Trip</Link>
            </div>
          </div>
        </div>

        <div className="ui-wrap" style={{ paddingBottom: 80 }}>
          {/* Stats Grid */}
          <div style={{ marginTop: -50, position: "relative", zIndex: 10 }}>
            <div className="dash-stats-grid ui-glass">
              {[
                { icon: <PlaneIcon />, val: String(bookings.length), label: "Total Bookings" },
                { icon: <WalletIcon />, val: `₹${(totalSpent / 1000).toFixed(1)}k`, label: "Total Spent" },
                { icon: <BellIcon />, val: String(alerts.length), label: "Active Alerts" },
                { icon: <TrophyIcon />, val: String(confirmedTrips * 1200), label: "SkyPoints" },
              ].map((s, idx) => (
                <div key={s.label} className="dash-stat-item">
                  <div className="stat-icon">{s.icon}</div>
                  <div className="stat-val">{s.val}</div>
                  <div className="stat-label">{s.label}</div>
                </div>
              ))}
            </div>
          </div>

          <div className="dash-content" style={{ marginTop: 40 }}>
            <div className="dash-grid" style={{ display: "grid", gridTemplateColumns: "1fr 340px", gap: 32 }}>

              {/* Bookings Section */}
              <div>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20 }}>
                  <h2 style={{ fontFamily: "var(--fd)", fontSize: "2rem", letterSpacing: "0.04em" }}>YOUR ITINERARIES</h2>
                  <div style={{ height: 1, flex: 1, background: "var(--grey1)", margin: "0 20px" }} />
                  <span style={{ fontSize: "12px", color: "var(--grey3)", fontFamily: "var(--fm)" }}>{bookings.length} Items</span>
                </div>

                {loading ? (
                   <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                     {[0, 1].map(i => (
                       <div key={i} className="skel" style={{ height: 160, borderRadius: 12 }} />
                     ))}
                   </div>
                ) : bookings.length === 0 ? (
                  <div style={{ padding: 80, textAlign: "center", background: "var(--white)", borderRadius: 20, border: "1px dashed var(--grey2)", boxShadow: "var(--shadow-sm)" }}>
                    <div style={{ color:"var(--red)", marginBottom:20, display: "flex", justifyContent: "center", opacity: 0.5 }}>
                      <PlaneIcon />
                    </div>
                    <div style={{ fontSize: "1.5rem", fontFamily: "var(--fd)", color: "var(--black)", marginBottom: 12, textTransform: "uppercase", letterSpacing: "0.05em" }}>No active itineraries</div>
                    <div style={{ fontSize: "14px", color: "var(--grey3)", marginBottom: 32, maxWidth: 300, margin: "0 auto 32px" }}>You haven't booked any flights yet. Use our AI to find the perfect fare.</div>
                    <Link href="/flights" className="ui-btn ui-btn-red" style={{ padding: "14px 40px" }}>Search Flights</Link>
                  </div>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
                    {bookings.map((b) => (
                      <div key={b.id} className="booking-card" style={{ 
                        background: "var(--white)",
                        borderRadius: 16,
                        overflow: "hidden",
                        border: "1px solid var(--grey1)",
                        boxShadow: "var(--shadow-sm)",
                        transition: "transform 0.2s, box-shadow 0.2s"
                      }}>
                        <div className="booking-card-head" style={{ 
                          padding: "16px 24px", 
                          borderBottom: "1px solid var(--grey1)", 
                          display: "flex", 
                          justifyContent: "space-between", 
                          alignItems: "center", 
                          background: "linear-gradient(to right, var(--off), var(--white))" 
                        }}>
                          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                            <div style={{ width: 32, height: 32, borderRadius: 8, background: "var(--black)", display: "flex", alignItems: "center", justifyContent: "center", color: "#fff", fontSize: "10px", fontFamily: "var(--fm)" }}>
                              {(b.origin_code || "??").substring(0,2)}
                            </div>
                            <div>
                              <div style={{ fontFamily: "var(--fm)", fontSize: "11px", fontWeight: 700, color: "var(--black)" }}>{b.booking_reference}</div>
                              <div style={{ fontSize: "10px", color: "var(--grey3)", fontFamily: "var(--fm)" }}>
                                Booked on {b.created_at ? new Date(b.created_at).toLocaleDateString("en-IN", { day:'numeric', month:'short', year:'numeric' }) : "--"}
                              </div>
                            </div>
                          </div>
                          <span className={`badge ${statusClass(b.status)}`} style={{ borderRadius: 6, fontSize: "10px", padding: "4px 10px" }}>{b.status}</span>
                        </div>
                        
                        <div className="booking-card-body" style={{ padding: "32px 24px" }}>
                          <div className="itinerary-row" style={{ display: "flex", alignItems: "center", gap: 32 }}>
                            <div style={{ minWidth: 80 }}>
                              <div style={{ fontFamily: "var(--fd)", fontSize: "2.8rem", lineHeight: 1, letterSpacing: "-0.02em" }}>{b.origin_code || "???"}</div>
                              <div style={{ fontSize: "11px", color: "var(--grey3)", marginTop: 6, fontFamily: "var(--fm)", letterSpacing: "0.05em" }}>ORIGIN</div>
                            </div>
                            
                            <div style={{ flex: 1, display: "flex", alignItems: "center", position: "relative", padding: "0 10px" }}>
                              <div style={{ flex: 1, height: 1, borderTop: "2px dashed var(--grey2)", position: "relative", display: "flex", alignItems: "center", justifyContent: "center" }}>
                                <div style={{ 
                                  width: 36, height: 36, background: "var(--white)", border: "1px solid var(--grey2)", 
                                  borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center",
                                  boxShadow: "var(--shadow-sm)", color: "var(--red)", transform: "rotate(90deg)"
                                }}>
                                  <PlaneIcon />
                                </div>
                              </div>
                            </div>
                            
                            <div style={{ minWidth: 80, textAlign: "right" }}>
                              <div style={{ fontFamily: "var(--fd)", fontSize: "2.8rem", lineHeight: 1, letterSpacing: "-0.02em" }}>{b.destination_code || "???"}</div>
                              <div style={{ fontSize: "11px", color: "var(--grey3)", marginTop: 6, fontFamily: "var(--fm)", letterSpacing: "0.05em" }}>DESTINATION</div>
                            </div>
                          </div>
                          
                          <div className="itinerary-footer" style={{ 
                            display: "grid", 
                            gridTemplateColumns: "1fr auto", 
                            alignItems: "center", 
                            marginTop: 32, 
                            paddingTop: 24, 
                            borderTop: "1px solid var(--grey1)" 
                          }}>
                            <div style={{ display: "flex", gap: 32, flexWrap: "wrap" }}>
                              <div>
                                <div style={{ fontSize: "10px", color: "var(--grey3)", fontWeight: 700, marginBottom: 4, letterSpacing: "0.05em" }}>PAYMENT METHOD</div>
                                <div style={{ fontSize: "12px", fontWeight: 600 }}>Razorpay / UPI</div>
                              </div>
                              <div>
                                <div style={{ fontSize: "10px", color: "var(--grey3)", fontWeight: 700, marginBottom: 4, letterSpacing: "0.05em" }}>PASSENGERS</div>
                                <div style={{ fontSize: "12px", fontWeight: 600 }}>1 Adult, 0 Children</div>
                              </div>
                            </div>
                            <div style={{ textAlign: "right" }}>
                              <div style={{ fontSize: "11px", color: "var(--grey4)", fontWeight: 700, marginBottom: 4 }}>TOTAL PAID</div>
                              <div style={{ fontFamily: "var(--fd)", fontSize: "2rem", color: "var(--black)", lineHeight: 1 }}>₹{Math.round(b.total_price || 0).toLocaleString("en-IN")}</div>
                            </div>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Sidebar Section */}
              <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
                {/* Price Alerts Card */}
                <div className="sidebar-card" style={{ padding: 0 }}>
                  <div style={{ padding: "16px 20px", borderBottom: "1px solid var(--grey1)", background: "var(--black)", color: "#fff", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span style={{ fontFamily: "var(--fm)", fontSize: "10px", fontWeight: 700, letterSpacing: "0.1em" }}>PRICE ALERTS</span>
                    <span className="badge" style={{ background: "var(--red)", color: "#fff" }}>{alerts.length} ACTIVE</span>
                  </div>
                  <div style={{ padding: "8px 0" }}>
                    {alerts.length === 0 && !loading && (
                      <div style={{ padding: 32, textAlign: "center", background: "var(--off)" }}>
                        <div style={{ color:"var(--grey2)", marginBottom:12, display: "flex", justifyContent: "center" }}><BellIcon /></div>
                        <div style={{ fontSize: "14px", fontFamily: "var(--fb)", fontWeight: 600, color: "var(--black)", marginBottom: 4 }}>NO ALERTS SET</div>
                        <div style={{ fontSize: "12px", color: "var(--grey3)" }}>Track routes to get notified.</div>
                      </div>
                    )}
                    {alerts.map(a => (
                      <div key={a.id} style={{ padding: "16px 20px", borderBottom: "1px solid var(--grey1)" }}>
                        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
                          <div style={{ fontWeight: 700, fontSize: "14px" }}>{a.origin_code}  {a.destination_code}</div>
                          <div style={{ width: 8, height: 8, borderRadius: "50%", background: a.triggered_count > 0 ? "var(--green)" : "#f59e0b" }} />
                        </div>
                        <div style={{ fontSize: "11px", color: "var(--grey3)", marginBottom: 12, fontFamily: "var(--fm)" }}>DEPARTURE: {a.departure_date}</div>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                          <div>
                            <div style={{ fontSize: "10px", color: "var(--grey3)", marginBottom: 2 }}>TARGET</div>
                            <div style={{ fontWeight: 700 }}>{Math.round(a.target_price).toLocaleString("en-IN")}</div>
                          </div>
                          <div style={{ textAlign: "right" }}>
                            <div style={{ fontSize: "10px", color: "var(--grey3)", marginBottom: 2 }}>CURRENT</div>
                            <div style={{ fontWeight: 700, color: a.triggered_count > 0 ? "var(--green)" : "var(--black)" }}>{Math.round(a.last_price).toLocaleString("en-IN")}</div>
                          </div>
                        </div>
                        {a.triggered_count > 0 && (
                          <div style={{ marginTop: 12, padding: "8px", background: "#dcfce7", color: "#166534", fontSize: "11px", fontWeight: 700, textAlign: "center", borderRadius: 4 }}>
                            TARGET REACHED! BOOK NOW
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                  <div style={{ padding: "16px 20px" }}>
                    <Link href="/predict" className="ui-btn ui-btn-red" style={{ width: "100%", height: 42, fontSize: "11px", letterSpacing: "0.05em" }}>+ NEW ALERT</Link>
                  </div>
                </div>

                {/* Quick Actions Card */}
                <div className="sidebar-card" style={{ background: "var(--white)", borderRadius: 16, overflow: "hidden", border: "1px solid var(--grey1)", boxShadow: "var(--shadow-sm)" }}>
                  <div style={{ padding: "16px 20px", borderBottom: "1px solid var(--grey1)", background: "var(--off)" }}>
                    <span style={{ fontFamily: "var(--fm)", fontSize: "10px", fontWeight: 700, letterSpacing: "0.1em", color: "var(--grey3)" }}>QUICK ACTIONS</span>
                  </div>
                  <div style={{ display: "flex", flexDirection: "column" }}>
                    {[
                      { label: "Search Flights", href: "/flights", icon: <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg> },
                      { label: "AI Fare Prediction", href: "/predict", icon: <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg> },
                      { label: "Account Settings", href: "/dashboard", icon: <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg> },
                    ].map((q, i) => (
                      <Link key={q.label} href={q.href} style={{ 
                        display: "flex", alignItems: "center", gap: 12, padding: "16px 20px", 
                        borderBottom: i < 2 ? "1px solid var(--grey1)" : "none",
                        fontSize: "12px", color: "var(--black)", fontWeight: 600,
                        textDecoration: "none",
                        transition: "background 0.2s"
                      }}
                      onMouseEnter={e => (e.currentTarget.style.background = "var(--off)")}
                      onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
                      >
                        <div style={{ color: "var(--red)", display: "flex" }}>{q.icon}</div>
                        <span style={{ fontFamily: "var(--fb)" }}>{q.label}</span>
                      </Link>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

const styles = `
  .dash-stats-grid { 
    display: grid; 
    grid-template-columns: repeat(4, 1fr); 
    gap: 0; 
    background: var(--white);
    border: 1px solid var(--grey1); 
    box-shadow: var(--shadow-lg);
    border-radius: 20px;
    overflow: hidden;
  }
  .dash-stat-item {
    padding: 32px 24px;
    display: flex;
    flex-direction: column;
    gap: 12px;
    border-right: 1px solid var(--grey1);
    background: var(--white);
  }
  .dash-stat-item:last-child { border-right: none; }
  .stat-icon { color: var(--red); opacity: 0.8; }
  .stat-val { font-size: 32px; font-family: var(--fd); color: var(--black); letter-spacing: -0.02em; line-height: 1; }
  .stat-label { font-size: 11px; font-family: var(--fm); color: var(--grey3); text-transform: uppercase; letter-spacing: 0.12em; fontWeight: 700; }

  @media (max-width: 1024px) {
    .dash-grid { grid-template-columns: 1fr !important; }
  }

  @media (max-width: 768px) {
    .dash-head { padding: 40px 0 80px 0 !important; }
    .dash-title { font-size: 3.5rem !important; letter-spacing: -0.02em; }
    .dash-stats-grid { grid-template-columns: repeat(2, 1fr) !important; border-radius: 16px !important; }
    .dash-stat-item { padding: 24px 16px !important; gap: 8px !important; border-bottom: 1px solid var(--grey1); }
    .dash-stat-item:nth-child(even) { border-right: none !important; }
    .dash-stat-item:nth-last-child(-n+2) { border-bottom: none !important; }
    .stat-val { font-size: 28px !important; }
    .stat-label { font-size: 10px !important; }
    
    .booking-card-body { padding: 20px 16px !important; }
    .itinerary-row { gap: 12px !important; }
    .itinerary-row .ui-title-lg { font-size: 2.2rem !important; }
    .itinerary-footer { grid-template-columns: 1fr !important; gap: 20px; padding-top: 20px !important; }
  }

  @media (max-width: 480px) {
    .dash-title { font-size: 3rem !important; }
    .dash-stats-grid { grid-template-columns: 1fr !important; }
    .dash-stat-item { border-right: none !important; }
    .dash-stat-item:not(:last-child) { border-bottom: 1px solid var(--grey1) !important; }
  }
`;

if (typeof document !== 'undefined') {
  const styleTag = document.createElement('style');
  styleTag.textContent = styles;
  document.head.appendChild(styleTag);
}
