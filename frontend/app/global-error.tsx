"use client";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html>
      <body style={{ padding: "80px 24px", textAlign: "center", fontFamily: "sans-serif" }}>
        <h2 style={{ fontSize: "1.5rem", marginBottom: 16 }}>System Error</h2>
        <p style={{ color: "#666", marginBottom: 24 }}>{error?.message || "Application encountered an error."}</p>
        <button
          onClick={() => reset()}
          style={{
            padding: "10px 20px",
            background: "#000",
            color: "#fff",
            border: "none",
            borderRadius: "8px",
            cursor: "pointer"
          }}
        >
          Reload Page
        </button>
      </body>
    </html>
  );
}
