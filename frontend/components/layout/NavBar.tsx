"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { supabase } from "@/lib/supabase";

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

  const links = [
    { href: "/",         label: "Home" },
    { href: "/flights",  label: "Search" },
    { href: "/predict",  label: "AI Predict" },
    { href: "/dashboard",label: "Dashboard" },
  ];

  const isActive = (href: string) =>
    href === "/" ? pathname === "/" : pathname.startsWith(href);

  const userInitial =
    user?.email?.[0]?.toUpperCase() ||
    user?.user_metadata?.full_name?.[0]?.toUpperCase() ||
    "?";

  const PLANE = (
    <svg width="18" height="18" viewBox="0 0 20 20" fill="currentColor">
      <path d="M18 7L11 11L4 7L2.5 8.5L9.5 13L7.5 17.5L10.5 16.5L13.5 17.5L11.5 13L18.5 8.5L18 7Z" />
      <path d="M11 11L15.5 4.5L18 7L11 11Z" opacity=".55" />
    </svg>
  );

  return (
    <>
      <nav style={{
        position: "fixed", top: 0, left: 0, right: 0, zIndex: 200,
        background: "#ffffff", borderBottom: "1px solid #131210",
        height: "60px", display: "flex", alignItems: "stretch",
        boxShadow: scrolled ? "0 2px 12px rgba(19,18,16,.08)" : "none",
        transition: "box-shadow .2s",
      }}>
        <div style={{ width: "100%", maxWidth: "1160px", margin: "0 auto", padding: "0 20px", display: "flex", alignItems: "stretch" }}>

          {/* Logo */}
          <Link href="/" style={{ display: "flex", alignItems: "center", gap: "10px", paddingRight: "24px", borderRight: "1px solid #131210", textDecoration: "none", flexShrink: 0 }}>
            <div style={{ width: "32px", height: "32px", background: "#131210", display: "flex", alignItems: "center", justifyContent: "center", color: "#fff", flexShrink: 0 }}>
              {PLANE}
            </div>
            <span style={{ fontFamily: "'Bebas Neue',sans-serif", fontSize: "1.4rem", letterSpacing: ".04em", color: "#131210", lineHeight: 1 }}>
              SKY<em style={{ color: "#e8191a", fontStyle: "normal" }}>MIND</em>
            </span>
          </Link>

          {/* Desktop links */}
          <div className="nav-links-desktop" style={{ display: "flex", alignItems: "stretch", flex: 1 }}>
            {links.map(l => {
              const active = isActive(l.href);
              return (
                <Link key={l.href} href={l.href} style={{
                  display: "flex", alignItems: "center", padding: "0 18px",
                  fontSize: ".78rem", fontWeight: 500, letterSpacing: ".04em", textTransform: "uppercase",
                  color: active ? "#131210" : "#5c5a56",
                  textDecoration: "none", borderRight: "1px solid #efefed",
                  position: "relative", transition: "color .15s, background .15s",
                  whiteSpace: "nowrap",
                }}
                  onMouseEnter={e => { if (!active) { e.currentTarget.style.color = "#131210"; e.currentTarget.style.background = "#f6f4f0"; } }}
                  onMouseLeave={e => { if (!active) { e.currentTarget.style.color = "#5c5a56"; e.currentTarget.style.background = "transparent"; } }}
                >
                  {l.label}
                  {active && <span style={{ position: "absolute", bottom: 0, left: 0, right: 0, height: "2px", background: "#e8191a" }} />}
                </Link>
              );
            })}
          </div>

          {/* Right — auth */}
          <div className="nav-links-desktop" style={{ display: "flex", alignItems: "center", marginLeft: "auto", borderLeft: "1px solid #efefed" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "7px", padding: "0 16px", borderRight: "1px solid #efefed", fontSize: ".72rem", letterSpacing: ".06em", textTransform: "uppercase", color: "#5c5a56", whiteSpace: "nowrap" }}>
              <div className="status-dot" />
              Live fares
            </div>

            {!userLoading && (
              user ? (
                <div style={{ display: "flex", alignItems: "center" }}>
                  <Link href="/dashboard" style={{ padding: "0 16px", height: "100%", display: "flex", alignItems: "center", gap: "8px", textDecoration: "none", fontSize: ".78rem", fontWeight: 600, color: "var(--black)", borderRight: "1px solid #efefed", transition: "background .15s" }}
                    onMouseEnter={e => (e.currentTarget.style.background = "#f6f4f0")}
                    onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
                  >
                    <div style={{ width: "26px", height: "26px", borderRadius: "50%", background: "#e8191a", color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", fontSize: ".72rem", fontWeight: 700, flexShrink: 0 }}>
                      {userInitial}
                    </div>
                    My Account
                  </Link>
                  <button onClick={handleSignOut} style={{ padding: "0 16px", height: "100%", background: "none", border: "none", cursor: "pointer", fontSize: ".78rem", fontWeight: 500, color: "#5c5a56", borderRight: "1px solid #efefed", fontFamily: "'Instrument Sans',sans-serif", transition: "color .15s" }}
                    onMouseEnter={e => (e.currentTarget.style.color = "#e8191a")}
                    onMouseLeave={e => (e.currentTarget.style.color = "#5c5a56")}
                  >
                    Sign Out
                  </button>
                </div>
              ) : (
                <Link href="/auth" style={{ padding: "0 16px", height: "100%", display: "flex", alignItems: "center", textDecoration: "none", fontSize: ".78rem", fontWeight: 600, color: "var(--black)", borderRight: "1px solid #efefed", transition: "background .15s" }}
                  onMouseEnter={e => (e.currentTarget.style.background = "#f6f4f0")}
                  onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
                >
                  Sign In
                </Link>
              )
            )}

            <Link href="/flights" style={{ padding: "0 20px", height: "100%", background: "#e8191a", color: "#fff", display: "flex", alignItems: "center", gap: "6px", textDecoration: "none", fontSize: ".78rem", fontWeight: 700, fontFamily: "'Instrument Sans',sans-serif", transition: "background .15s", whiteSpace: "nowrap" }}
              onMouseEnter={e => (e.currentTarget.style.background = "#c01415")}
              onMouseLeave={e => (e.currentTarget.style.background = "#e8191a")}
            >
              Book now
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M5 12h14M12 5l7 7-7 7" /></svg>
            </Link>
          </div>

          {/* Mobile hamburger */}
          <div className="nav-mobile-menu" style={{ marginLeft: "auto", alignItems: "center", gap: "12px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: ".68rem", color: "#5c5a56" }}>
              <div className="status-dot" />
            </div>
            <button onClick={() => setMobileOpen(o => !o)} style={{ background: "none", border: "none", cursor: "pointer", padding: "8px", color: "#131210", display: "flex", flexDirection: "column", gap: "5px" }} aria-label="Menu">
              <span style={{ width: "20px", height: "2px", background: "#131210", display: "block", transition: "all .2s", transform: mobileOpen ? "rotate(45deg) translate(5px, 5px)" : "none" }} />
              <span style={{ width: "20px", height: "2px", background: "#131210", display: "block", transition: "all .2s", opacity: mobileOpen ? 0 : 1 }} />
              <span style={{ width: "20px", height: "2px", background: "#131210", display: "block", transition: "all .2s", transform: mobileOpen ? "rotate(-45deg) translate(5px, -5px)" : "none" }} />
            </button>
          </div>
        </div>
      </nav>

      {/* Mobile dropdown */}
      {mobileOpen && (
        <div style={{ position: "fixed", top: "60px", left: 0, right: 0, zIndex: 199, background: "#ffffff", borderBottom: "1px solid #131210", boxShadow: "0 8px 24px rgba(19,18,16,.12)" }}>
          {links.map(l => {
            const active = isActive(l.href);
            return (
              <Link key={l.href} href={l.href} style={{ display: "block", padding: "16px 20px", fontSize: ".9rem", fontWeight: active ? 600 : 400, color: active ? "#131210" : "#5c5a56", textDecoration: "none", borderBottom: "1px solid #efefed", background: active ? "#f6f4f0" : "transparent", borderLeft: active ? "3px solid #e8191a" : "3px solid transparent" }}>
                {l.label}
              </Link>
            );
          })}
          {user ? (
            <>
              <Link href="/dashboard" style={{ display: "block", padding: "16px 20px", fontSize: ".9rem", color: "#5c5a56", textDecoration: "none", borderBottom: "1px solid #efefed" }}>My Dashboard</Link>
              <button onClick={handleSignOut} style={{ display: "block", width: "100%", textAlign: "left", padding: "16px 20px", fontSize: ".9rem", color: "#e8191a", background: "none", border: "none", borderBottom: "1px solid #efefed", cursor: "pointer", fontFamily: "'Instrument Sans',sans-serif" }}>Sign Out</button>
            </>
          ) : (
            <Link href="/auth" style={{ display: "block", padding: "16px 20px", fontSize: ".9rem", color: "#5c5a56", textDecoration: "none", borderBottom: "1px solid #efefed" }}>Sign In</Link>
          )}
          <Link href="/flights" style={{ display: "block", padding: "16px 20px", margin: "12px", background: "#e8191a", color: "#fff", textAlign: "center", textDecoration: "none", fontSize: ".9rem", fontWeight: 700, fontFamily: "'Instrument Sans',sans-serif" }}>
            Book now →
          </Link>
        </div>
      )}

      {/* Spacer */}
      <div style={{ height: "60px" }} />
    </>
  );
}
