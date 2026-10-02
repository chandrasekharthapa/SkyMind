"""Chat Response Builder.

Translates internal canonical objects (NormalizedFlight, PredictionResponse, etc.)
into human-friendly structured presentation templates (tables, markdown lists, summary cards).
"""

from typing import List, Dict, Any, Optional

class ChatResponseBuilder:
    @staticmethod
    def build_flight_search_summary(flights: List[Dict[str, Any]], origin: str, destination: str) -> str:
        """Format flight search results into a clean markdown table list."""
        if not flights:
            return f"No flights found from {origin} to {destination}."

        lines = [
            f"### Available flights from {origin} to {destination}:",
            "",
            "| Airline | Flight No | Departure | Duration | Stops | Price | Recommendation |",
            "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |"
        ]

        for f in flights:
            airline = f.get("primary_airline_name") or f.get("primary_airline") or "Unknown"
            flight_num = f.get("flight_number") or "N/A"
            price_str = f.get("price_display") or f.get("price") or "N/A"
            
            # Extract duration and departure from segment if available
            duration = "N/A"
            departure = "N/A"
            stops = 0
            stops = "N/A"
            if f.get("itineraries") and f["itineraries"]:
                itin = f["itineraries"][0]
                duration = ChatResponseBuilder.format_duration(itin.get("duration")) or "N/A"
                if itin.get("segments") and itin["segments"]:
                    seg = itin["segments"][0]
                    departure = seg.get("departure_time") or "N/A"
                    if "T" in departure:
                        departure = departure.split("T")[1][:5]
                    # The scraper reports stops on the segment. Counting segments
                    # gave 0 for every flight (there is one segment per card), so
                    # a 5-hour connection was listed as non-stop.
                    if isinstance(seg.get("stops"), int):
                        stops = seg["stops"]
                    elif len(itin["segments"]) > 1:
                        stops = len(itin["segments"]) - 1
            if stops == 0:
                stops = "Non-stop"

            rec_label = "Monitor"
            if f.get("metadata") and isinstance(f["metadata"], dict):
                rec_label = f["metadata"].get("recommendation") or "Monitor"

            lines.append(f"| {airline} | {flight_num} | {departure} | {duration} | {stops} | {price_str} | {rec_label} |")

        return "\n".join(lines)

    @staticmethod
    def format_duration(iso: Optional[str]) -> Optional[str]:
        """"PT350M" or "PT5H50M" -> "5h 50m". The normaliser writes whole minutes
        ("PT350M"), which used to display as "350m"."""
        import re
        m = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?", str(iso or "").strip())
        if not m or not (m.group(1) or m.group(2)):
            return None
        total = int(m.group(1) or 0) * 60 + int(m.group(2) or 0)
        h, mins = divmod(total, 60)
        return f"{h}h {mins:02d}m" if h else f"{mins}m"

    @staticmethod
    def build_prediction_summary(pred: Dict[str, Any], origin: str, destination: str, departure_date: str) -> str:
        """Format price predictions and forecast timelines into clean text cards."""
        predicted_price = pred.get("predicted_price", 0.0)
        trend = pred.get("trend", "STABLE")
        change_pct = pred.get("change_percent", 0.0)
        
        intel = pred.get("intelligence", {})
        prob_increase = intel.get("prob_increase", 0.5)
        decision = pred.get("decision", {})
        recommendation = decision.get("decision", "WAIT")
        reasons = decision.get("reasons", ["Price is stable."])
        market_status = intel.get("market_status") or "STABLE"

        lines = [
            f"### Price Prediction Summary for {origin} to {destination} ({departure_date}):",
            f"- **Predicted Fare**: ₹{predicted_price:,.2f}",
            f"- **Market Status**: {market_status}",
            f"- **Trend**: {trend} ({change_pct:+.1f}%)",
            f"- **Probability of Increase**: {int(prob_increase * 100)}%",
            f"- **Recommendation**: **{recommendation}**",
            "",
            "#### Analysis Details:",
            "\n".join(f"- {r}" for r in reasons),
            "",
            "#### Forecast Projection:"
        ]

        forecast = pred.get("forecast", [])
        if forecast:
            lines.extend([
                "| Booking Offset | Target Date | Projected Price | Lower Bound | Upper Bound |",
                "| :--- | :--- | :--- | :--- | :--- |"
            ])
            for idx, day in enumerate(forecast):
                lines.append(f"| Day {day['day']} | {day['date']} | ₹{day['price']:.2f} | ₹{day['lower']:.2f} | ₹{day['upper']:.2f} |")

        return "\n".join(lines)

    @staticmethod
    def _price_text(flight: Dict[str, Any]) -> Optional[str]:
        """"₹6,913" for a rupee fare. It printed the raw float ("6913.0")."""
        if flight.get("price_display"):
            return str(flight["price_display"])
        price = flight.get("price")
        if isinstance(price, dict):
            price = price.get("total")
        if isinstance(price, (int, float)) and flight.get("currency") in (None, "INR"):
            return f"₹{price:,.0f}"
        return str(price) if price is not None else None

    @staticmethod
    def _departure_text(flight: Dict[str, Any]) -> Optional[str]:
        dep = flight.get("departure_time")
        if not dep:
            for itin in flight.get("itineraries") or []:
                for seg in itin.get("segments") or []:
                    dep = seg.get("departure_time")
                    break
                break
        if isinstance(dep, str) and "T" in dep:
            return dep.split("T")[1][:5]
        return dep or None

    @staticmethod
    def build_recommendations_summary(recs: Dict[str, Any]) -> str:
        """Construct highlights list for Cheapest, Fastest, and Best Value flights."""
        lines = ["### Highlight Recommendations:"]

        has_recs = False
        for category in ["cheapest", "fastest", "best_value"]:
            flight = recs.get(category)
            if flight:
                has_recs = True
                airline = flight.get("primary_airline_name") or flight.get("primary_airline") or "Unknown airline"
                # Google Flights cards often carry no flight number; it printed "(None)".
                label = f"{airline} {flight['flight_number']}" if flight.get("flight_number") else airline
                departure = ChatResponseBuilder._departure_text(flight)
                if departure:
                    label += f", departs {departure}"
                price_str = ChatResponseBuilder._price_text(flight) or "price unavailable"
                lines.append(f"- **{category.replace('_', ' ').title()} Option**: {label} at **{price_str}**")

        if not has_recs:
            return "No specific flight recommendations available at the moment."

        return "\n".join(lines)
