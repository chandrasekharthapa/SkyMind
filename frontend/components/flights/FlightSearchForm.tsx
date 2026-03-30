'use client'
import { useState, useEffect, useRef } from 'react'
import { useRouter } from 'next/navigation'
import { format, addDays } from 'date-fns'
import { supabase } from '@/lib/supabase'
import type { Airport } from '@/lib/supabase'

const QUICK = ['DEL','BOM','BLR','MAA','HYD','CCU','COK','AMD','GOI','JAI','PNQ','GAU']

function AirportField({ label, value, onChange, placeholder }: {
  label:string; value:string; onChange:(v:string)=>void; placeholder:string
}) {
  const [open, setOpen]         = useState(false)
  const [query, setQuery]       = useState('')
  const [results, setResults]   = useState<Airport[]>([])
  const [selected, setSelected] = useState<Airport|null>(null)
  const [loading, setLoading]   = useState(false)
  const wrap   = useRef<HTMLDivElement>(null)
  const search = useRef<HTMLInputElement>(null)

  useEffect(() => {
    const fn = (e:MouseEvent) => {
      if (wrap.current && !wrap.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', fn)
    return () => document.removeEventListener('mousedown', fn)
  }, [])

  // Load airport name when value changes
  useEffect(() => {
    if (!value) { setSelected(null); return }
    supabase.from('airports').select('*').eq('iata_code', value).single()
      .then(({ data }) => { if (data) setSelected(data as Airport) })
  }, [value])

  // Load results when dropdown opens or query changes
  useEffect(() => {
    if (!open) return
    setLoading(true)
    if (!query.trim()) {
      supabase.from('airports').select('*').eq('is_active',true)
        .in('iata_code', QUICK).order('city').limit(12)
        .then(({ data }) => { setResults((data||[]) as Airport[]); setLoading(false) })
      return
    }
    const q = query.trim()
    supabase.from('airports').select('*').eq('is_active',true)
      .or(`iata_code.ilike.${q.toUpperCase()}%,city.ilike.%${q}%,name.ilike.%${q}%`)
      .order('city').limit(8)
      .then(({ data }) => { setResults((data||[]) as Airport[]); setLoading(false) })
  }, [query, open])

  const openDrop = () => {
    setOpen(true); setQuery('')
    setTimeout(() => search.current?.focus(), 60)
  }

  return (
    <div ref={wrap} style={{ position:'relative' }}>
      <label className="field-label">{label}</label>
      {/* Trigger button */}
      <button type="button" onClick={openDrop} style={{
        width:'100%', display:'flex', alignItems:'center', gap:'10px',
        padding:'11px 12px', background:'#fff',
        border: open ? '1.5px solid #131210' : '1px solid #d8d6d2',
        cursor:'pointer', textAlign:'left', fontFamily:"'Instrument Sans',sans-serif",
        transition:'border-color .15s',
      }}>
        {selected ? (
          <span style={{ fontFamily:"'Martian Mono',monospace", fontSize:'.72rem', fontWeight:700, color:'#e8191a', background:'#f6f4f0', padding:'2px 7px', border:'1px solid #efefed', flexShrink:0 }}>
            {selected.iata_code}
          </span>
        ) : (
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#c8c6c2" strokeWidth="2" style={{flexShrink:0}}>
            <path d="M17.8 19.2L16 11l3.5-3.5C21 6 21 4 19.5 2.5S18 2 16.5 3.5L13 7 4.8 6.2c-.5-.1-.9.1-1.1.5L2 8.9c-.2.4-.1.9.2 1.2l4.6 4.1-1.5 6.4 2.8 2.8 5.3-3.2 4.1 4.6c.3.4.8.5 1.2.2l1.1-1.2c.4-.2.6-.6.5-1.1z"/>
          </svg>
        )}
        <div style={{ flex:1, minWidth:0, textAlign:'left' }}>
          {selected ? (
            <div style={{ fontSize:'.875rem', fontWeight:600, color:'#131210', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>
              {selected.city}{selected.state ? `, ${selected.state}` : ''}
            </div>
          ) : (
            <div style={{ fontSize:'.875rem', color:'#c8c6c2' }}>{placeholder}</div>
          )}
        </div>
        <svg width="10" height="6" viewBox="0 0 10 6" fill="none" style={{flexShrink:0, transform:open?'rotate(180deg)':'none', transition:'transform .2s'}}>
          <path d="M1 1L5 5L9 1" stroke="#9b9890" strokeWidth="1.5" strokeLinecap="round"/>
        </svg>
      </button>

      {/* Dropdown */}
      {open && (
        <div style={{
          position:'absolute', top:'100%', left:0, right:0, zIndex:500,
          background:'#fff', border:'1px solid #131210', borderTop:'none',
          boxShadow:'0 12px 32px rgba(19,18,16,.16)',
        }}>
          {/* Search input */}
          <div style={{ padding:'8px 12px', borderBottom:'1px solid #efefed', display:'flex', alignItems:'center', gap:'8px' }}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#9b9890" strokeWidth="2" style={{flexShrink:0}}><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg>
            <input ref={search} value={query} onChange={e=>setQuery(e.target.value)}
              placeholder="City, airport or IATA code..."
              style={{ width:'100%', border:'none', outline:'none', fontSize:'.875rem', color:'#131210', background:'transparent', fontFamily:"'Instrument Sans',sans-serif" }}
            />
            {query && (
              <button onClick={()=>setQuery('')} style={{background:'none',border:'none',cursor:'pointer',color:'#9b9890',padding:'2px',flexShrink:0}}>✕</button>
            )}
          </div>

          {!query && <div style={{ padding:'6px 12px 3px', fontSize:'.6rem', fontWeight:600, letterSpacing:'.12em', textTransform:'uppercase', color:'#c8c6c2', fontFamily:"'Martian Mono',monospace" }}>Popular airports</div>}

          <div style={{ maxHeight:'200px', overflowY:'auto' }}>
            {loading && <div style={{ padding:'12px', fontSize:'.82rem', color:'#9b9890', textAlign:'center' }}>Searching...</div>}
            {!loading && results.length === 0 && query && <div style={{ padding:'12px', fontSize:'.82rem', color:'#9b9890', textAlign:'center' }}>No airports found for "{query}"</div>}
            {results.map(ap => (
              <button key={ap.iata_code} type="button"
                onClick={() => { onChange(ap.iata_code); setOpen(false); setQuery('') }}
                style={{
                  width:'100%', textAlign:'left', padding:'10px 12px',
                  display:'flex', alignItems:'center', gap:'12px',
                  background: ap.iata_code===value ? '#f6f4f0' : 'transparent',
                  border:'none', borderBottom:'1px solid #efefed',
                  cursor:'pointer', fontFamily:"'Instrument Sans',sans-serif",
                  transition:'background .1s',
                }}
                onMouseEnter={e=>(e.currentTarget.style.background='#f6f4f0')}
                onMouseLeave={e=>(e.currentTarget.style.background=ap.iata_code===value?'#f6f4f0':'transparent')}
              >
                <div style={{ width:'40px', height:'32px', background:ap.iata_code===value?'#131210':'#f6f4f0', border:'1px solid #efefed', display:'flex', alignItems:'center', justifyContent:'center', flexShrink:0 }}>
                  <span style={{ fontFamily:"'Martian Mono',monospace", fontSize:'.68rem', fontWeight:700, color:ap.iata_code===value?'#fff':'#e8191a' }}>{ap.iata_code}</span>
                </div>
                <div style={{ flex:1, minWidth:0 }}>
                  <div style={{ fontSize:'.875rem', fontWeight:600, color:'#131210', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{ap.city}</div>
                  <div style={{ fontSize:'.72rem', color:'#9b9890', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{ap.name}</div>
                </div>
                <div style={{ fontSize:'.65rem', fontWeight:700, color: ap.is_international?'#e8191a':'#9b9890', fontFamily:"'Martian Mono',monospace", flexShrink:0 }}>
                  {ap.is_international ? 'INTL' : (ap.state||'').slice(0,3).toUpperCase()}
                </div>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

export default function FlightSearchForm({ compact=false }: { compact?:boolean }) {
  const router   = useRouter()
  // Default to 7 days from now — ensures Amadeus always finds results
  const defaultDate = format(addDays(new Date(), 7), 'yyyy-MM-dd')
  const tomorrow    = format(addDays(new Date(), 1), 'yyyy-MM-dd')

  const [form, setForm] = useState({
    origin:'DEL', destination:'BOM',
    departure_date: defaultDate, return_date:'',
    adults:1, cabin_class:'ECONOMY',
    trip_type:'ONE_WAY' as 'ONE_WAY'|'ROUND_TRIP',
  })
  const [activeTab, setActiveTab] = useState('One Way')
  const [swapping, setSwapping]   = useState(false)

  const swap = () => {
    setSwapping(true)
    setTimeout(() => setSwapping(false), 300)
    setForm(f => ({ ...f, origin:f.destination, destination:f.origin }))
  }

  const submit = (e:React.FormEvent) => {
    e.preventDefault()
    const p = new URLSearchParams({
      origin:         form.origin,
      destination:    form.destination,
      departure_date: form.departure_date,
      adults:         String(form.adults),
      cabin_class:    form.cabin_class,
      ...(form.return_date ? { return_date:form.return_date } : {}),
    })
    router.push(`/flights?${p}`)
  }

  return (
    <form onSubmit={submit}>
      {/* Trip type tabs */}
      <div className="trip-tabs">
        {(['One Way','Round Trip','Multi-city'] as const).map(t => (
          <button key={t} type="button"
            className={`trip-tab${activeTab===t?' active':''}`}
            onClick={() => setActiveTab(t)}
          >{t}</button>
        ))}
      </div>

      {/* FROM — SWAP — TO */}
      <div className="form-grid-2" style={{ marginBottom:'14px' }}>
        <AirportField label="From" value={form.origin} onChange={v=>setForm(f=>({...f,origin:v}))} placeholder="New Delhi (DEL)" />
        <div className="swap-col">
          <button type="button" className="swap-btn" onClick={swap} title="Swap airports"
            style={{ transform: swapping ? 'rotate(180deg)' : 'none', transition:'transform .3s' }}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M7 16V4m0 0L3 8m4-4l4 4M17 8v12m0 0l4-4m-4 4l-4-4"/>
            </svg>
          </button>
        </div>
        <AirportField label="To" value={form.destination} onChange={v=>setForm(f=>({...f,destination:v}))} placeholder="Mumbai (BOM)" />
      </div>

      {/* DATE — PAX — CLASS grid */}
      <div className="form-grid-4" style={{ marginBottom:'20px' }}>
        <div>
          <label className="field-label">Departure</label>
          <input type="date" className="inp" value={form.departure_date} min={tomorrow} required
            onChange={e=>setForm(f=>({...f,departure_date:e.target.value}))}
            onFocus={e=>(e.target.style.borderColor='#131210')}
            onBlur={e=>(e.target.style.borderColor='#d8d6d2')}
          />
        </div>
        <div>
          <label className="field-label">Return <span style={{color:'#c8c6c2',fontWeight:400,fontSize:'.6rem'}}>optional</span></label>
          <input type="date" className="inp" value={form.return_date} min={form.departure_date}
            onChange={e=>setForm(f=>({...f,return_date:e.target.value,trip_type:e.target.value?'ROUND_TRIP':'ONE_WAY'}))}
            onFocus={e=>(e.target.style.borderColor='#131210')}
            onBlur={e=>(e.target.style.borderColor='#d8d6d2')}
          />
        </div>
        <div>
          <label className="field-label">Passengers</label>
          <select className="inp" value={form.adults} onChange={e=>setForm(f=>({...f,adults:+e.target.value}))}>
            {[1,2,3,4,5,6,7,8,9].map(n => <option key={n} value={n}>{n} {n===1?'Adult':'Adults'}</option>)}
          </select>
        </div>
        <div>
          <label className="field-label">Class</label>
          <select className="inp" value={form.cabin_class} onChange={e=>setForm(f=>({...f,cabin_class:e.target.value}))}>
            <option value="ECONOMY">Economy</option>
            <option value="PREMIUM_ECONOMY">Prem Economy</option>
            <option value="BUSINESS">Business</option>
            <option value="FIRST">First Class</option>
          </select>
        </div>
      </div>

      {/* Submit */}
      <button type="submit" className="search-submit">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
          <circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/>
        </svg>
        SEARCH FLIGHTS
      </button>
    </form>
  )
}
