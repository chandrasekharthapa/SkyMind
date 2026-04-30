"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { supabase } from "@/lib/supabase";
import { useTheme } from "@/context/ThemeContext";

export default function NavBar() {
  const [scrolled, setScrolled] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [user, setUser] = useState<any>(null);
  const pathname = usePathname();
  const router = useRouter();
  const { theme, toggleTheme } = useTheme();
  const [profile, setProfile] = useState<any>(null);

  useEffect(() => {
    const fn = () => setScrolled(window.scrollY > 4);
    window.addEventListener("scroll", fn, { passive: true });
    return () => window.removeEventListener("scroll", fn);
  }, []);

  useEffect(() => { setMobileOpen(false); }, [pathname]);

  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => setUser(session?.user ?? null));
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_e, session) => setUser(session?.user ?? null));
    return () => subscription.unsubscribe();
  }, []);

  useEffect(() => {
    if (user) {
      supabase.from("profiles").select("*").eq("id", user.id).single().then(({ data }) => setProfile(data));
    } else {
      setProfile(null);
    }
  }, [user]);

  const handleSignOut = async () => {
    await supabase.auth.signOut();
    router.push("/");
  };

  const isActive = (href: string) => href === "/" ? pathname === "/" : pathname.startsWith(href);

  const navLinks = [
    { href: "/", label: "Home", icon: <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 12L12 3L21 12V21H15V15H9V21H3V12Z"/></svg> },
    { href: "/flights", label: "Search", icon: <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M17.8 19.2L16 11l3.5-3.5C21 6 21 4 19.5 2.5S18 2 16.5 3.5L13 7 4.8 6.2c-.5-.1-.9.1-1.1.5L2 8.9c-.2.4-.1.9.2 1.2l4.6 4.1-1.5 6.4 2.8 2.8 5.3-3.2 4.1 4.6c.3.4.8.5 1.2.2l1.1-1.2c.4-.2.6-.6.5-1.1z"/></svg> },
    { href: "/predict", label: "AI Forecast", icon: <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg> },
    { href: "/dashboard", label: "Dashboard", icon: <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg> },
  ];

  return (
    <>
      <nav className={`ui-nav ${scrolled ? "ui-nav-scrolled" : ""}`}>
        <div className="ui-wrap ui-nav-inner">

          {/* Logo Section */}
          <Link href="/" className="ui-nav-logo" style={{ transition: "opacity 0.2s" }}>
            <div className="ui-nav-logo-box" style={{ transition: "transform 0.2s" }}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="white"><path d="M17.8 19.2L16 11l3.5-3.5C21 6 21 4 19.5 2.5S18 2 16.5 3.5L13 7 4.8 6.2c-.5-.1-.9.1-1.1.5L2 8.9c-.2.4-.1.9.2 1.2l4.6 4.1-1.5 6.4 2.8 2.8 5.3-3.2 4.1 4.6c.3.4.8.5 1.2.2l1.1-1.2c.4-.2.6-.6.5-1.1z"/></svg>
            </div>
            <span style={{ fontFamily: "var(--fd)", fontSize: "1.4rem", color: theme === 'dark' ? '#fff' : '#000', lineHeight: 1, letterSpacing: "-0.01em" }}>
              SKY<em style={{ color: "var(--red)", fontStyle: "normal", fontWeight: 800 }}>MIND</em>
            </span>
          </Link>

          {/* Desktop Navigation Links */}
          <div className="nav-links-desktop ui-flex" style={{ flex: 1 }}>
            {navLinks.map(l => (
              <Link 
                key={l.href} 
                href={l.href} 
                className={`ui-nav-link ${isActive(l.href) ? "active" : ""}`}
              >
                {l.icon}
                {l.label}
              </Link>
            ))}
          </div>

          {/* Desktop Action Section */}
          <div className="nav-links-desktop ui-flex" style={{ marginLeft: "auto", height: "100%", gap: "24px", paddingRight: "24px" }}>
            
            <button 
              onClick={toggleTheme}
              className="ui-nav-link"
              style={{ 
                background: "none", 
                border: "none", 
                cursor: "pointer", 
                color: "var(--grey3)",
                fontFamily: "var(--fm)",
                fontSize: "0.6rem",
                fontWeight: 700,
                letterSpacing: "0.1em"
              }}
            >
              {theme === 'light' ? "[ DARK ]" : "[ LIGHT ]"}
            </button>

            <div className="ui-flex" style={{ fontSize: "0.65rem", color: "var(--grey3)", textTransform: "uppercase", fontFamily: "var(--fm)", gap: "8px", fontWeight: 700, letterSpacing: "0.1em" }}>
              <div className="status-dot" style={{ width: 6, height: 6, background: "var(--red)", boxShadow: "0 0 8px var(--red)", animation: "blink 2s infinite" }} />
              AI Live
            </div>
            
            {user ? (
              <>
                <Link href="/dashboard" className={`ui-nav-link ${pathname === '/dashboard' ? 'active' : ''}`}>
                  <div style={{ width: 22, height: 22, borderRadius: "5px", background: "var(--red)", color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "10px", fontWeight: 800 }}>
                    {(profile?.display_name || user.email || "U")[0].toUpperCase()}
                  </div>
                  ACCOUNT
                </Link>
                <button onClick={handleSignOut} className="ui-nav-link" style={{ background: "none", border: "none", cursor: "pointer", fontSize: "0.7rem" }}>
                  SIGN OUT
                </button>
              </>
            ) : (
              <Link href="/auth" className="ui-nav-link">Sign In</Link>
            )}
            
            <Link href="/flights" className="ui-btn ui-btn-red" style={{ height: "100%", borderRadius: 0, padding: "0 24px", fontSize: "0.8rem", fontWeight: 800, letterSpacing: "0.05em", textTransform: "uppercase" }}>
              Book Now
            </Link>
          </div>

          {/* Mobile Menu Toggle */}
          <div className="nav-mobile-btn ui-flex" style={{ marginLeft: "auto", display: "none", gap: "12px" }}>
            <button 
              onClick={toggleTheme}
              className="ui-nav-link" 
              style={{ 
                background: "none", 
                border: "none", 
                cursor: "pointer", 
                color: "var(--grey3)",
                fontFamily: "var(--fm)",
                fontSize: "0.6rem",
                fontWeight: 700,
                letterSpacing: "0.1em",
                padding: "0 10px"
              }}
            >
              {theme === 'light' ? "[ DARK ]" : "[ LIGHT ]"}
            </button>
            <button 
              onClick={() => setMobileOpen(o => !o)} 
              className="ui-btn ui-btn-white" 
              style={{ width: 44, height: 44, padding: 0 }}
            >
              {mobileOpen
                ? <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                : <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
              }
            </button>
          </div>
        </div>
      </nav>

      {/* Mobile Menu Backdrop */}
      <div 
        className={`ui-nav-mobile ${mobileOpen ? "open" : ""}`} 
        onClick={() => setMobileOpen(false)}
      >
        {navLinks.map(l => (
          <Link 
            key={l.href} 
            href={l.href} 
            className={`ui-nav-mobile-link ${isActive(l.href) ? "active" : ""}`}
          >
            {l.icon} {l.label}
          </Link>
        ))}
        {user ? (
          <button 
            onClick={async () => { await supabase.auth.signOut(); router.push("/"); }}
            className="ui-nav-mobile-link"
            style={{ width: "100%", background: "none", border: "none", color: "var(--red)", textAlign: "left" }}
          >
            Sign Out
          </button>
        ) : (
          <Link href="/auth" className="ui-nav-mobile-link">Sign In</Link>
        )}
        <div style={{ padding: "var(--ui-space-md)" }}>
          <Link href="/flights" className="ui-btn ui-btn-red" style={{ width: "100%" }}>
            BOOK NOW
          </Link>
        </div>
      </div>
    </>
  );
}
