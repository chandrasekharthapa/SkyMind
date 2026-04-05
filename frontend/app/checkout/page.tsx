"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import NavBar from "@/components/layout/NavBar";
import {
  createRazorpayOrder,
  verifyPayment,
} from "@/lib/api";
import type {
  Booking,
  CreateOrderResponse,
  VerifyPaymentResponse,
} from "@/types";

// Razorpay types
declare global {
  interface Window {
    Razorpay: new (options: RazorpayOptions) => RazorpayInstance;
  }
}

interface RazorpayOptions {
  key: string;
  amount: number;
  currency: string;
  order_id: string;
  name: string;
  description: string;
  handler: (response: RazorpayPaymentResponse) => void;
  prefill?: { name?: string; email?: string; contact?: string };
  theme?: { color?: string };
  modal?: { ondismiss?: () => void };
}

interface RazorpayInstance {
  open: () => void;
}

interface RazorpayPaymentResponse {
  razorpay_order_id: string;
  razorpay_payment_id: string;
  razorpay_signature: string;
}

// ─────────────────────────────────────────────────────────────────────
// Component
// ─────────────────────────────────────────────────────────────────────

export default function CheckoutPage() {
  const router = useRouter();
  const [booking, setBooking] = useState<Booking | null>(null);
  const [loading, setLoading] = useState(false);
  const [payError, setPayError] = useState("");

  useEffect(() => {
    if (typeof window !== "undefined") {
      const saved = sessionStorage.getItem("booking_data");
      if (saved) {
        try {
          setBooking(JSON.parse(saved) as Booking);
        } catch {
          /* malformed — ignore */
        }
      }
    }
  }, []);

  const price = booking?.total_price ?? 4299;
  const ref = booking?.booking_reference ?? "SKY26-DEMO";
  const passengerName =
    (booking?.flight_offer_data as any)?.passengers?.[0]?.first_name ??
    "Traveller";
  const passengerEmail = booking?.contact_email ?? "";
  const passengerPhone = booking?.contact_phone ?? "";

  // Route display
  let routeLabel = "DEL → BOM";
  try {
    const itin = (booking?.flight_offer_data as any)?.itineraries?.[0];
    const segs = itin?.segments ?? [];
    const first = segs[0];
    const last = segs[segs.length - 1];
    if (first && last) routeLabel = `${first.origin} → ${last.destination}`;
  } catch {
    /* keep default */
  }

  // ── Razorpay handler ───────────────────────────────────────────────
  const handlePay = async () => {
    setLoading(true);
    setPayError("");

    try {
      // 1. Create Razorpay order via backend
      const order: CreateOrderResponse = await createRazorpayOrder({
        amount: price,
        currency: booking?.currency ?? "INR",
        booking_id: booking?.id ?? "demo-id",
        booking_reference: ref,
      });

      const razorpayKey =
        process.env.NEXT_PUBLIC_RAZORPAY_KEY ?? "";

      if (
        razorpayKey &&
        typeof window !== "undefined" &&
        window.Razorpay
      ) {
        const rzp = new window.Razorpay({
          key: order.key ?? razorpayKey,
          amount: Math.round(price * 100), // paise
          currency: order.currency ?? "INR",
          order_id: order.order_id,
          name: "SkyMind Flights",
          description: `Booking ${ref}`,
          prefill: {
            name: passengerName,
            email: passengerEmail,
            contact: passengerPhone,
          },
          theme: { color: "#e8191a" },
          modal: {
            ondismiss: () => {
              setLoading(false);
            },
          },
          handler: async (response: RazorpayPaymentResponse) => {
            try {
              const verifyRes: VerifyPaymentResponse = await verifyPayment({
                razorpay_order_id: response.razorpay_order_id,
                razorpay_payment_id: response.razorpay_payment_id,
                razorpay_signature: response.razorpay_signature,
                booking_id: booking?.id ?? "demo-id",
              });

              if (typeof window !== "undefined") {
                sessionStorage.setItem(
                  "payment_data",
                  JSON.stringify({
                    ...response,
                    verified: verifyRes.success,
                  })
                );
              }

              router.push("/success");
            } catch (verifyErr) {
              // Even if verify call fails, navigate — payment happened
              console.error("Verify error:", verifyErr);
              router.push("/success");
            }
          },
        });

        rzp.open();
        // Note: setLoading(false) is handled inside handler / ondismiss
        return;
      }

      // No Razorpay SDK / no key → demo mode
      if (typeof window !== "undefined") {
        sessionStorage.setItem(
          "payment_data",
          JSON.stringify({ demo: true, razorpay_payment_id: `pay_demo_${Date.now()}` })
        );
      }
      router.push("/success");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Payment failed. Please try again.";
      setPayError(msg);
    } finally {
      setLoading(false);
    }
  };

  const base = Math.round(price * 0.85);
  const taxes = Math.round(price * 0.15);

  return (
    <div>
      {/* Razorpay SDK */}
      <script
        src="https://checkout.razorpay.com/v1/checkout.js"
        async
      />

      <NavBar />
      <div style={{ paddingTop: "60px" }}>

        {/* Sub-nav breadcrumb */}
        <div className="booking-subnav">
          <div className="wrap">
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "12px" }}>
              <button
                onClick={() => router.push("/booking")}
                style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: ".78rem", color: "var(--grey4)", background: "none", border: "none", cursor: "pointer", fontFamily: "var(--fb)", fontWeight: 500 }}
              >
                <svg width="13" height="13" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                  <path d="M15 18l-6-6 6-6" />
                </svg>
                Back
              </button>
              <div className="steps">
                <div className="step done">
                  <div className="step-num">✓</div>Passenger details
                </div>
                <div className="step-sep" />
                <div className="step active">
                  <div className="step-num">2</div>Payment
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="wrap">
          <div className="booking-body">
            <div className="booking-layout">

              {/* Left — payment info */}
              <div>
                <div className="form-block">
                  <div className="form-block-head">
                    <div className="form-block-num" style={{ background: "var(--black)", color: "#fff", borderColor: "var(--black)" }}>
                      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                        <rect x="1" y="4" width="22" height="16" rx="2" /><line x1="1" y1="10" x2="23" y2="10" />
                      </svg>
                    </div>
                    <div className="form-block-title">Secure payment via Razorpay</div>
                  </div>
                  <div className="form-block-body">

                    {/* Gateway badge */}
                    <div style={{ display: "flex", alignItems: "center", gap: "12px", padding: "14px 16px", background: "var(--off)", border: "1px solid var(--grey1)", marginBottom: "16px" }}>
                      <div style={{ width: "44px", height: "44px", background: "#2563eb", display: "flex", alignItems: "center", justifyContent: "center", fontSize: ".65rem", fontWeight: 800, color: "#fff", fontFamily: "var(--fm)", flexShrink: 0 }}>
                        rzp
                      </div>
                      <div>
                        <div style={{ fontWeight: 600, fontSize: ".9rem", color: "var(--black)" }}>Razorpay Payment Gateway</div>
                        <div style={{ fontSize: ".75rem", color: "var(--grey3)", marginTop: "2px" }}>UPI · Cards · Netbanking · Wallets</div>
                      </div>
                    </div>

                    {/* Trust badges */}
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px", marginBottom: "14px" }}>
                      {[{ label: "256-bit SSL", sub: "Encrypted" }, { label: "PCI-DSS", sub: "Compliant" }].map((b) => (
                        <div key={b.label} style={{ padding: "10px 14px", background: "var(--off)", border: "1px solid var(--grey1)", display: "flex", alignItems: "center", gap: "8px" }}>
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#166534" strokeWidth="2">
                            <rect x="3" y="11" width="18" height="11" rx="2" /><path d="M7 11V7a5 5 0 0110 0v4" />
                          </svg>
                          <div>
                            <div style={{ fontSize: ".7rem", fontWeight: 700, color: "#166534", letterSpacing: ".06em", textTransform: "uppercase" }}>{b.label}</div>
                            <div style={{ fontSize: ".65rem", color: "var(--grey3)" }}>{b.sub}</div>
                          </div>
                        </div>
                      ))}
                    </div>

                    {/* Test-mode note */}
                    <div className="test-note">
                      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#854d0e" strokeWidth="2" style={{ flexShrink: 0, marginTop: "1px" }}>
                        <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
                        <line x1="12" y1="9" x2="12" y2="13" /><line x1="12" y1="17" x2="12.01" y2="17" />
                      </svg>
                      <span>
                        <strong>Test mode active.</strong> Use card 4111 1111 1111 1111 · Any CVV · Any future expiry.
                      </span>
                    </div>

                    {/* Error */}
                    {payError && (
                      <div style={{ marginTop: "12px", padding: "10px 14px", background: "rgba(232,25,26,.07)", border: "1px solid var(--red)", color: "var(--red)", fontSize: ".82rem" }}>
                        ⚠️ {payError}
                      </div>
                    )}
                  </div>
                </div>
              </div>

              {/* Right — price panel */}
              <div>
                <div className="price-panel">
                  <div className="price-panel-head">
                    <div className="price-panel-head-label">Order summary</div>
                  </div>
                  <div className="price-panel-body">

                    {/* Route pill */}
                    <div style={{ display: "flex", alignItems: "center", gap: "10px", padding: "12px 14px", background: "rgba(232,25,26,.06)", border: "1px solid var(--red-rim)", marginBottom: "14px" }}>
                      <svg width="14" height="14" fill="none" stroke="var(--red)" strokeWidth="2" viewBox="0 0 24 24">
                        <path d="M17.8 19.2L16 11l3.5-3.5C21 6 21 4 19.5 2.5S18 2 16.5 3.5L13 7 4.8 6.2c-.5-.1-.9.1-1.1.5L2 8.9c-.2.4-.1.9.2 1.2l4.6 4.1-1.5 6.4 2.8 2.8 5.3-3.2 4.1 4.6c.3.4.8.5 1.2.2l1.1-1.2c.4-.2.6-.6.5-1.1z" />
                      </svg>
                      <div>
                        <div style={{ fontSize: ".68rem", color: "var(--red)", fontFamily: "var(--fm)", letterSpacing: ".06em", textTransform: "uppercase" }}>Ref: {ref}</div>
                        <div style={{ fontSize: ".8rem", fontWeight: 600, color: "var(--black)" }}>{routeLabel}</div>
                      </div>
                    </div>

                    <div className="price-row">
                      <span className="price-row-label">Flight fare</span>
                      <span className="price-row-val">₹{base.toLocaleString("en-IN")}</span>
                    </div>
                    <div className="price-row" style={{ borderBottom: "none" }}>
                      <span className="price-row-label">Taxes &amp; fees</span>
                      <span className="price-row-val">₹{taxes.toLocaleString("en-IN")}</span>
                    </div>

                    <div className="price-total-row">
                      <span className="price-total-label">Total</span>
                      <span className="price-total-val">₹{Math.round(price).toLocaleString("en-IN")}</span>
                    </div>

                    <button
                      className="pay-btn"
                      onClick={handlePay}
                      disabled={loading}
                    >
                      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <rect x="3" y="11" width="18" height="11" rx="2" /><path d="M7 11V7a5 5 0 0110 0v4" />
                      </svg>
                      {loading
                        ? "PROCESSING…"
                        : `PAY ₹${Math.round(price).toLocaleString("en-IN")}`}
                    </button>
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
