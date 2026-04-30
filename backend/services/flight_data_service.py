"""
SkyMind proprietary flight data engine.

No external flight APIs are used here. Prices are generated from deterministic
market factors: route baseline, sigmoid demand, inventory pressure, seasonality,
weekday effects, and airline variation.
"""

from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any


ROUTE_BASE_PRICES: dict[tuple[str, str], int] = {
    ("DEL", "BOM"): 4200,
    ("BOM", "DEL"): 4100,
    ("DEL", "BLR"): 4800,
    ("BLR", "DEL"): 4700,
    ("DEL", "MAA"): 5100,
    ("MAA", "DEL"): 5000,
    ("DEL", "HYD"): 4400,
    ("HYD", "DEL"): 4300,
    ("DEL", "CCU"): 3900,
    ("CCU", "DEL"): 3800,
    ("BOM", "BLR"): 3600,
    ("BLR", "BOM"): 3500,
    ("BOM", "GOI"): 3400,
    ("GOI", "BOM"): 3300,
    ("BBI", "DEL"): 3800,
    ("DEL", "BBI"): 3700,
    ("DEL", "DXB"): 9500,
    ("DXB", "DEL"): 9200,
    ("BOM", "DXB"): 8800,
    ("DXB", "BOM"): 8600,
    ("DEL", "LHR"): 32000,
    ("LHR", "DEL"): 31000,
    ("DEL", "SIN"): 14000,
    ("SIN", "DEL"): 13500,
}

ROUTE_DURATIONS: dict[tuple[str, str], int] = {
    ("DEL", "BOM"): 135,
    ("BOM", "DEL"): 130,
    ("DEL", "BLR"): 165,
    ("BLR", "DEL"): 160,
    ("DEL", "MAA"): 175,
    ("MAA", "DEL"): 170,
    ("DEL", "HYD"): 150,
    ("HYD", "DEL"): 145,
    ("DEL", "CCU"): 140,
    ("CCU", "DEL"): 135,
    ("BOM", "BLR"): 100,
    ("BLR", "BOM"): 95,
    ("BOM", "GOI"): 60,
    ("GOI", "BOM"): 55,
    ("BBI", "DEL"): 130,
    ("DEL", "BBI"): 125,
    ("DEL", "DXB"): 210,
    ("DXB", "DEL"): 205,
    ("BOM", "DXB"): 195,
    ("DXB", "BOM"): 190,
    ("DEL", "LHR"): 540,
    ("LHR", "DEL"): 530,
    ("DEL", "SIN"): 360,
    ("SIN", "DEL"): 355,
}

ROUTE_AIRLINES: dict[tuple[str, str], list[str]] = {
    route: ["6E", "AI", "UK", "SG"] for route in ROUTE_BASE_PRICES
}
ROUTE_AIRLINES.update({
    ("DEL", "DXB"): ["EK", "AI", "6E", "FZ"],
    ("DXB", "DEL"): ["EK", "AI", "6E", "FZ"],
    ("BOM", "DXB"): ["EK", "AI", "6E", "G9"],
    ("DXB", "BOM"): ["EK", "AI", "6E", "G9"],
    ("DEL", "LHR"): ["AI", "BA", "UK"],
    ("LHR", "DEL"): ["AI", "BA", "UK"],
    ("DEL", "SIN"): ["SQ", "AI", "6E"],
    ("SIN", "DEL"): ["SQ", "AI", "6E"],
})

AIRLINE_NAMES = {
    "6E": "IndiGo",
    "AI": "Air India",
    "UK": "Vistara",
    "SG": "SpiceJet",
    "EK": "Emirates",
    "FZ": "flydubai",
    "G9": "Air Arabia",
    "BA": "British Airways",
    "SQ": "Singapore Airlines",
}

AIRLINE_VARIATION = {
    "6E": 0.91,
    "SG": 0.88,
    "FZ": 0.95,
    "G9": 0.93,
    "AI": 1.04,
    "UK": 1.12,
    "EK": 1.2,
    "SQ": 1.24,
    "BA": 1.28,
}

PEAK_MONTHS = {1, 5, 6, 10, 12}
SHOULDER_MONTHS = {4, 7, 11}
HOLIDAYS = {(1, 1), (1, 26), (8, 15), (10, 2), (12, 25)}

CABIN_MULTIPLIERS = {
    "ECONOMY": 1.0,
    "PREMIUM_ECONOMY": 1.5,
    "BUSINESS": 2.8,
    "FIRST": 4.5
}


@dataclass(frozen=True)
class PriceContext:
    origin: str
    destination: str
    departure_date: date
    airline: str = "6E"
    seats_available: int = 45
    cabin_class: str = "ECONOMY"
    generated_on: date = field(default_factory=date.today)


def parse_date(value: str | None, fallback_days: int = 14) -> date:
    if not value:
        return date.today() + timedelta(days=fallback_days)
    return datetime.strptime(value, "%Y-%m-%d").date()


def stable_seed(*parts: Any) -> int:
    raw = "|".join(str(part) for part in parts)
    return int(hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12], 16)


def sigmoid_demand(days_until_departure: int) -> float:
    x = (14 - days_until_departure) / 5.5
    return 1.0 + (0.72 / (1.0 + math.exp(-x)))


def inventory_pressure(seats_available: int) -> float:
    seats = max(1, min(60, seats_available))
    pressure = 1.0 + ((60 - seats) / 60) ** 2 * 0.62
    return round(pressure, 4)


def seasonality(departure_date: date) -> float:
    if departure_date.month in PEAK_MONTHS:
        return 1.26
    if departure_date.month in SHOULDER_MONTHS:
        return 1.12
    return 1.0


def weekday_factor(departure_date: date) -> float:
    return {0: 0.97, 4: 1.16, 5: 1.08, 6: 1.14}.get(departure_date.weekday(), 1.0)


def holiday_factor(departure_date: date) -> float:
    marker = (departure_date.month, departure_date.day)
    if marker in HOLIDAYS:
        return 1.24
    if ((departure_date - timedelta(days=1)).month, (departure_date - timedelta(days=1)).day) in HOLIDAYS:
        return 1.1
    if ((departure_date + timedelta(days=1)).month, (departure_date + timedelta(days=1)).day) in HOLIDAYS:
        return 1.1
    return 1.0


def demand_score(days_until_departure: int, departure_date: date, seats_available: int) -> float:
    urgency = min(1.0, sigmoid_demand(days_until_departure) - 1.0)
    season = seasonality(departure_date) - 1.0
    inventory = inventory_pressure(seats_available) - 1.0
    return round(min(1.0, urgency * 0.58 + season * 1.05 + inventory * 0.72), 4)


def calculate_price(ctx: PriceContext, seed: int) -> int:
    """
    Simulate dynamic pricing with deterministic factors + psychological rounding.
    """
    base = ROUTE_BASE_PRICES.get((ctx.origin, ctx.destination), 4500)
    
    # 1. Airline positioning
    airline_mod = AIRLINE_VARIATION.get(ctx.airline, 1.0)
    
    # 2. Advance purchase discount/premium (Sigmoid)
    days = max(0, (ctx.departure_date - date.today()).days)
    if days > 30:
        advance_mod = 0.7 + (0.1 * math.sin(days / 10))
    elif days < 3:
        advance_mod = 1.8 + (0.2 * math.cos(days))
    else:
        advance_mod = 1.0 + (0.5 * math.exp(-days / 12))
        
    # 3. Demand/Inventory noise
    rng = random.Random(seed)
    noise = rng.uniform(0.95, 1.15)
    
    # 4. Weekday effect (Weekends are higher)
    is_weekend = ctx.departure_date.weekday() >= 4 
    weekend_mod = 1.15 if is_weekend else 1.0
    
    # 5. Seasonality
    season_mod = seasonality(ctx.departure_date)
    
    # 6. Cabin Class positioning
    cabin_mod = CABIN_MULTIPLIERS.get(ctx.cabin_class.upper(), 1.0)
    
    price = int(base * airline_mod * advance_mod * weekend_mod * season_mod * cabin_mod * noise)
    
    # 6. Psychological Rounding
    if price > 1000:
        hundreds = (price // 100) * 100
        rem = price % 100
        price = hundreds + (99 if rem > 50 else 49)
            
    return price


class FlightDataService:
    def route_supported(self, origin: str, destination: str) -> bool:
        return (origin.upper(), destination.upper()) in ROUTE_BASE_PRICES

    def market_snapshot(self, origin: str, destination: str, departure_date: str | None, cabin_class: str = "ECONOMY") -> dict[str, Any]:
        dep_date = parse_date(departure_date)
        route = (origin.upper().strip(), destination.upper().strip())
        airlines = ROUTE_AIRLINES.get(route, ["6E", "AI"])
        seed = stable_seed(*route, dep_date.isoformat())
        rng = random.Random(seed)
        days = max(0, (dep_date - date.today()).days)
        seats = max(1, min(60, int(8 + days * 1.3 + rng.randint(-4, 8))))
        prices = []

        for idx, airline in enumerate(airlines):
            ctx = PriceContext(route[0], route[1], dep_date, airline, max(1, seats - idx * 4), cabin_class=cabin_class)
            prices.append(calculate_price(ctx, seed + idx))

        current_price = float(round(min(prices), 2))
        return {
            "origin": route[0],
            "destination": route[1],
            "departure_date": dep_date.isoformat(),
            "days_until_departure": days,
            "airline": airlines[0],
            "seats_available": seats,
            "current_price": current_price,
            "market_low": min(prices),
            "market_high": max(prices),
            "demand_score": demand_score(days, dep_date, seats),
            "seasonality_factor": seasonality(dep_date),
            "inventory_pressure": inventory_pressure(seats),
        }

    async def search_flights(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        adults: int = 1,
        children: int = 0,
        infants: int = 0,
        cabin_class: str = "ECONOMY",
        max_results: int = 20,
        return_date: str | None = None,
    ) -> dict[str, Any]:
        snapshot = self.market_snapshot(origin, destination, departure_date, cabin_class=cabin_class)
        dep_date = parse_date(departure_date)
        ret_date = parse_date(return_date) if return_date else None
        
        duration = ROUTE_DURATIONS.get((snapshot["origin"], snapshot["destination"]), 120)
        seed = stable_seed(snapshot["origin"], snapshot["destination"], dep_date.isoformat(), "offers", return_date or "")
        rng = random.Random(seed)
        offers = []

        for airline_idx, airline in enumerate(ROUTE_AIRLINES.get((snapshot["origin"], snapshot["destination"]), ["6E"])):
            for slot_idx, slot_hour in enumerate([2, 8, 13, 18, 22]):
                seats = max(1, snapshot["seats_available"] - (airline_idx * 5) - (slot_idx * 2))
                
                # Outbound Price
                out_price = calculate_price(
                    PriceContext(snapshot["origin"], snapshot["destination"], dep_date, airline, seats, cabin_class=cabin_class),
                    seed + airline_idx + slot_idx,
                )
                
                # Return Price if applicable
                in_price = 0
                if ret_date:
                    in_price = calculate_price(
                        PriceContext(snapshot["destination"], snapshot["origin"], ret_date, airline, seats + 5, cabin_class=cabin_class),
                        seed + airline_idx + slot_idx + 100,
                    )

                time_multiplier = 1.1 if slot_hour in [6, 18] else 1.0
                total_unit_price = (out_price + in_price) * time_multiplier
                total_price = total_unit_price * max(1, adults)
                
                minute = (rng.randint(0, 11) * 5) + (airline_idx * 7) % 60
                depart = datetime.combine(dep_date, datetime.min.time()).replace(hour=slot_hour, minute=minute % 60)
                var_duration = duration + rng.randint(-10, 10)
                arrive = depart + timedelta(minutes=var_duration)
                
                # Generate Outbound Segments
                segments = [{
                    "flight_number": f"{airline}{100 + (airline_idx * 10) + slot_idx + rng.randint(1, 9)}",
                    "airline_code": airline,
                    "airline_name": AIRLINE_NAMES.get(airline, airline),
                    "origin": snapshot["origin"],
                    "destination": snapshot["destination"],
                    "departure_time": depart.isoformat(),
                    "arrival_time": arrive.isoformat(),
                    "duration": f"PT{var_duration // 60}H{var_duration % 60}M",
                    "cabin": cabin_class,
                    "stops": 0,
                }]

                itineraries = [{
                    "duration": f"PT{var_duration // 60}H{var_duration % 60}M",
                    "segments": segments,
                }]

                # Generate Inbound Segments if Round Trip
                if ret_date:
                    ret_depart = datetime.combine(ret_date, datetime.min.time()).replace(hour=(slot_hour + 2) % 24, minute=(minute + 15) % 60)
                    ret_var_duration = ROUTE_DURATIONS.get((snapshot["destination"], snapshot["origin"]), 120) + rng.randint(-10, 10)
                    ret_arrive = ret_depart + timedelta(minutes=ret_var_duration)
                    
                    ret_segments = [{
                        "flight_number": f"{airline}{800 + (airline_idx * 10) + slot_idx + rng.randint(1, 9)}",
                        "airline_code": airline,
                        "airline_name": AIRLINE_NAMES.get(airline, airline),
                        "origin": snapshot["destination"],
                        "destination": snapshot["origin"],
                        "departure_time": ret_depart.isoformat(),
                        "arrival_time": ret_arrive.isoformat(),
                        "duration": f"PT{ret_var_duration // 60}H{ret_var_duration % 60}M",
                        "cabin": cabin_class,
                        "stops": 0,
                    }]
                    
                    itineraries.append({
                        "duration": f"PT{ret_var_duration // 60}H{ret_var_duration % 60}M",
                        "segments": ret_segments,
                    })

                offers.append({
                    "id": f"SKY-{snapshot['origin']}-{snapshot['destination']}-{airline}-{airline_idx}-{slot_idx}",
                    "source": "SKYMIND_INTELLIGENCE",
                    "price": {"total": float(total_price), "base": float(round(total_price * 0.82, 2)), "currency": "INR"},
                    "itineraries": itineraries,
                    "primary_airline": airline,
                    "primary_airline_name": AIRLINE_NAMES.get(airline, airline),
                    "seats_available": seats,
                })

        offers.sort(key=lambda item: item["price"]["total"])
        return {
            "flights": offers[:max_results],
            "count": min(len(offers), max_results),
            "origin_iata": snapshot["origin"],
            "destination_iata": snapshot["destination"],
            "data_source": "SKYMIND_INTELLIGENCE",
        }

    def format_for_training(self, origin: str, destination: str, departure_date: str) -> list[dict[str, Any]]:
        dep_date = parse_date(departure_date)
        route = (origin.upper().strip(), destination.upper().strip())
        airlines = ROUTE_AIRLINES.get(route, ["6E", "AI"])
        days = max(0, (dep_date - date.today()).days)
        records = []
        
        for airline in airlines:
            seed = stable_seed(*route, airline, dep_date.isoformat())
            rng = random.Random(seed)
            seats = max(1, min(60, int(8 + days * 1.3 + rng.randint(-4, 8))))
            ctx = PriceContext(route[0], route[1], dep_date, airline, seats)
            price = calculate_price(ctx, seed)
            
            # Simple simulation for past prices
            ctx_1d = PriceContext(route[0], route[1], dep_date, airline, seats + rng.randint(0, 3))
            price_1d = calculate_price(ctx_1d, seed + 1)
            ctx_3d = PriceContext(route[0], route[1], dep_date, airline, seats + rng.randint(2, 7))
            price_3d = calculate_price(ctx_3d, seed + 3)
            
            dep_hour = rng.randint(6, 22)
            
            records.append({
                "origin_code": route[0],
                "destination_code": route[1],
                "airline_code": airline,
                "price": price,
                "currency": "INR",
                "departure_date": dep_date.isoformat(),
                "days_until_dep": days,
                "urgency": round(1 / (days + 1), 4),
                "day_of_week": dep_date.weekday(),
                "month": dep_date.month,
                "week_of_year": dep_date.isocalendar()[1] if isinstance(dep_date.isocalendar(), tuple) else dep_date.isocalendar().week,
                "is_holiday": True if holiday_factor(dep_date) > 1.0 else False,
                "is_weekend": True if dep_date.weekday() >= 5 else False,
                "seats_available": seats,
                "recorded_at": datetime.now().isoformat(),
                "is_live": False,
                "training_weight": 1.0
            })
            
        return records

    def proprietary_training_rows(self, days: int = 210) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        today = date.today()
        for route in ROUTE_BASE_PRICES:
            for offset in range(1, min(days, 90)):
                dep_date = today + timedelta(days=offset)
                for airline in ROUTE_AIRLINES.get(route, ["6E", "AI"]):
                    seed = stable_seed(route[0], route[1], airline, dep_date.isoformat())
                    seats = 1 + seed % 60
                    ctx = PriceContext(route[0], route[1], dep_date, airline, seats)
                    rows.append({
                        "origin_code": route[0],
                        "destination_code": route[1],
                        "airline_code": airline,
                        "price": calculate_price(ctx, seed),
                        "days_until_dep": offset,
                        "day_of_week": dep_date.weekday(),
                        "month": dep_date.month,
                        "week_of_year": dep_date.isocalendar().week,
                        "seats_available": seats,
                        "demand_score": demand_score(offset, dep_date, seats),
                        "seasonality_factor": seasonality(dep_date),
                    })
        return rows


flight_data_service = FlightDataService()
