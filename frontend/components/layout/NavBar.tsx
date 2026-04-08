"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { supabase } from "@/lib/supabase";

export default function NavBar() {
  const [scrolled, setScrolled] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [user, setUser] = useState<any>(null);
  const pathname = usePathname();
  const router = useRouter();

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

  const isActive = (href: string) => href === "/" ? pathname === "/" : pathname.startsWith(href);

  const navLinks = [
    { href: "/", label: "Home", icon: <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 12L12 3L21 12V21H15V15H9V21H3V12Z"/></svg> },
    { href: "/flights", label: "Search", icon: <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M17.8 19.2L16 11l3.5-3.5C21 6 21 4 19.5 2.5S18 2 16.5 3.5L13 7 4.8 6.2c-.5-.1-.9.1-1.1.5L2 8.9c-.2.4-.1.9.2 1.2l4.6 4.1-1.5 6.4 2.8 2.8 5.3-3.2 4.1 4.6c.3.4.8.5 1.2.2l1.1-1.2c.4-.2.6-.6.5-1.1z"/></svg> },
    { href: "/predict", label: "AI Forecast", icon: <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg> },
    { href: "/dashboard", label: "Dashboard", icon: <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg> },
  ];

  return (
    <>
      <nav style={{
        position:"fixed", top:0, left:0, right:0, zIndex:200,
        background:"var(--white)", borderBottom:"1px solid var(--black)",
        height:60, display:"flex", alignItems:"stretch",
        boxShadow: scrolled ? "0 2px 8px rgba(19,18,16,.06)" : "none",
        transition:"box-shadow .2s",
      }}>
        <div style={{ width:"100%", maxWidth:1160, margin:"0 auto", padding:"0 32px", display:"flex", alignItems:"stretch" }}>

          {/* Logo */}
          <Link href="/" style={{ display:"flex", alignItems:"center", gap:12, paddingRight:28, borderRight:"1px solid var(--black)", textDecoration:"none", flexShrink:0 }}>
            <div style={{ width:34, height:34, background:"var(--black)", display:"flex", alignItems:"center", justifyContent:"center", flexShrink:0 }}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="white"><path d="M17.8 19.2L16 11l3.5-3.5C21 6 21 4 19.5 2.5S18 2 16.5 3.5L13 7 4.8 6.2c-.5-.1-.9.1-1.1.5L2 8.9c-.2.4-.1.9.2 1.2l4.6 4.1-1.5 6.4 2.8 2.8 5.3-3.2 4.1 4.6c.3.4.8.5 1.2.2l1.1-1.2c.4-.2.6-.6.5-1.1z"/></svg>
            </div>
            <span style={{ fontFamily:"var(--fd)", fontSize:"1.45rem", letterSpacing:".04em", color:"var(--black)", lineHeight:1 }}>
              SKY<em style={{ color:"var(--red)", fontStyle:"normal" }}>MIND</em>
            </span>
          </Link>

          {/* Desktop nav */}
          <div className="nav-links-desktop" style={{ display:"flex", alignItems:"stretch", flex:1 }}>
            {navLinks.map(l => {
              const active = isActive(l.href);
              return (
                <Link key={l.href} href={l.href} style={{
                  display:"flex", alignItems:"center", gap:7, padding:"0 20px",
                  fontSize:".78rem", fontWeight:500, letterSpacing:".04em", textTransform:"uppercase",
                  color: active ? "var(--black)" : "var(--grey4)",
                  textDecoration:"none", borderRight:"1px solid var(--grey1)",
                  position:"relative", transition:"color .15s,background .15s", whiteSpace:"nowrap",
                  fontFamily:"var(--fb)",
                }}
                  onMouseEnter={e => { if (!active) { (e.currentTarget as HTMLElement).style.color = "var(--black)"; (e.currentTarget as HTMLElement).style.background = "var(--off)"; } }}
                  onMouseLeave={e => { if (!active) { (e.currentTarget as HTMLElement).style.color = "var(--grey4)"; (e.currentTarget as HTMLElement).style.background = "transparent"; } }}
                >
                  {l.icon}
                  {l.label}
                  {active && <span style={{ position:"absolute", bottom:0, left:0, right:0, height:2, background:"var(--red)" }} />}
                </Link>
              );
            })}
          </div>

          {/* Right section */}
          <div className="nav-links-desktop" style={{ display:"flex", alignItems:"center", marginLeft:"auto", borderLeft:"1px solid var(--grey1)" }}>
            <div style={{ display:"flex", alignItems:"center", gap:7, padding:"0 18px", borderRight:"1px solid var(--grey1)", fontSize:".72rem", letterSpacing:".06em", textTransform:"uppercase", color:"var(--grey4)", height:"100%", fontFamily:"var(--fm)" }}>
              <div className="status-dot" />
              XGBoost Live
            </div>
            {user ? (
              <>
                <Link href="/dashboard" style={{ padding:"0 16px", height:"100%", display:"flex", alignItems:"center", gap:8, textDecoration:"none", fontSize:".78rem", fontWeight:500, letterSpacing:".04em", textTransform:"uppercase", color:"var(--grey4)", borderRight:"1px solid var(--grey1)", transition:"background .15s,color .15s", fontFamily:"var(--fb)" }}
                  onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = "var(--off)"; (e.currentTarget as HTMLElement).style.color = "var(--black)"; }}
                  onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = "transparent"; (e.currentTarget as HTMLElement).style.color = "var(--grey4)"; }}
                >
                  <div style={{ width:24, height:24, background:"var(--red)", color:"#fff", display:"flex", alignItems:"center", justifyContent:"center", fontSize:".68rem", fontWeight:700, fontFamily:"var(--fm)" }}>
                    {user.email?.[0]?.toUpperCase() ?? "U"}
                  </div>
                  Account
                </Link>
                <button onClick={async () => { await supabase.auth.signOut(); router.push("/"); }}
                  style={{ padding:"0 16px", height:"100%", background:"none", border:"none", cursor:"pointer", fontSize:".78rem", fontWeight:500, letterSpacing:".04em", textTransform:"uppercase", color:"var(--grey4)", borderRight:"1px solid var(--grey1)", fontFamily:"var(--fb)", transition:"color .15s,background .15s" }}
                  onMouseEnter={e => { (e.currentTarget as HTMLElement).style.color = "var(--red)"; (e.currentTarget as HTMLElement).style.background = "var(--off)"; }}
                  onMouseLeave={e => { (e.currentTarget as HTMLElement).style.color = "var(--grey4)"; (e.currentTarget as HTMLElement).style.background = "transparent"; }}
                >
                  Sign Out
                </button>
              </>
            ) : (
              <Link href="/auth" style={{ padding:"0 20px", height:"100%", display:"flex", alignItems:"center", textDecoration:"none", fontSize:".78rem", fontWeight:500, letterSpacing:".04em", textTransform:"uppercase", color:"var(--grey4)", borderRight:"1px solid var(--grey1)", transition:"background .15s,color .15s", fontFamily:"var(--fb)" }}
                onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = "var(--off)"; (e.currentTarget as HTMLElement).style.color = "var(--black)"; }}
                onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = "transparent"; (e.currentTarget as HTMLElement).style.color = "var(--grey4)"; }}
              >
                Sign In
              </Link>
            )}
            <Link href="/flights" style={{ padding:"0 22px", height:"100%", background:"var(--red)", color:"#fff", display:"flex", alignItems:"center", gap:6, textDecoration:"none", fontSize:".8rem", fontWeight:600, fontFamily:"var(--fb)", transition:"background .15s", whiteSpace:"nowrap" }}
              onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = "var(--red-d)"; }}
              onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = "var(--red)"; }}
            >
              Book now
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
            </Link>
          </div>

          {/* Mobile hamburger */}
          <div className="nav-mobile-btn" style={{ marginLeft:"auto", alignItems:"center", gap:12, display:"none" }}>
            <div className="status-dot" />
            <button onClick={() => setMobileOpen(o => !o)} style={{ background:"none", border:"none", cursor:"pointer", padding:8, color:"var(--black)", display:"flex", alignItems:"center" }}>
              {mobileOpen
                ? <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                : <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
              }
            </button>
          </div>
        </div>
      </nav>

      {/* Mobile menu */}
      {mobileOpen && (
        <div style={{ position:"fixed", top:60, left:0, right:0, zIndex:199, background:"var(--white)", borderBottom:"1px solid var(--black)", boxShadow:"0 8px 24px rgba(19,18,16,.12)" }}>
          {navLinks.map(l => (
            <Link key={l.href} href={l.href} style={{
              display:"flex", alignItems:"center", gap:10, padding:"16px 24px",
              fontSize:".85rem", fontWeight: isActive(l.href) ? 600 : 500,
              color: isActive(l.href) ? "var(--black)" : "var(--grey4)", textDecoration:"none",
              borderBottom:"1px solid var(--grey1)", background: isActive(l.href) ? "var(--off)" : "transparent",
              borderLeft: isActive(l.href) ? "3px solid var(--red)" : "3px solid transparent", fontFamily:"var(--fb)",
            }}>
              {l.icon} {l.label}
            </Link>
          ))}
          {user
            ? <button onClick={async () => { await supabase.auth.signOut(); router.push("/"); }} style={{ display:"block", width:"100%", textAlign:"left", padding:"16px 24px", fontSize:".85rem", color:"var(--red)", background:"none", border:"none", borderBottom:"1px solid var(--grey1)", cursor:"pointer", fontFamily:"var(--fb)" }}>Sign Out</button>
            : <Link href="/auth" style={{ display:"block", padding:"16px 24px", fontSize:".85rem", color:"var(--grey4)", textDecoration:"none", borderBottom:"1px solid var(--grey1)", fontFamily:"var(--fb)" }}>Sign In</Link>
          }
          <Link href="/flights" style={{ display:"block", padding:"16px 24px", margin:"12px 16px 16px", background:"var(--red)", color:"#fff", textAlign:"center", textDecoration:"none", fontSize:".88rem", fontWeight:700, fontFamily:"var(--fd)", letterSpacing:".08em" }}>
            BOOK NOW
          </Link>
        </div>
      )}

      <div style={{ height:60 }} />

      <style>{`
        @keyframes blink { 0%,100%{opacity:1} 50%{opacity:.3} }
        @media(max-width:768px){.nav-links-desktop{display:none!important}.nav-mobile-btn{display:flex!important}}
        @media(min-width:769px){.nav-mobile-btn{display:none!important}}
      `}</style>
    </>
  );
}
