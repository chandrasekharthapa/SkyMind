"use client";

import { useReducer, useState } from "react";
import { useRouter } from "next/navigation";
import { format, addDays } from "date-fns";
import { Search as SearchIcon, ArrowLeftRight } from "lucide-react";
import type { FlightSearchParams, CabinClass } from "@/types";
import AirportDropdown from "./AirportDropdown";
import PassengerSelector from "./PassengerSelector";

type State = {
  origin: string;
  originDisplay: string;
  destination: string;
  destinationDisplay: string;
  departure_date: string;
  return_date: string;
  adults: number;
  children: number;
  infants: number;
  cabin_class: CabinClass;
  trip_type: "ONE_WAY" | "ROUND_TRIP";
};

type Action = 
  | { type: 'SET_FIELD'; field: keyof State; value: any }
  | { type: 'SET_PASSENGERS'; adults: number; children: number; infants: number }
  | { type: 'SWAP_LOCATIONS' };

function searchReducer(state: State, action: Action): State {
  switch (action.type) {
    case 'SET_FIELD':
      return { ...state, [action.field]: action.value };
    case 'SET_PASSENGERS':
      return { ...state, adults: action.adults, children: action.children, infants: action.infants };
    case 'SWAP_LOCATIONS':
      return { 
        ...state, 
        origin: state.destination, 
        originDisplay: state.destinationDisplay,
        destination: state.origin,
        destinationDisplay: state.originDisplay 
      };
    default:
      return state;
  }
}

const CITY_NAMES: Record<string, string> = {
  DEL: "New Delhi", BOM: "Mumbai", BLR: "Bengaluru", HYD: "Hyderabad",
  MAA: "Chennai", CCU: "Kolkata", AMD: "Ahmedabad", COK: "Kochi",
  DXB: "Dubai", LHR: "London", SIN: "Singapore", JFK: "New York",
  BKK: "Bangkok", CDG: "Paris", AMS: "Amsterdam", FRA: "Frankfurt",
  PNQ: "Pune", JAI: "Jaipur", ATQ: "Amritsar", LKO: "Lucknow",
  BHO: "Bhopal", IXC: "Chandigarh", VNS: "Varanasi", GAU: "Guwahati",
  PAT: "Patna", BBI: "Bhubaneswar", SXR: "Srinagar",
};

function iataToDisplay(code: string): string {
  const city = CITY_NAMES[code.toUpperCase()];
  return city ? `${city} (${code.toUpperCase()})` : code.toUpperCase();
}

interface FlightSearchFormProps {
  initialData?: Partial<FlightSearchParams>;
  onSearch?: (params: FlightSearchParams) => void;
  mode?: "search" | "predict";
  variant?: "standard" | "slim";
}

export default function FlightSearchForm({ initialData, onSearch, mode = "search", variant = "standard" }: FlightSearchFormProps) {
  const router = useRouter();
  const today = format(new Date(), "yyyy-MM-dd");
  const defaultDeparture = format(addDays(new Date(), 7), "yyyy-MM-dd");

  const [state, dispatch] = useReducer(searchReducer, {
    origin: initialData?.origin || "DEL",
    originDisplay: initialData?.origin ? iataToDisplay(initialData.origin) : "New Delhi (DEL)",
    destination: initialData?.destination || "BOM",
    destinationDisplay: initialData?.destination ? iataToDisplay(initialData.destination) : "Mumbai (BOM)",
    departure_date: initialData?.departure_date || defaultDeparture,
    return_date: initialData?.return_date || "",
    adults: Number(initialData?.adults || 1),
    children: Number(initialData?.children || 0),
    infants: Number(initialData?.infants || 0),
    cabin_class: (initialData?.cabin_class as CabinClass) || "ECONOMY",
    trip_type: initialData?.return_date ? "ROUND_TRIP" : "ONE_WAY"
  });

  const [error, setError] = useState("");

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!state.origin || !state.destination) { setError("Select both locations."); return; }
    if (state.origin === state.destination) { setError("Locations must differ."); return; }
    if (state.trip_type === "ROUND_TRIP" && !state.return_date) { setError("Select return date."); return; }
    
    setError("");

    const params: FlightSearchParams = {
      origin: state.origin,
      destination: state.destination,
      departure_date: state.departure_date,
      adults: state.adults,
      children: state.children,
      infants: state.infants,
      cabin_class: state.cabin_class,
      ...(state.trip_type === "ROUND_TRIP" ? { return_date: state.return_date } : {}),
    };

    if (onSearch) {
      onSearch(params);
    } else {
      const p = new URLSearchParams();
      Object.entries(params).forEach(([k, v]) => p.set(k, String(v)));
      router.push(`/flights?${p.toString()}`);
    }
  };

  return (
    <div className={`ui-search-form ${variant === 'slim' ? 'is-slim' : ''}`} 
      style={{ 
        padding: variant === 'slim' ? '0' : 'var(--ui-space-lg)', 
        background: variant === 'slim' ? 'transparent' : 'var(--white)', 
        border: variant === 'slim' ? 'none' : '1px solid var(--grey1)', 
        borderRadius: 'var(--ui-radius-xl)', 
        boxShadow: variant === 'slim' ? 'none' : '0 4px 24px rgba(0,0,0,0.02)' 
      }}>
      
      {/* Trip Type Toggle */}
      {mode !== "predict" && (
        <div className="ui-tabs" style={{ marginBottom: variant === 'slim' ? 16 : 24, borderBottom: "1px solid var(--grey1)", paddingBottom: 12 }}>
          <button type="button" onClick={() => dispatch({ type: 'SET_FIELD', field: 'trip_type', value: 'ONE_WAY' })} 
            className={`ui-tab-btn ${state.trip_type === 'ONE_WAY' ? 'active' : ''}`}>ONE WAY</button>
          <button type="button" onClick={() => dispatch({ type: 'SET_FIELD', field: 'trip_type', value: 'ROUND_TRIP' })} 
            className={`ui-tab-btn ${state.trip_type === 'ROUND_TRIP' ? 'active' : ''}`}>ROUND TRIP</button>
        </div>
      )}

      <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: variant === 'slim' ? "16px" : "24px" }}>
        {/* Main Search Logic */}
        {mode === "predict" ? (
          <div className="predict-box-grid">
              <div style={{ display: "flex", flexDirection: "column", gap: "0px" }}>
                <AirportDropdown
                  label="From"
                  value={state.origin}
                  displayValue={state.originDisplay}
                  onChange={(iata, disp) => {
                    dispatch({ type: 'SET_FIELD', field: 'origin', value: iata });
                    dispatch({ type: 'SET_FIELD', field: 'originDisplay', value: disp });
                  }}
                  placeholder="Departure City"
                />
                <div className="swap-wrapper-vertical">
                  <button type="button" onClick={() => dispatch({ type: 'SWAP_LOCATIONS' })} className="ui-btn ui-btn-white ui-swap-btn-v"><ArrowLeftRight /></button>
                </div>
                <AirportDropdown
                  label="To"
                  value={state.destination}
                  displayValue={state.destinationDisplay}
                  onChange={(iata, disp) => {
                    dispatch({ type: 'SET_FIELD', field: 'destination', value: iata });
                    dispatch({ type: 'SET_FIELD', field: 'destinationDisplay', value: disp });
                  }}
                  placeholder="Arrival City"
                />
              </div>
            <div>
              <label className="ui-field-label">Departure Date</label>
              <input type="date" className="ui-input" value={state.departure_date} min={today} onChange={e => dispatch({ type: 'SET_FIELD', field: 'departure_date', value: e.target.value })} />
            </div>
            <button type="submit" className="ui-btn ui-btn-red" style={{ height: 56, fontSize: "1rem", marginTop: 8 }}>
              <SearchIcon /> GET AI FORECAST
            </button>
          </div>
        ) : (
          <div className="standard-search-grid">
            <div className="locations-row">
              <AirportDropdown
                label="From"
                value={state.origin}
                displayValue={state.originDisplay}
                onChange={(iata, disp) => {
                  dispatch({ type: 'SET_FIELD', field: 'origin', value: iata });
                  dispatch({ type: 'SET_FIELD', field: 'originDisplay', value: disp });
                }}
                placeholder="Departure City"
              />
              <div className="swap-wrapper">
                <button type="button" onClick={() => dispatch({ type: 'SWAP_LOCATIONS' })} className="ui-btn ui-btn-white ui-swap-btn"><ArrowLeftRight /></button>
              </div>
              <AirportDropdown
                label="To"
                value={state.destination}
                displayValue={state.destinationDisplay}
                onChange={(iata, disp) => {
                  dispatch({ type: 'SET_FIELD', field: 'destination', value: iata });
                  dispatch({ type: 'SET_FIELD', field: 'destinationDisplay', value: disp });
                }}
                placeholder="Arrival City"
              />
            </div>

            <div className="dates-row">
              <div style={{ flex: 1 }}>
                <label className="ui-field-label">Departure</label>
                <input type="date" className="ui-input" value={state.departure_date} min={today} onChange={e => dispatch({ type: 'SET_FIELD', field: 'departure_date', value: e.target.value })} />
              </div>
              {state.trip_type === "ROUND_TRIP" && (
                <div style={{ flex: 1 }}>
                  <label className="ui-field-label">Return</label>
                  <input type="date" className="ui-input" value={state.return_date} min={state.departure_date} onChange={e => dispatch({ type: 'SET_FIELD', field: 'return_date', value: e.target.value })} />
                </div>
              )}
            </div>
            
            <div className="options-row">
              <div style={{ flex: 1 }}>
                <PassengerSelector
                  adults={state.adults} children={state.children} infants={state.infants}
                  onChange={(a, c, i) => dispatch({ type: 'SET_PASSENGERS', adults: a, children: c, infants: i })}
                />
              </div>
              
              <div style={{ flex: 1 }}>
                <label className="ui-field-label">Cabin Class</label>
                <select className="ui-input" value={state.cabin_class} onChange={e => dispatch({ type: 'SET_FIELD', field: 'cabin_class', value: e.target.value as CabinClass })}>
                  <option value="ECONOMY">Economy</option>
                  <option value="PREMIUM_ECONOMY">Premium</option>
                  <option value="BUSINESS">Business</option>
                  <option value="FIRST">First Class</option>
                </select>
              </div>
            </div>

            <button type="submit" className="ui-btn ui-btn-red" style={{ height: 60, fontSize: "1rem", marginTop: 8 }}>
              <SearchIcon /> SEARCH FLIGHTS
            </button>
          </div>
        )}

        {error && (
          <div style={{ color: "var(--red)", fontSize: "12px", fontWeight: 700, fontFamily: "var(--fm)", textAlign: "center" }}>
            {error}
          </div>
        )}
      </form>

      <style jsx>{`
        .ui-tab-btn {
          background: none;
          border: none;
          font-family: var(--fm);
          font-size: 11px;
          font-weight: 700;
          color: var(--grey3);
          padding: 8px 16px;
          cursor: pointer;
          letter-spacing: 0.1em;
          position: relative;
          transition: all 0.2s;
        }
        .ui-tab-btn.active { color: var(--red); }
        .ui-tab-btn.active::after {
          content: "";
          position: absolute;
          bottom: -13px;
          left: 0;
          right: 0;
          height: 2px;
          background: var(--red);
        }

        .predict-box-grid { display: flex; flex-direction: column; gap: 20px; }
        .standard-search-grid { display: flex; flex-direction: column; gap: 24px; }
        
        .locations-row {
          display: grid;
          grid-template-columns: 1fr auto 1fr;
          gap: 12px;
          align-items: end;
          position: relative;
        }
        .swap-wrapper { padding-bottom: 4px; }
        .swap-wrapper-vertical { display: flex; justify-content: center; height: 0; position: relative; z-index: 5; }
        
        .ui-swap-btn { width: 44px; height: 44px; border-radius: 50%; padding: 0; box-shadow: var(--shadow-sm); display: flex; align-items: center; justify-content: center; }
        .ui-swap-btn-v { 
          width: 36px; 
          height: 36px; 
          border-radius: 50%; 
          padding: 0; 
          position: absolute; 
          left: 50%;
          transform: translateX(-50%) translateY(-18px) rotate(90deg);
          border: 1px solid var(--grey1); 
          background: #fff; 
          box-shadow: var(--shadow-sm); 
          z-index: 5;
          display: flex;
          align-items: center;
          justify-content: center;
        }
        .dates-row, .options-row {
          display: flex;
          gap: 16px;
          align-items: end;
        }
        .dates-row > div, .options-row > div { flex: 1; min-width: 0; }
        
        .slim-fields-row {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
          gap: 12px;
        }

        @media (max-width: 900px) {
          .details-row { grid-template-columns: 1fr; gap: 20px; }
        }

        @media (max-width: 768px) {
          .locations-row { grid-template-columns: 1fr; gap: 0; }
          .dates-row, .options-row { flex-direction: column; gap: 16px; align-items: stretch; }
          .swap-wrapper { display: flex; justify-content: center; height: 0; position: relative; z-index: 5; }
          .ui-swap-btn { width: 36px; height: 36px; transform: rotate(90deg); position: absolute; top: -18px; border: 1px solid var(--grey1); background: #fff; display: flex; align-items: center; justify-content: center; }
        }
      `}</style>
    </div>
  );
}
