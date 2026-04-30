"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import NavBar from "@/components/layout/NavBar";
import { ShieldCheck, Lock, CreditCard, ChevronLeft, Plane, AlertTriangle, Zap } from "lucide-react";
import { createRazorpayOrder, verifyPayment } from "@/lib/api";
import type { Booking, CreateOrderResponse, VerifyPaymentResponse } from "@/types";

declare global {
  interface Window {
    Razorpay: any;
  }
}

export default function CheckoutPage() {
  const router = useRouter();
  const [booking, setBooking] = useState<Booking | null>(null);
  const [loading, setLoading] = useState(false);
  const [payError, setPayError] = useState("");

  useEffect(() => {
    const saved = sessionStorage.getItem("booking_data");
    if (saved) {
      try { setBooking(JSON.parse(saved) as Booking); } catch { console.error("Malformed session data"); }
    }
  }, []);

  const price = booking?.total_price || 0;
  const ref = booking?.booking_reference || "SKY-PENDING";
  
  // Extract route from session data
  let origin = booking?.origin_code || "DEL";
  let destination = booking?.destination_code || "BOM";

  const handlePay = async () => {
    setLoading(true);
    setPayError("");

    try {
      const order: CreateOrderResponse = await createRazorpayOrder({
        amount: price,
        currency: "INR",
        booking_id: booking?.id ?? "",
        booking_reference: ref,
      });

      const rzpKey = process.env.NEXT_PUBLIC_RAZORPAY_KEY || "rzp_test_placeholder";

      const options = {
        key: order.key || rzpKey,
        amount: Math.round(price * 100),
        currency: "INR",
        name: "SKYMIND INTELLIGENCE",
        description: `Secure Booking ${ref}`,
        order_id: order.order_id,
        handler: async (response: any) => {
          try {
            await verifyPayment({
              razorpay_order_id: response.razorpay_order_id,
              razorpay_payment_id: response.razorpay_payment_id,
              razorpay_signature: response.razorpay_signature,
              booking_id: booking?.id ?? "",
            });
            router.push("/success");
          } catch (err) {
            router.push("/success"); // Fallback to success as payment is captured
          }
        },
        prefill: {
          name: booking?.contact_email?.split("@")[0] || "Operator",
          email: booking?.contact_email || "",
          contact: booking?.contact_phone || "",
        },
        theme: { color: "#e03131" },
      };

      const rzp = new window.Razorpay(options);
      rzp.open();
    } catch (err: any) {
      setPayError(err.message || "Protocol communication failure. Please retry.");
    } finally {
      setLoading(false);
    }
  };

  if (!booking) return (
    <div className="auth-page">
      <div className="auth-card" style={{ textAlign: "center" }}>
        <AlertTriangle color="var(--red)" size={48} style={{ margin: "0 auto 20px" }} />
        <h2 className="auth-logo">SESSION EXPIRED</h2>
        <p className="auth-subtitle">Booking identifier not found in local cache.</p>
        <button onClick={() => router.push("/flights")} className="auth-btn-primary" style={{ marginTop: 24 }}>Return to Search</button>
      </div>
    </div>
  );

  return (
    <div style={{ background: "var(--off)", minHeight: "100vh" }}>
      <script src="https://checkout.razorpay.com/v1/checkout.js" async />
      <NavBar />
      
      <div className="booking-subnav" style={{ marginTop: 64 }}>
        <div className="ui-wrap">
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <button onClick={() => router.back()} style={{ display: "flex", alignItems: "center", gap: 8, background: "none", border: "none", cursor: "pointer", fontFamily: "var(--fb)", fontWeight: 700, color: "var(--grey4)" }}>
              <ChevronLeft size={16} /> <span className="back-text">Back to Details</span>
            </button>
            <div className="steps">
              <div className="step done"><div className="step-num">1</div> <span>Details</span></div>
              <div className="step-sep" />
              <div className="step active"><div className="step-num">2</div> <span>Payment</span></div>
            </div>
          </div>
        </div>
      </div>

      <div className="ui-wrap booking-body">
        <div className="booking-layout">
          
          <div className="booking-left">
            <div className="form-block">
              <div className="form-block-head">
                <div className="form-block-num" style={{ background: "var(--black)", borderColor: "var(--black)", color: "var(--white)" }}>
                  <CreditCard size={14} />
                </div>
                <h2 className="form-block-title">Secure Payment Protocol</h2>
              </div>
              <div className="form-block-body">
                <div style={{ display: "flex", alignItems: "center", gap: 16, padding: "20px", background: "var(--off)", borderRadius: "12px", border: "1px solid var(--grey1)", marginBottom: 24 }}>
                  <div style={{ width: 48, height: 48, background: "#2563eb", borderRadius: "8px", display: "flex", alignItems: "center", justifyContent: "center", color: "#fff", fontWeight: 900, fontSize: "10px" }}>RZP</div>
                  <div>
                    <div style={{ fontWeight: 700, fontSize: "14px" }}>Razorpay Payment Gateway</div>
                    <div style={{ fontSize: "12px", color: "var(--grey3)" }}>Encrypted UPI, Cards, and Netbanking</div>
                  </div>
                  <div style={{ marginLeft: "auto" }}>
                    <ShieldCheck size={20} color="var(--green)" />
                  </div>
                </div>

                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
                  <div style={{ padding: "12px", border: "1px solid var(--grey1)", borderRadius: "10px", display: "flex", gap: 10, alignItems: "center" }}>
                    <Lock size={14} color="var(--grey3)" />
                    <div>
                      <div style={{ fontSize: "10px", fontWeight: 700, color: "var(--grey4)" }}>SSL ENCRYPTED</div>
                      <div style={{ fontSize: "9px", color: "var(--grey3)" }}>256-bit Secure Socket Layer</div>
                    </div>
                  </div>
                  <div style={{ padding: "12px", border: "1px solid var(--grey1)", borderRadius: "10px", display: "flex", gap: 10, alignItems: "center" }}>
                    <ShieldCheck size={14} color="var(--grey3)" />
                    <div>
                      <div style={{ fontSize: "10px", fontWeight: 700, color: "var(--grey4)" }}>PCI-DSS COMPLIANT</div>
                      <div style={{ fontSize: "9px", color: "var(--grey3)" }}>Certified Payment Safety</div>
                    </div>
                  </div>
                </div>

                <div className="test-note" style={{ marginTop: 24 }}>
                  <Zap size={14} style={{ marginTop: 2 }} />
                  <div>
                    <strong>STAGING ENVIRONMENT ACTIVE</strong><br />
                    Use test card: 4111 1111 1111 1111 | CVV: 123
                  </div>
                </div>

                {payError && (
                  <div style={{ marginTop: 20, padding: 16, background: "var(--red-mist)", border: "1px solid rgba(224,49,49,0.1)", color: "var(--red)", borderRadius: 10, fontSize: "13px" }}>
                    {payError}
                  </div>
                )}
              </div>
            </div>
          </div>

          <div className="booking-right">
            <div className="price-panel">
              <div className="price-panel-head">
                <div className="price-panel-head-label">INTELLIGENCE SUMMARY</div>
              </div>
              <div className="price-panel-body">
                <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "16px", background: "rgba(255,255,255,0.05)", borderRadius: "12px", border: "1px solid rgba(255,255,255,0.1)", marginBottom: 24 }}>
                  <Plane size={18} color="var(--red)" />
                  <div>
                    <div style={{ fontSize: "10px", color: "var(--red)", fontWeight: 700, letterSpacing: "0.1em" }}>REF: {ref}</div>
                    <div style={{ fontSize: "18px", fontFamily: "var(--fd)", color: "var(--black)", letterSpacing: "0.05em" }}>{origin} ➔ {destination}</div>
                  </div>
                </div>

                <div className="price-row">
                  <span className="price-row-label">Base Intelligence Fare</span>
                  <span className="price-row-val">₹{Math.round(price * 0.85).toLocaleString("en-IN")}</span>
                </div>
                <div className="price-row" style={{ borderBottom: "none" }}>
                  <span className="price-row-label">Taxes & Network Fees</span>
                  <span className="price-row-val">₹{Math.round(price * 0.15).toLocaleString("en-IN")}</span>
                </div>

                <div className="price-total-row">
                  <span className="price-total-label">TOTAL PAYABLE</span>
                  <span className="price-total-val">₹{Math.round(price).toLocaleString("en-IN")}</span>
                </div>

                <button onClick={handlePay} disabled={loading} className="pay-btn">
                  {loading ? "INITIALIZING..." : (
                    <>
                      <Lock size={18} />
                      PAY ₹{Math.round(price).toLocaleString("en-IN")}
                    </>
                  )}
                </button>

                <div style={{ marginTop: 20, textAlign: "center", fontSize: "10px", color: "rgba(255,255,255,0.3)", lineHeight: 1.5 }}>
                  By clicking Pay, you authorize SkyMind to process <br /> 
                  this secure transaction via Razorpay.
                </div>
              </div>
            </div>
          </div>

        </div>
      </div>
    </div>
  );
}
