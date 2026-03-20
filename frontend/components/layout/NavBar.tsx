'use client'
import { useState, useEffect } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'

const PLANE_SVG = (
  <svg width="18" height="18" viewBox="0 0 20 20" fill="currentColor">
    <path d="M18 7L11 11L4 7L2.5 8.5L9.5 13L7.5 17.5L10.5 16.5L13.5 17.5L11.5 13L18.5 8.5L18 7Z"/>
    <path d="M11 11L15.5 4.5L18 7L11 11Z" opacity=".55"/>
  </svg>
)

export default function NavBar() {
  const [scrolled, setScrolled] = useState(false)
  const pathname = usePathname()
  useEffect(() => {
    const fn = () => setScrolled(window.scrollY > 4)
    window.addEventListener('scroll', fn, { passive: true })
    return () => window.removeEventListener('scroll', fn)
  }, [])

  const links = [
    { href: '/',          id: 'home',      label: 'Home',       icon: <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 12L12 3L21 12V21H15V15H9V21H3V12Z"/></svg> },
    { href: '/flights',   id: 'flights',   label: 'Search',     icon: <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M17.8 19.2L16 11l3.5-3.5C21 6 21 4 19.5 2.5S18 2 16.5 3.5L13 7 4.8 6.2c-.5-.1-.9.1-1.1.5L2 8.9c-.2.4-.1.9.2 1.2l4.6 4.1-1.5 6.4 2.8 2.8 5.3-3.2 4.1 4.6c.3.4.8.5 1.2.2l1.1-1.2c.4-.2.6-.6.5-1.1z"/></svg> },
    { href: '/predict',   id: 'predict',   label: 'AI Predict', icon: <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg> },
    { href: '/dashboard', id: 'dashboard', label: 'Dashboard',  icon: <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg> },
  ]

  const isActive = (href: string) => href === '/' ? pathname === '/' : pathname.startsWith(href)

  return (
    <nav style={{ position:'fixed', top:0, left:0, right:0, zIndex:200, background:'#ffffff', borderBottom:'1px solid #131210', height:'60px', display:'flex', alignItems:'stretch', boxShadow: scrolled ? '0 2px 12px rgba(19,18,16,.07)' : 'none', transition:'box-shadow .2s' }}>
      <div style={{ width:'100%', maxWidth:'1160px', margin:'0 auto', padding:'0 32px', display:'flex', alignItems:'stretch' }}>
        {/* Logo */}
        <Link href="/" style={{ display:'flex', alignItems:'center', gap:'12px', paddingRight:'28px', borderRight:'1px solid #131210', textDecoration:'none', flexShrink:0 }}>
          <div style={{ width:'34px', height:'34px', background:'#131210', display:'flex', alignItems:'center', justifyContent:'center', color:'#fff' }}>{PLANE_SVG}</div>
          <div style={{ fontFamily:"'Bebas Neue',sans-serif", fontSize:'1.45rem', letterSpacing:'.04em', color:'#131210', lineHeight:1 }}>
            SKY<em style={{ color:'#e8191a', fontStyle:'normal' }}>MIND</em>
          </div>
        </Link>

        {/* Nav links */}
        <div style={{ display:'flex', alignItems:'stretch', flex:1 }}>
          {links.map(l => {
            const active = isActive(l.href)
            return (
              <Link key={l.href} href={l.href} style={{
                display:'flex', alignItems:'center', gap:'7px', padding:'0 20px',
                fontSize:'.78rem', fontWeight:500, letterSpacing:'.04em', textTransform:'uppercase',
                color: active ? '#131210' : '#5c5a56',
                textDecoration:'none', borderRight:'1px solid #efefed',
                position:'relative', transition:'color .15s, background .15s',
                background: active ? 'transparent' : 'transparent',
                whiteSpace:'nowrap',
              }}
                onMouseEnter={e => { if (!active) { e.currentTarget.style.color='#131210'; e.currentTarget.style.background='#f6f4f0' } }}
                onMouseLeave={e => { if (!active) { e.currentTarget.style.color='#5c5a56'; e.currentTarget.style.background='transparent' } }}
              >
                {l.icon}{l.label}
                {active && <span style={{ position:'absolute', bottom:0, left:0, right:0, height:'2px', background:'#e8191a' }} />}
              </Link>
            )
          })}
        </div>

        {/* Right */}
        <div style={{ display:'flex', alignItems:'center', marginLeft:'auto', borderLeft:'1px solid #efefed' }}>
          <div style={{ display:'flex', alignItems:'center', gap:'7px', padding:'0 18px', borderRight:'1px solid #efefed', fontSize:'.72rem', letterSpacing:'.06em', textTransform:'uppercase', color:'#5c5a56' }}>
            <div className="status-dot" />
            Live fares
          </div>
          <button style={{ padding:'0 20px', height:'100%', background:'transparent', color:'#5c5a56', border:'none', borderRight:'1px solid #efefed', cursor:'pointer', fontSize:'.8rem', fontWeight:600, fontFamily:"'Instrument Sans',sans-serif", transition:'all .15s' }}
            onMouseEnter={e=>{e.currentTarget.style.background='#f6f4f0';e.currentTarget.style.color='#131210'}}
            onMouseLeave={e=>{e.currentTarget.style.background='transparent';e.currentTarget.style.color='#5c5a56'}}
          >Sign in</button>
          <Link href="/flights" style={{ padding:'0 22px', height:'100%', background:'#e8191a', color:'#fff', display:'flex', alignItems:'center', gap:'7px', textDecoration:'none', fontSize:'.8rem', fontWeight:700, fontFamily:"'Instrument Sans',sans-serif", letterSpacing:'.02em', transition:'background .15s' }}
            onMouseEnter={e=>(e.currentTarget.style.background='#c01415')}
            onMouseLeave={e=>(e.currentTarget.style.background='#e8191a')}
          >
            Book now
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
          </Link>
        </div>
      </div>
    </nav>
  )
}
