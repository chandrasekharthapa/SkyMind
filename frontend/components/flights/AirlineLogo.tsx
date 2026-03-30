'use client'
/**
 * AirlineLogo — robust multi-source logo with graceful fallback.
 *
 * Source chain:
 *   1. airhex.com  (best quality, supports most carriers)
 *   2. aviationstack CDN
 *   3. Logo.dev (works for many airline domains)
 *   4. Colored IATA badge (always works)
 */

import { useState } from 'react'

// Known airline brand colors for the fallback badge
const AIRLINE_COLORS: Record<string, { bg: string; text: string }> = {
  AI:  { bg: '#C8102E', text: '#fff' },   // Air India red
  '6E': { bg: '#2B3A8C', text: '#fff' },  // IndiGo blue
  SG:  { bg: '#FF0000', text: '#fff' },   // SpiceJet red
  UK:  { bg: '#4A235A', text: '#fff' },   // Vistara purple
  IX:  { bg: '#C8102E', text: '#fff' },   // Air India Express
  QP:  { bg: '#FF5F00', text: '#fff' },   // Akasa orange
  S5:  { bg: '#002868', text: '#fff' },   // Star Air navy
  EK:  { bg: '#D4A017', text: '#000' },   // Emirates gold
  SQ:  { bg: '#003B5C', text: '#fff' },   // Singapore navy
  QR:  { bg: '#5C0632', text: '#fff' },   // Qatar maroon
  EY:  { bg: '#BD8B13', text: '#fff' },   // Etihad gold
  BA:  { bg: '#075AAA', text: '#fff' },   // British blue
  TK:  { bg: '#C8102E', text: '#fff' },   // Turkish red
  MH:  { bg: '#DC241F', text: '#fff' },   // Malaysia red
  LH:  { bg: '#05164D', text: '#FFD700' }, // Lufthansa navy
  AF:  { bg: '#002157', text: '#fff' },   // Air France blue
  KL:  { bg: '#00A1E4', text: '#fff' },   // KLM light blue
  FZ:  { bg: '#E42C2E', text: '#fff' },   // flydubai red
  G9:  { bg: '#E52628', text: '#fff' },   // Air Arabia red
  WY:  { bg: '#005E8F', text: '#fff' },   // Oman Air
  UL:  { bg: '#00205B', text: '#fff' },   // SriLankan
}

// Airline website domains for Logo.dev fallback
const AIRLINE_DOMAINS: Record<string, string> = {
  AI: 'airindia.com', '6E': 'goindigo.in', SG: 'spicejet.com',
  UK: 'airvistara.com', IX: 'airindiaexpress.in', QP: 'akasaair.com',
  EK: 'emirates.com', SQ: 'singaporeair.com', QR: 'qatarairways.com',
  EY: 'etihad.com', BA: 'britishairways.com', TK: 'turkishairlines.com',
  MH: 'malaysiaairlines.com', LH: 'lufthansa.com', AF: 'airfrance.com',
  KL: 'klm.com', FZ: 'flydubai.com', G9: 'airarabia.com',
}

function getLogoSources(iata: string): string[] {
  const code = iata.toUpperCase()
  const sources: string[] = []

  // 1. airhex — best, supports 900+ airlines
  sources.push(`https://content.airhex.com/content/logos/airlines_${code}_200_200_s.png`)

  // 2. Logo.dev via airline domain
  const domain = AIRLINE_DOMAINS[code]
  if (domain) {
    sources.push(`https://img.logo.dev/${domain}?token=pk_X3FZt3VfT4ShbQi5lJ91nw&format=png&size=48`)
  }

  // 3. Clearbit (catches some airlines)
  if (domain) {
    sources.push(`https://logo.clearbit.com/${domain}`)
  }

  return sources
}

interface AirlineLogoProps {
  code: string
  name: string
  size?: number  // px, default 42
  className?: string
}

export default function AirlineLogo({ code, name, size = 42, className }: AirlineLogoProps) {
  const iata = code.toUpperCase()
  const sources = getLogoSources(iata)
  const [srcIndex, setSrcIndex] = useState(0)
  const [failed, setFailed] = useState(false)

  const colors = AIRLINE_COLORS[iata] || { bg: '#131210', text: '#fff' }

  const handleError = () => {
    const next = srcIndex + 1
    if (next < sources.length) {
      setSrcIndex(next)
    } else {
      setFailed(true)
    }
  }

  const boxStyle: React.CSSProperties = {
    width: `${size}px`,
    height: `${size}px`,
    flexShrink: 0,
    border: '1px solid var(--grey1)',
    overflow: 'hidden',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: '4px',
  }

  if (failed) {
    // Colored IATA badge — always looks good
    return (
      <div
        style={{
          ...boxStyle,
          background: colors.bg,
          border: `1px solid ${colors.bg}`,
        }}
        className={className}
        title={name}
      >
        <span style={{
          fontFamily: "'Martian Mono', monospace",
          fontSize: size > 38 ? '.62rem' : '.55rem',
          fontWeight: 800,
          color: colors.text,
          letterSpacing: '.04em',
          textAlign: 'center',
          padding: '2px',
          lineHeight: 1,
          userSelect: 'none',
        }}>
          {iata.length <= 2 ? iata : iata.slice(0, 2)}
        </span>
      </div>
    )
  }

  return (
    <div style={{ ...boxStyle, background: '#f8f8f8', padding: '3px' }} className={className} title={name}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={sources[srcIndex]}
        alt={name}
        style={{
          width: '100%',
          height: '100%',
          objectFit: 'contain',
        }}
        onError={handleError}
        loading="lazy"
      />
    </div>
  )
}

/**
 * Rectangular banner logo (for booking confirmation, etc.)
 */
export function AirlineLogoBanner({ code, name, height = 28 }: { code: string; name: string; height?: number }) {
  const iata = code.toUpperCase()
  const [failed, setFailed] = useState(false)
  const colors = AIRLINE_COLORS[iata] || { bg: '#131210', text: '#fff' }
  const src = `https://content.airhex.com/content/logos/airlines_${iata}_100_25_r.png`

  if (failed) {
    return (
      <div style={{
        height: `${height}px`,
        padding: '0 10px',
        background: colors.bg,
        display: 'inline-flex',
        alignItems: 'center',
        borderRadius: '3px',
      }}>
        <span style={{
          fontFamily: "'Martian Mono', monospace",
          fontSize: '.65rem',
          fontWeight: 800,
          color: colors.text,
          letterSpacing: '.06em',
        }}>
          {name.slice(0, 12)}
        </span>
      </div>
    )
  }

  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={src}
      alt={name}
      height={height}
      style={{ objectFit: 'contain' }}
      onError={() => setFailed(true)}
      loading="lazy"
    />
  )
}
