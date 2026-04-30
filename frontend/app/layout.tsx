import type { Metadata } from "next";
import "./globals.css";
import { Toaster } from "sonner";
import QueryProvider from "@/components/providers/QueryProvider";
import { ThemeProvider } from "@/context/ThemeContext";

export const metadata: Metadata = {
  metadataBase: new URL("https://skymind.app"),
  title: "SkyMind - AI Flight Intelligence",
  description:
    "ML-powered flight price prediction, hidden route discovery, and seamless booking for Indian and international flights.",
  openGraph: {
    title: "SkyMind - AI Flight Intelligence",
    description:
      "Book smarter with AI-powered price forecasts and hidden route discovery.",
    type: "website",
    images: [
      {
        url: "/og-image.png",
        width: 1200,
        height: 630,
        alt: "SkyMind - AI Flight Intelligence",
      },
    ],
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link
          rel="preconnect"
          href="https://fonts.gstatic.com"
          crossOrigin="anonymous"
        />
        <link
          href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=DM+Serif+Display:ital@0;1&family=Instrument+Sans:ital,wght@0,400;0,500;0,600;0,700;1,400&family=Martian+Mono:wght@300;400;500;700&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="font-sans antialiased" suppressHydrationWarning>
        <ThemeProvider>
          <QueryProvider>{children}</QueryProvider>
          <Toaster
            position="top-right"
            toastOptions={{
              style: {
                background: "var(--card-bg)",
                border: "1px solid var(--border-color)",
                color: "var(--text-main)",
                fontFamily: "'Instrument Sans',sans-serif",
                fontSize: ".875rem",
              },
            }}
          />
        </ThemeProvider>
      </body>
    </html>
  );
}
