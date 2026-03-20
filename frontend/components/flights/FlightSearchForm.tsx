'use client'
import { useState, useEffect, useRef } from 'react'
import { useRouter } from 'next/navigation'
import { format, addDays } from 'date-fns'
import { supabase } from '@/lib/supabase'
import type { Airport } from '@/lib/supabase'

const QUICK = ['DEL','BOM','BLR','MAA','HYD','CCU','COK','AMD','GOI','JAI','PNQ','GAU']

function AirportDropdown({ label, value, onChange, icon }: { label:string; value:string; onChange:(v:string)=>void; icon: React.ReactNode }) {
  const [open, setOpen]         = useState(false)
  const [query, setQuery]       = useState('')
  const [results, setResults]   = useState<Airport[]>([])
  const [selected, setSelected] = useState<Airport|null>(null)
  const wrap   = useRef<HTMLDivElement>(null)
  const search = useRef<HTMLInputElement>(null)

  useEffect(() => {
    const fn = (e:MouseEvent) => { if (wrap.current && !wrap.current.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', fn)
    return () => document.removeEventListener('mousedown', fn)
  }, [])

  useEffect(() => {
    if (!value) { setSelected(null); return }
    supabase.from('airports').select('*').eq('iata_code', value).single()
      .then(({ data }) => { if (data) setSelected(data as Airport) })
  }, [value])

  useEffect(() => {
    if (!open) return
    if (!query.trim()) {
      supabase.from('airports').select('*').eq('is_active',true).in('iata_code',QUICK).order('city').limit(12)
        .then(({ data }) => setResults((data||[]) as Airport[]))
      return
    }
    const q = query.trim()
    supabase.from('airports').select('*').eq('is_active',true)
      .or(`iata_code.ilike.${q.toUpperCase()}%,city.ilike.%${q}%,name.ilike.%${q}%`)
      .order('city').limit(10)
      .then(({ data }) => setResults((data||[]) as Airport[]))
  }, [query, open])

  return (
    <div ref={wrap} style={{ position:'relative' }}>
      <label className="field-label">{label}</label>
      <div className="inp-wrap">
        <span className="inp-icon">{icon}</span>
        <input
          className="inp"
          value={selected ? `${selected.city} (${selected.iata_code})` : value}
          readOnly
          placeholder={label === 'From' ? 'New Delhi (DEL)' : 'Mumbai (BOM)'}
          onClick={() => { setOpen(true); setTimeout(() => search.current?.focus(), 50) }}
          onChange={() => {}}
          style={{ cursor:'pointer' }}
        />
      </div>
      {open && (
        <div style={{ position:'absolute', top:'100%', left:0, right:0, zIndex:200, background:'#fff', border:'1px solid #131210', borderTop:'none', boxShadow:'0 12px 32px rgba(19,18,16,.14)' }}>
          <div style={{ padding:'8px 12px', borderBottom:'1px solid #efefed' }}>
            <input ref={search} value={query} onChange={e=>setQuery(e.target.value)}
              placeholder="City, airport or IATA code..."
              style={{ width:'100%', border:'none', outline:'none', fontSize:'.875rem', color:'#131210', background:'transparent', fontFamily:"'Instrument Sans',sans-serif" }}
            />
          </div>
          {!query && <div style={{ padding:'6px 12px 3px', fontSize:'.6rem', fontWeight:600, letterSpacing:'.12em', textTransform:'uppercase', color:'#c8c6c2', fontFamily:"'Martian Mono',monospace" }}>Popular airports</div>}
          <div style={{ maxHeight:'220px', overflowY:'auto' }}>
            {results.map(ap => (
              <button key={ap.iata_code} type="button"
                onClick={() => { onChange(ap.iata_code); setOpen(false); setQuery('') }}
                style={{ width:'100%', textAlign:'left', padding:'10px 12px', display:'flex', alignItems:'center', gap:'12px', background:ap.iata_code===value?'#f6f4f0':'transparent', border:'none', borderBottom:'1px solid #efefed', cursor:'pointer', fontFamily:"'Instrument Sans',sans-serif" }}
                onMouseEnter={e=>(e.currentTarget.style.background='#f6f4f0')}
                onMouseLeave={e=>(e.currentTarget.style.background=ap.iata_code===value?'#f6f4f0':'transparent')}
              >
                <div style={{ width:'42px', height:'32px', background:ap.iata_code===value?'#131210':'#f6f4f0', border:'1px solid #efefed', display:'flex', alignItems:'center', justifyContent:'center', flexShrink:0 }}>
                  <span style={{ fontFamily:"'Martian Mono',monospace", fontSize:'.68rem', fontWeight:700, color:ap.iata_code===value?'#fff':'#e8191a' }}>{ap.iata_code}</span>
                </div>
                <div style={{ flex:1, minWidth:0 }}>
                  <div style={{ fontSize:'.875rem', fontWeight:600, color:'#131210', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{ap.city}</div>
                  <div style={{ fontSize:'.72rem', color:'#9b9890', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{ap.name}</div>
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
  const tomorrow = format(addDays(new Date(),1),'yyyy-MM-dd')
  const [form, setForm] = useState({ origin:'DEL', destination:'BOM', departure_date:tomorrow, return_date:'', adults:1, cabin_class:'ECONOMY', trip_type:'ONE_WAY' as 'ONE_WAY'|'ROUND_TRIP' })
  const [activeTab, setActiveTab] = useState('One Way')

  const swap = () => setForm(f => ({ ...f, origin:f.destination, destination:f.origin }))
  const submit = (e:React.FormEvent) => {
    e.preventDefault()
    const p = new URLSearchParams({ origin:form.origin, destination:form.destination, departure_date:form.departure_date, adults:String(form.adults), cabin_class:form.cabin_class, ...(form.return_date?{return_date:form.return_date}:{}) })
    router.push(`/flights?${p}`)
  }

  const planeIcon = <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M17.8 19.2L16 11l3.5-3.5C21 6 21 4 19.5 2.5S18 2 16.5 3.5L13 7 4.8 6.2c-.5-.1-.9.1-1.1.5L2 8.9c-.2.4-.1.9.2 1.2l4.6 4.1-1.5 6.4 2.8 2.8 5.3-3.2 4.1 4.6c.3.4.8.5 1.2.2l1.1-1.2c.4-.2.6-.6.5-1.1z"/></svg>
  const pinIcon   = <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0118 0z"/><circle cx="12" cy="10" r="3"/></svg>

  return (
    <form onSubmit={submit}>
      <div className="trip-tabs">
        {['One Way','Round Trip','Multi-city'].map(t => (
          <button key={t} type="button" className={`trip-tab${activeTab===t?' active':''}`} onClick={() => setActiveTab(t)}>{t}</button>
        ))}
      </div>

      <div className="form-grid-2">
        <AirportDropdown label="From" value={form.origin} onChange={v=>setForm(f=>({...f,origin:v}))} icon={planeIcon} />
        <div className="swap-col">
          <button type="button" className="swap-btn" onClick={swap} title="Swap">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M7 16V4m0 0L3 8m4-4l4 4M17 8v12m0 0l4-4m-4 4l-4-4"/></svg>
          </button>
        </div>
        <AirportDropdown label="To" value={form.destination} onChange={v=>setForm(f=>({...f,destination:v}))} icon={pinIcon} />
      </div>

      <div className="form-grid-4">
        <div>
          <label className="field-label">Departure</label>
          <input type="date" className="inp" value={form.departure_date} min={tomorrow} required onChange={e=>setForm(f=>({...f,departure_date:e.target.value}))} />
        </div>
        <div>
          <label className="field-label">Return</label>
          <input type="date" className="inp" value={form.return_date} min={form.departure_date} onChange={e=>setForm(f=>({...f,return_date:e.target.value,trip_type:e.target.value?'ROUND_TRIP':'ONE_WAY'}))} />
        </div>
        <div>
          <label className="field-label">Passengers</label>
          <select className="inp" value={form.adults} onChange={e=>setForm(f=>({...f,adults:+e.target.value}))}>
            {[1,2,3,4,5,6,7,8,9].map(n=><option key={n} value={n}>{n} {n===1?'Adult':'Adults'}</option>)}
          </select>
        </div>
        <div>
          <label className="field-label">Class</label>
          <select className="inp" value={form.cabin_class} onChange={e=>setForm(f=>({...f,cabin_class:e.target.value}))}>
            <option value="ECONOMY">Economy</option>
            <option value="PREMIUM_ECONOMY">Premium Economy</option>
            <option value="BUSINESS">Business</option>
            <option value="FIRST">First</option>
          </select>
        </div>
      </div>

      <button type="submit" className="search-submit">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg>
        SEARCH FLIGHTS
      </button>
    </form>
  )
}
