// Booking and payment run against Razorpay's test mode. Say so wherever a
// person could otherwise think they are buying a real ticket.
export default function DemoNotice({ style }: { style?: React.CSSProperties }) {
  return (
    <div
      role="note"
      style={{
        display: "flex",
        gap: 12,
        alignItems: "flex-start",
        background: "#000",
        color: "#fff",
        borderRadius: 12,
        padding: "14px 18px",
        ...style,
      }}
    >
      <span
        aria-hidden="true"
        style={{ width: 8, height: 8, borderRadius: "50%", background: "var(--red)", marginTop: 6, flexShrink: 0 }}
      />
      <div>
        <div style={{ fontFamily: "var(--fm)", fontSize: "0.65rem", letterSpacing: "0.12em", textTransform: "uppercase", color: "rgba(255,255,255,0.6)", marginBottom: 4 }}>
          Demo booking
        </div>
        <div style={{ fontSize: "0.875rem", lineHeight: 1.5 }}>
          Payments here run in Razorpay test mode. No money is taken and no airline ticket is issued.
          Use a Razorpay test card or test UPI ID to try the flow.
        </div>
      </div>
    </div>
  );
}
