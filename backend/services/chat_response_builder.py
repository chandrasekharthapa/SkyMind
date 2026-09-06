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
            if f.get("itineraries") and f["itineraries"]:
                itin = f["itineraries"][0]
                duration = itin.get("duration") or "N/A"
                if "PT" in duration:
                    # Clean ISO format
                    duration = duration.replace("PT", "").replace("H", "h ").replace("M", "m").strip()
                if itin.get("segments") and itin["segments"]:
                    seg = itin["segments"][0]
                    departure = seg.get("departure_time") or "N/A"
                    if "T" in departure:
                        departure = departure.split("T")[1][:5]
                    stops = len(itin["segments"]) - 1

            rec_label = "Monitor"
            if f.get("metadata") and isinstance(f["metadata"], dict):
                rec_label = f["metadata"].get("recommendation") or "Monitor"

            lines.append(f"| {airline} | {flight_num} | {departure} | {duration} | {stops} | {price_str} | {rec_label} |")

        return "\n".join(lines)

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
    def build_recommendations_summary(recs: Dict[str, Any]) -> str:
        """Construct highlights list for Cheapest, Fastest, and Best Value flights."""
        lines = ["### Highlight Recommendations:"]
        
        has_recs = False
        for category in ["cheapest", "fastest", "best_value"]:
            flight = recs.get(category)
            if flight:
                has_recs = True
                price_str = flight.get("price_display") or flight.get("price")
                airline = flight.get("primary_airline_name") or flight.get("primary_airline")
                flight_num = flight.get("flight_number")
                lines.append(f"- **{category.replace('_', ' ').title()} Option**: {airline} ({flight_num}) at **{price_str}**")

        if not has_recs:
            return "No specific flight recommendations available at the moment."

        return "\n".join(lines)
