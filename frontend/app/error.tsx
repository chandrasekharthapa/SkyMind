"use client";

import { useEffect } from "react";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Next.js Error Boundary caught:", error);
  }, [error]);

  return (
    <div style={{ padding: "80px 24px", textAlign: "center", fontFamily: "sans-serif" }}>
      <h2 style={{ fontSize: "1.5rem", marginBottom: 16 }}>Something went wrong!</h2>
      <p style={{ color: "#666", marginBottom: 24 }}>{error.message || "An unexpected error occurred."}</p>
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
        Try again
      </button>
    </div>
  );
}
