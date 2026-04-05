import type { Metadata } from "next";
import "./globals.css";
import { Toaster } from "sonner";
import QueryProvider from "@/components/providers/QueryProvider";

export const metadata: Metadata = {
  metadataBase: new URL("https://skymind.app"),
  title: "SkyMind — AI Flight Intelligence",
  description: "ML-powered flight price prediction, hidden route discovery, and seamless booking for Indian and international flights.",
  openGraph: {
    title: "SkyMind — AI Flight Intelligence",
    description: "Book smarter with AI-powered price forecasts and hidden route discovery.",
    type: "website",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=DM+Serif+Display:ital@0;1&family=Instrument+Sans:ital,wght@0,400;0,500;0,600;0,700;1,400&family=Martian+Mono:wght@300;400;500;700&display=swap" rel="stylesheet" />
      </head>
      <body>
        <QueryProvider>{children}</QueryProvider>
        <Toaster
          theme="light"
          position="top-right"
          toastOptions={{
            style: {
              background: "#fff",
              border: "1px solid #d8d6d2",
              color: "#131210",
              fontFamily: "'Instrument Sans',sans-serif",
              fontSize: ".875rem",
            },
          }}
        />
      </body>
    </html>
  );
}
