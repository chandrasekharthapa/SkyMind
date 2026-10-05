"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { format, addDays } from "date-fns";
import { getApiBase } from "@/lib/api";
import { airlineName } from "@/lib/places";

const META: Record<string, { img: string; tag: string; tagClass: string }> = {
  BOM: { img: "https://images.unsplash.com/photo-1570168007204-dfb528c6958f?w=600&q=80&auto=format&fit=crop", tag: "Popular", tagClass: "badge-red" },
  GOI: { img: "https://images.unsplash.com/photo-1587922546307-776227941871?w=600&q=80&auto=format&fit=crop", tag: "Beach", tagClass: "badge-black" },
  BLR: { img: "https://images.unsplash.com/photo-1596176530529-78163a4f7af2?w=600&q=80&auto=format&fit=crop", tag: "Tech", tagClass: "badge-off" },
  MAA: { img: "https://images.unsplash.com/photo-1582510003544-4d00b7f74220?w=600&q=80&auto=format&fit=crop", tag: "Heritage", tagClass: "badge-off" },
  HYD: { img: "https://images.unsplash.com/photo-1598091383021-15ddea10925d?w=600&q=80&auto=format&fit=crop", tag: "Pearls", tagClass: "badge-black" },
  CCU: { img: "https://images.unsplash.com/photo-1558618666-fcd25c85cd64?w=600&q=80&auto=format&fit=crop", tag: "Culture", tagClass: "badge-off" },
};

// The three featured routes from Delhi. Fares come from GET /flights/fare-board:
// the cheapest fare actually collected on that route in the last day. This used
// to fall back to hardcoded prices ("from ₹4,299, 18 flights") whenever the
// lookup failed, which looked exactly like real data. Now a card with no
// collected fare simply says so.
const FEATURED = [
  { origin_code: "DEL", destination_code: "BOM", dest_city: "Mumbai" },
  { origin_code: "DEL", destination_code: "GOI", dest_city: "Goa" },
  { origin_code: "DEL", destination_code: "BLR", dest_city: "Bengaluru" },
];

type BoardRow = {
  origin_code: string;
  destination_code: string;
  departure_date: string;
  airline_code: string | null;
  price: number;
  stops: number | null;
};

type Card = (typeof FEATURED)[number] & { fare: BoardRow | null };

export default function PopularDestinations() {
  const [routes, setRoutes] = useState<Card[]>([]);
  const [loading, setLoading] = useState(true);
  const dep = format(addDays(new Date(), 30), "yyyy-MM-dd");

  useEffect(() => {
    let mounted = true;
    const load = async () => {
      let rows: BoardRow[] = [];
      try {
        const res = await fetch(`${getApiBase()}/flights/fare-board`);
        if (res.ok) rows = ((await res.json()).rows || []) as BoardRow[];
      } catch {
        // Leave rows empty: cards render without a fare.
      }
      if (!mounted) return;
      setRoutes(FEATURED.map(f => ({
        ...f,
        fare: rows.find(r => r.origin_code === f.origin_code && r.destination_code === f.destination_code && r.price > 0) || null,
      })));
      setLoading(false);
    };
    load();
    return () => { mounted = false; };
  }, []);

  const fb = "https://images.unsplash.com/photo-1436491865332-7a61a109cc05?w=600&q=80&auto=format&fit=crop";

  if (loading) {
    return (
      <div className="dest-grid">
        {[0, 1, 2].map(i => (
          <div key={i} className="ui-card" style={{ height: "420px", padding: 0, overflow: "hidden" }}>
            <div className="skel" style={{ height: "260px", width: "100%" }} />
            <div className="dest-body">
              <div className="skel" style={{ height: "12px", width: "30%", marginBottom: "12px" }} />
              <div className="skel" style={{ height: "32px", width: "60%", marginBottom: "24px" }} />
              <div className="ui-flex" style={{ gap: "12px" }}>
                <div className="skel" style={{ height: "16px", width: "25%" }} />
                <div className="skel" style={{ height: "16px", width: "25%" }} />
              </div>
            </div>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="dest-grid">
      {routes.map(r => {
        const m = META[r.destination_code] || { img: fb, tag: "Trending", tagClass: "badge-off" };
        const fare = r.fare;
        const date = fare?.departure_date || dep;
        const url = `/flights?origin=${r.origin_code}&destination=${r.destination_code}&departure_date=${date}&adults=1&cabin_class=ECONOMY`;
        const when = fare
          ? new Date(`${fare.departure_date}T00:00:00`).toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short" })
          : null;

        return (
          <Link key={`${r.origin_code}-${r.destination_code}`} href={url} className="dest-card">
            <div className="dest-img-wrap" style={{ background: "linear-gradient(135deg, #1a1a1a, #3a3a3a)" }}>
              <img
                src={m.img}
                alt=""
                loading="lazy"
                onError={e => { (e.currentTarget as HTMLImageElement).style.visibility = "hidden"; }}
              />
              <div className="dest-img-overlay" />
              <div className="dest-img-label">
                <div className="dest-img-city">{r.dest_city.toUpperCase()}</div>
                <div className="ui-label" style={{ color: "rgba(255,255,255,0.7)" }}>{r.origin_code} TO {r.destination_code}</div>
              </div>
            </div>
            <div className="dest-body">
              <div className="dest-price-row">
                <div>
                  <div className="ui-label" style={{ marginBottom: "4px" }}>{fare ? "LOWEST FARE TODAY" : "TODAY'S FARE"}</div>
                  <div className="dest-price-val">
                    {fare ? `₹${Math.round(fare.price).toLocaleString("en-IN")}` : "Search to see"}
                  </div>
                </div>
              </div>
              <div className="dest-meta">
                {fare ? (
                  <>
                    <div className="dest-meta-item">
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden="true">
                        <rect x="3" y="4" width="18" height="18" rx="2" /><line x1="16" y1="2" x2="16" y2="6" /><line x1="8" y1="2" x2="8" y2="6" /><line x1="3" y1="10" x2="21" y2="10" />
                      </svg>
                      {when}
                    </div>
                    <div className="dest-meta-item">
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden="true">
                        <path d="M17.8 19.2L16 11l3.5-3.5C21 6 21 4 19.5 2.5S18 2 16.5 3.5L13 7 4.8 6.2c-.5-.1-.9.1-1.1.5L2 8.9c-.2.4-.1.9.2 1.2l4.6 4.1-1.5 6.4 2.8 2.8 5.3-3.2 4.1 4.6c.3.4.8.5 1.2.2l1.1-1.2c.4-.2.6-.6.5-1.1z" />
                      </svg>
                      {airlineName(fare.airline_code)}{fare.stops === 0 ? " · Non-stop" : ""}
                    </div>
                  </>
                ) : (
                  <div className="dest-meta-item">No fare collected in the last day — tap to search live</div>
                )}
              </div>
            </div>
          </Link>
        );
      })}
    </div>
  );
}
