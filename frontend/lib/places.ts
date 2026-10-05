// Display names for the airports and airlines SkyMind tracks. Codes that are
// not listed fall back to the code itself.

export const CITY_BY_IATA: Record<string, string> = {
  AMD: "Ahmedabad",
  BBI: "Bhubaneswar",
  BLR: "Bengaluru",
  BOM: "Mumbai",
  CCU: "Kolkata",
  COK: "Kochi",
  DEL: "Delhi",
  GOI: "Goa",
  HYD: "Hyderabad",
  IXC: "Chandigarh",
  MAA: "Chennai",
  PNQ: "Pune",
  TRV: "Thiruvananthapuram",
  VTZ: "Visakhapatnam",
  JAI: "Jaipur",
  LKO: "Lucknow",
  GAU: "Guwahati",
  PAT: "Patna",
  SXR: "Srinagar",
  VNS: "Varanasi",
  ATQ: "Amritsar",
  BHO: "Bhopal",
};

export const AIRLINE_BY_CODE: Record<string, string> = {
  "6E": "IndiGo",
  AI: "Air India",
  IX: "Air India Express",
  SG: "SpiceJet",
  QP: "Akasa Air",
  "9I": "Alliance Air",
  S5: "Star Air",
  UK: "Vistara",
};

export function cityName(code: string): string {
  return CITY_BY_IATA[(code || "").toUpperCase()] || (code || "").toUpperCase();
}

export function airlineName(code: string | null | undefined): string {
  if (!code) return "Mixed";
  return AIRLINE_BY_CODE[code.toUpperCase()] || code.toUpperCase();
}
