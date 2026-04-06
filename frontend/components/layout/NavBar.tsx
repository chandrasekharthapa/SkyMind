"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { supabase } from "@/lib/supabase";

// ─── Air India Official "AI" Logomark (SVG inline) ────────────────────
// Using the official red swan/Centaur inspired minimal mark
function AirIndiaLogoMark({ size = 36 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 36 36" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect width="36" height="36" rx="4" fill="#E11D48" />
      <text
        x="18"
        y="24"
        textAnchor="middle"
        fill="white"
        fontSize="13"
        fontWeight="800"
        fontFamily="'Plus Jakarta Sans', sans-serif"
        letterSpacing="-0.5"
      >
        AI
      </text>
    </svg>
  );
}

// ─── SVG Icons (no emojis) ────────────────────────────────────────────
const PlaneIcon = ({ size = 16, className = "" }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
    <path d="M17.8 19.2L16 11l3.5-3.5C21 6 21 4 19.5 2.5S18 2 16.5 3.5L13 7 4.8 6.2c-.5-.1-.9.1-1.1.5L2 8.9c-.2.4-.1.9.2 1.2l4.6 4.1-1.5 6.4 2.8 2.8 5.3-3.2 4.1 4.6c.3.4.8.5 1.2.2l1.1-1.2c.4-.2.6-.6.5-1.1z" />
  </svg>
);

const ChevronRight = ({ size = 12 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
    <path d="M9 18l6-6-6-6" />
  </svg>
);

const MenuIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
    <line x1="3" y1="6" x2="21" y2="6" />
    <line x1="3" y1="12" x2="21" y2="12" />
    <line x1="3" y1="18" x2="21" y2="18" />
  </svg>
);

const XIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
    <line x1="18" y1="6" x2="6" y2="18" />
    <line x1="6" y1="6" x2="18" y2="18" />
  </svg>
);

export default function NavBar() {
  const [scrolled, setScrolled] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [user, setUser] = useState<any>(null);
  const [userLoading, setUserLoading] = useState(true);
  const pathname = usePathname();
  const router = useRouter();

  useEffect(() => {
    const fn = () => setScrolled(window.scrollY > 4);
    window.addEventListener("scroll", fn, { passive: true });
    return () => window.removeEventListener("scroll", fn);
  }, []);

  useEffect(() => { setMobileOpen(false); }, [pathname]);

  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => {
      setUser(session?.user ?? null);
      setUserLoading(false);
    });
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_e, session) => {
      setUser(session?.user ?? null);
    });
    return () => subscription.unsubscribe();
  }, []);

  const handleSignOut = async () => {
    await supabase.auth.signOut();
    router.push("/");
  };

  const navLinks = [
    { href: "/",          label: "Home" },
    { href: "/flights",   label: "Search" },
    { href: "/predict",   label: "AI Predict" },
    { href: "/dashboard", label: "Dashboard" },
  ];

  const isActive = (href: string) =>
    href === "/" ? pathname === "/" : pathname.startsWith(href);

  const userInitial =
    user?.email?.[0]?.toUpperCase() ||
    user?.user_metadata?.full_name?.[0]?.toUpperCase() ||
    "?";

  return (
    <>
      <nav
        style={{
          position: "fixed",
          top: 0, left: 0, right: 0,
          zIndex: 200,
          background: "#FFFFFF",
          borderBottom: `1px solid ${scrolled ? "#E2E8F0" : "#E2E8F0"}`,
          height: "60px",
          display: "flex",
          alignItems: "stretch",
          boxShadow: scrolled ? "0 1px 8px rgba(30,41,59,0.06)" : "none",
          transition: "box-shadow 200ms ease",
        }}
      >
        <div
          style={{
            width: "100%",
            maxWidth: "1200px",
            margin: "0 auto",
            padding: "0 32px",
            display: "flex",
            alignItems: "stretch",
          }}
        >
          {/* ── Logo ─────────────────────────────────────────────── */}
          <Link
            href="/"
            style={{
              display: "flex",
              alignItems: "center",
              gap: "10px",
              paddingRight: "24px",
              borderRight: "1px solid #E2E8F0",
              textDecoration: "none",
              flexShrink: 0,
            }}
          >
            {/* Air India plane silhouette + brand mark */}
            <div style={{ width: "32px", height: "32px", background: "#E11D48", borderRadius: "6px", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
              <PlaneIcon size={16} className="" />
            </div>
            <span
              style={{
                fontFamily: "'Plus Jakarta Sans', sans-serif",
                fontWeight: 800,
                fontSize: "1.15rem",
                letterSpacing: "-0.04em",
                color: "#1E293B",
                lineHeight: 1,
              }}
            >
              SKY<em style={{ color: "#E11D48", fontStyle: "normal" }}>MIND</em>
            </span>
          </Link>

          {/* ── Desktop Nav Links ─────────────────────────────────── */}
          <div
            className="nav-links-desktop"
            style={{ alignItems: "stretch", flex: 1 }}
          >
            {navLinks.map((l) => {
              const active = isActive(l.href);
              return (
                <Link
                  key={l.href}
                  href={l.href}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    padding: "0 18px",
                    fontSize: "13px",
                    fontWeight: 600,
                    letterSpacing: "-0.01em",
                    color: active ? "#1E293B" : "#64748B",
                    textDecoration: "none",
                    borderRight: "1px solid #F1F5F9",
                    position: "relative",
                    transition: "color 120ms ease, background 120ms ease",
                    whiteSpace: "nowrap",
                    fontFamily: "'Plus Jakarta Sans', sans-serif",
                  }}
                  onMouseEnter={(e) => {
                    if (!active) {
                      e.currentTarget.style.color = "#1E293B";
                      e.currentTarget.style.background = "#F8FAFC";
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (!active) {
                      e.currentTarget.style.color = "#64748B";
                      e.currentTarget.style.background = "transparent";
                    }
                  }}
                >
                  {l.label}
                  {/* Active underline */}
                  {active && (
                    <span
                      style={{
                        position: "absolute",
                        bottom: 0,
                        left: "18px",
                        right: "18px",
                        height: "2px",
                        background: "#E11D48",
                        borderRadius: "2px 2px 0 0",
                      }}
                    />
                  )}
                </Link>
              );
            })}
          </div>

          {/* ── Right Side ────────────────────────────────────────── */}
          <div
            className="nav-links-desktop"
            style={{ alignItems: "center", marginLeft: "auto", borderLeft: "1px solid #F1F5F9" }}
          >
            {/* Live fares indicator */}
            <div style={{ padding: "0 16px", borderRight: "1px solid #F1F5F9" }}>
              <div className="live-pill">
                <div className="live-dot" />
                Live Fares
              </div>
            </div>

            {/* Auth */}
            {!userLoading && (
              user ? (
                <div style={{ display: "flex", alignItems: "stretch" }}>
                  <Link
                    href="/dashboard"
                    style={{
                      padding: "0 16px",
                      height: "100%",
                      display: "flex",
                      alignItems: "center",
                      gap: "8px",
                      textDecoration: "none",
                      fontSize: "13px",
                      fontWeight: 600,
                      color: "#1E293B",
                      borderRight: "1px solid #F1F5F9",
                      transition: "background 120ms",
                      fontFamily: "'Plus Jakarta Sans', sans-serif",
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.background = "#F8FAFC")}
                    onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
                  >
                    <div style={{ width: "26px", height: "26px", borderRadius: "50%", background: "#E11D48", color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "11px", fontWeight: 700, flexShrink: 0, fontFamily: "'Plus Jakarta Sans', sans-serif" }}>
                      {userInitial}
                    </div>
                    My Account
                  </Link>
                  <button
                    onClick={handleSignOut}
                    style={{ padding: "0 16px", height: "100%", background: "none", border: "none", cursor: "pointer", fontSize: "13px", fontWeight: 500, color: "#64748B", borderRight: "1px solid #F1F5F9", fontFamily: "'Plus Jakarta Sans', sans-serif", transition: "color 120ms" }}
                    onMouseEnter={(e) => (e.currentTarget.style.color = "#E11D48")}
                    onMouseLeave={(e) => (e.currentTarget.style.color = "#64748B")}
                  >
                    Sign Out
                  </button>
                </div>
              ) : (
                <Link
                  href="/auth"
                  style={{ padding: "0 16px", height: "100%", display: "flex", alignItems: "center", textDecoration: "none", fontSize: "13px", fontWeight: 600, color: "#1E293B", borderRight: "1px solid #F1F5F9", transition: "background 120ms", fontFamily: "'Plus Jakarta Sans', sans-serif" }}
                  onMouseEnter={(e) => (e.currentTarget.style.background = "#F8FAFC")}
                  onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
                >
                  Sign In
                </Link>
              )
            )}

            {/* Book Now CTA */}
            <Link
              href="/flights"
              style={{
                padding: "0 20px",
                height: "100%",
                background: "#E11D48",
                color: "#fff",
                display: "flex",
                alignItems: "center",
                gap: "6px",
                textDecoration: "none",
                fontSize: "13px",
                fontWeight: 700,
                fontFamily: "'Plus Jakarta Sans', sans-serif",
                transition: "background 120ms",
                whiteSpace: "nowrap",
                letterSpacing: "-0.01em",
              }}
              onMouseEnter={(e) => (e.currentTarget.style.background = "#BE123C")}
              onMouseLeave={(e) => (e.currentTarget.style.background = "#E11D48")}
            >
              Book now
              <ChevronRight size={12} />
            </Link>
          </div>

          {/* ── Mobile Hamburger ─────────────────────────────────── */}
          <div
            className="nav-mobile-menu"
            style={{ marginLeft: "auto", alignItems: "center", gap: "12px", display: "none" }}
          >
            <div className="live-pill" style={{ display: "flex" }}>
              <div className="live-dot" />
            </div>
            <button
              onClick={() => setMobileOpen((o) => !o)}
              style={{ background: "none", border: "none", cursor: "pointer", padding: "8px", color: "#1E293B", display: "flex", alignItems: "center" }}
              aria-label="Toggle menu"
            >
              {mobileOpen ? <XIcon /> : <MenuIcon />}
            </button>
          </div>
        </div>
      </nav>

      {/* ── Mobile Dropdown ──────────────────────────────────────── */}
      {mobileOpen && (
        <div
          style={{
            position: "fixed",
            top: "60px",
            left: 0,
            right: 0,
            zIndex: 199,
            background: "#FFFFFF",
            borderBottom: "1px solid #E2E8F0",
            boxShadow: "0 8px 24px rgba(30,41,59,0.10)",
          }}
        >
          {navLinks.map((l) => {
            const active = isActive(l.href);
            return (
              <Link
                key={l.href}
                href={l.href}
                style={{
                  display: "block",
                  padding: "16px 24px",
                  fontSize: "15px",
                  fontWeight: active ? 700 : 500,
                  color: active ? "#1E293B" : "#64748B",
                  textDecoration: "none",
                  borderBottom: "1px solid #F1F5F9",
                  background: active ? "#F8FAFC" : "transparent",
                  borderLeft: active ? "3px solid #E11D48" : "3px solid transparent",
                  fontFamily: "'Plus Jakarta Sans', sans-serif",
                }}
              >
                {l.label}
              </Link>
            );
          })}
          {user ? (
            <>
              <Link href="/dashboard" style={{ display: "block", padding: "16px 24px", fontSize: "15px", color: "#64748B", textDecoration: "none", borderBottom: "1px solid #F1F5F9", fontFamily: "'Plus Jakarta Sans', sans-serif" }}>
                My Dashboard
              </Link>
              <button onClick={handleSignOut} style={{ display: "block", width: "100%", textAlign: "left", padding: "16px 24px", fontSize: "15px", color: "#E11D48", background: "none", border: "none", borderBottom: "1px solid #F1F5F9", cursor: "pointer", fontFamily: "'Plus Jakarta Sans', sans-serif" }}>
                Sign Out
              </button>
            </>
          ) : (
            <Link href="/auth" style={{ display: "block", padding: "16px 24px", fontSize: "15px", color: "#64748B", textDecoration: "none", borderBottom: "1px solid #F1F5F9", fontFamily: "'Plus Jakarta Sans', sans-serif" }}>
              Sign In
            </Link>
          )}
          <Link href="/flights" style={{ display: "block", padding: "16px 24px", margin: "12px 16px", background: "#E11D48", color: "#fff", textAlign: "center", textDecoration: "none", fontSize: "14px", fontWeight: 700, borderRadius: "8px", fontFamily: "'Plus Jakarta Sans', sans-serif" }}>
            Book now
          </Link>
        </div>
      )}

      {/* Spacer */}
      <div style={{ height: "60px" }} />
    </>
  );
}
