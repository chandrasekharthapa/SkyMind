"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { format, addDays } from "date-fns";

const META: Record<string, { img:string; tag:string; tagClass:string }> = {
  BOM: { img:"https://images.unsplash.com/photo-1570168007204-dfb528c6958f?w=600&q=80&auto=format&fit=crop", tag:"Popular", tagClass:"badge-red" },
  GOI: { img:"https://images.unsplash.com/photo-1587922546307-776227941871?w=600&q=80&auto=format&fit=crop", tag:"Beach", tagClass:"badge-black" },
  BLR: { img:"https://images.unsplash.com/photo-1596176530529-78163a4f7af2?w=600&q=80&auto=format&fit=crop", tag:"Tech", tagClass:"badge-off" },
  MAA: { img:"https://images.unsplash.com/photo-1582510003544-4d00b7f74220?w=600&q=80&auto=format&fit=crop", tag:"Heritage", tagClass:"badge-off" },
  HYD: { img:"https://images.unsplash.com/photo-1598091383021-15ddea10925d?w=600&q=80&auto=format&fit=crop", tag:"Pearls", tagClass:"badge-black" },
  CCU: { img:"https://images.unsplash.com/photo-1558618666-fcd25c85cd64?w=600&q=80&auto=format&fit=crop", tag:"Culture", tagClass:"badge-off" },
};

const FALLBACK_ROUTES = [
  { origin_code:"DEL", destination_code:"BOM", dest_city:"Mumbai",    min_price_inr:4299, avg_price_inr:6200, flights_per_day:18, avg_duration_min:130 },
  { origin_code:"DEL", destination_code:"GOI", dest_city:"Goa",       min_price_inr:3899, avg_price_inr:5800, flights_per_day:12, avg_duration_min:150 },
  { origin_code:"DEL", destination_code:"BLR", dest_city:"Bengaluru", min_price_inr:5199, avg_price_inr:7100, flights_per_day:22, avg_duration_min:165 },
];

export default function PopularDestinations() {
  const [routes, setRoutes] = useState<typeof FALLBACK_ROUTES>([]);
  const [loading, setLoading] = useState(true);
  const dep = format(addDays(new Date(),30),"yyyy-MM-dd");

  useEffect(() => {
    let mounted = true;
    const load = async () => {
      try {
        const { supabase } = await import("@/lib/supabase");
        const { data, error } = await supabase.from("v_domestic_routes").select("origin_code,destination_code,dest_city,min_price_inr,avg_price_inr,flights_per_day,avg_duration_min").eq("origin_code","DEL").order("flights_per_day",{ascending:false}).limit(3);
        if (mounted) setRoutes(!error && data && data.length>0 ? data : FALLBACK_ROUTES);
      } catch { if (mounted) setRoutes(FALLBACK_ROUTES); }
      finally { if (mounted) setLoading(false); }
    };
    load();
    return () => { mounted = false; };
  }, []);

  const fb = "https://images.unsplash.com/photo-1436491865332-7a61a109cc05?w=600&q=80&auto=format&fit=crop";

  if (loading) {
    return (
      <div className="dest-grid">
        {[0,1,2].map(i => (
          <div key={i} className="dest-card">
            <div className="dest-img-wrap"><div className="skel" style={{ height:"100%" }} /></div>
            <div className="dest-body"><div className="skel" style={{ height:14, marginBottom:8, width:"60%" }} /><div className="skel" style={{ height:28, width:"40%" }} /></div>
          </div>
        ))}
      </div>
    );
  }

  const data = routes.length ? routes : FALLBACK_ROUTES;
  return (
    <div className="dest-grid">
      {data.map(r => {
        const m = META[r.destination_code] || { img:fb, tag:"Trending", tagClass:"badge-off" };
        const dh = Math.floor((r.avg_duration_min||90)/60);
        const dm = (r.avg_duration_min||90)%60;
        const url = `/flights?origin=${r.origin_code}&destination=${r.destination_code}&departure_date=${dep}&adults=1&cabin_class=ECONOMY`;

        return (
          <Link key={`${r.origin_code}-${r.destination_code}`} href={url} className="dest-card">
            <div className="dest-img-wrap">
              <img src={m.img} alt={r.dest_city} loading="lazy" />
              <div className="dest-img-overlay" />
              <div className="dest-img-label">
                <div className="dest-img-city">{r.dest_city.toUpperCase()}</div>
                <div className="dest-img-code">{r.origin_code} → {r.destination_code}</div>
              </div>
            </div>
            <div className="dest-body">
              <div className="dest-price-row">
                <div>
                  <div className="dest-price-from">From</div>
                  <div className="dest-price-val">₹{Math.round(r.min_price_inr).toLocaleString("en-IN")}</div>
                </div>
                <span className={`badge ${m.tagClass}`}>{m.tag}</span>
              </div>
              <div className="dest-meta">
                <div className="dest-meta-item">
                  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M17.8 19.2L16 11l3.5-3.5C21 6 21 4 19.5 2.5S18 2 16.5 3.5L13 7 4.8 6.2c-.5-.1-.9.1-1.1.5L2 8.9c-.2.4-.1.9.2 1.2l4.6 4.1-1.5 6.4 2.8 2.8 5.3-3.2 4.1 4.6c.3.4.8.5 1.2.2l1.1-1.2c.4-.2.6-.6.5-1.1z"/></svg>
                  {r.flights_per_day} daily
                </div>
                <div className="dest-meta-item">
                  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                  {dh}h{dm>0?` ${dm}m`:""}
                </div>
                <div style={{ marginLeft:"auto", fontSize:".7rem", color:"var(--grey3)", fontFamily:"var(--fm)" }}>
                  avg ₹{(r.avg_price_inr/1000).toFixed(1)}k
                </div>
              </div>
            </div>
          </Link>
        );
      })}
    </div>
  );
}
