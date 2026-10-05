import type { Metadata } from "next";
// Fonts are bundled with the app instead of loaded from Google Fonts, so the
// page doesn't wait on (or break without) a third-party stylesheet.
import "@fontsource/bebas-neue/400.css";
import "@fontsource/dm-serif-display/400.css";
import "@fontsource/dm-serif-display/400-italic.css";
import "@fontsource/instrument-sans/400.css";
import "@fontsource/instrument-sans/500.css";
import "@fontsource/instrument-sans/600.css";
import "@fontsource/instrument-sans/700.css";
import "@fontsource/instrument-sans/400-italic.css";
import "@fontsource/martian-mono/300.css";
import "@fontsource/martian-mono/400.css";
import "@fontsource/martian-mono/500.css";
import "@fontsource/martian-mono/700.css";
import "./globals.css";
import { Toaster } from "sonner";
import QueryProvider from "@/components/providers/QueryProvider";
import { ThemeProvider } from "@/context/ThemeContext";
import Chatbot from "@/components/Chat/Chatbot";

export const metadata: Metadata = {
  metadataBase: new URL("https://skymind.app"),
  title: "SkyMind - AI Flight Intelligence",
  description:
    "Search domestic flights in India, see how fares have moved, and get a forecast of whether to book now or wait.",
  openGraph: {
    title: "SkyMind - AI Flight Intelligence",
    description:
      "Domestic flight fares across India, tracked daily, with a forecast of where they are heading.",
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
          <Chatbot />
        </ThemeProvider>
      </body>
    </html>
  );
}
