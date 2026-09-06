from datetime import datetime, timezone
import re
from typing import Optional, Any

from backend.domain.provenance import decode_currency

class MarketDataController:
    AIRLINE_NAMES = {
        "6E": "IndiGo",
        "AI": "Air India",
        "IX": "Air India Express",
        "QP": "Akasa Air",
        "UK": "Vistara",
        "SG": "SpiceJet",
        "G8": "Go First",
        "S5": "Star Air",
        "2T": "TruJet",
        "I5": "AirAsia India",
    }

    # There used to be a `parse_mmt_flight_string` staticmethod here, matching
    # `\b([A-Z0-9]{2})[- ]*([0-9]+)` against a display string like "Indigo 6E-2012"
    # and returning `(airline_code, flight_number)`. It is deleted, for the same
    # reason the flight-number regex in `GoogleFlightsProvider.js` was (§42 of
    # AUDIT-FIXES.md): it is a fabricator waiting for an input.
    #
    # Its one caller was `flight_normalizer.normalize_mcp_flight`, on the live path.
    # What it was fed is `flight_name` from `stdio_server.js`, which is the carrier's
    # display name with the flight number appended — and the provider publishes no
    # flight number (0 of 65 on the live 2026-09-03 fetch), so the string is a bare
    # name like "Air India Express", the regex finds no digits, and the function has
    # returned `("", "")` on every real card. Inert, but only because of what the
    # input happens to look like: `[- ]*` matches the empty string, so any display
    # text carrying two alphanumerics followed by digits synthesises a flight number
    # out of them. That is exactly how the deleted scraper regex turned "Sep 24" plus
    # "117 kg CO2e" into flight 24117 on 41 of 65 cards.
    #
    # Nothing replaces it. `primary_airline`/`airline_name` arrive as their own
    # fields, and an absent flight number stays None.

    @staticmethod
    def format_payload(
        origin_code: str,
        destination_code: str,
        airline_code: str,
        price: float,
        departure_date: str,
        days_until_dep: int,
        seats_available: Optional[int] = None,
        flight_number: Optional[str] = None,
        departure_time: Optional[str] = None,
        cabin_class: str = "ECONOMY",
        currency: Optional[str] = None,
        is_holiday: Optional[bool] = None,
        recorded_at: Optional[str] = None,
        search_session_id: Optional[str] = None,
        search_timestamp: Optional[str] = None,
        provider: Optional[str] = None,
        search_id: Optional[str] = None,
        snapshot_id: Optional[str] = None,
        collector_version: str = "1.0.0",
        booking_date: Optional[str] = None,
        duration: Optional[str] = None,
        stops: Optional[int] = None,
        terminal: Optional[str] = None,
        route: Optional[str] = None,
        data_source: Optional[str] = None,
    ) -> dict:
        """
        Maps live search observations to price_history schema, extracting chronological/temporal tags.
        Maintains a strict Zero Synthetic Feature Policy: missing attributes default to None / SQL NULL.

        There used to be an `is_synthetic: bool = False` parameter here, and no
        caller in the codebase passed it — the one production call site is
        `flight_search_service.py:488`. It mattered anyway, because the returned
        dict hardcoded `is_live: True` alongside `is_synthetic: bool(is_synthetic)`.
        A row written through that parameter would have carried
        `is_synthetic=True` *and* `is_live=True`, which is a contradiction the
        provenance predicate is not designed to arbitrate: `has_authentic_provenance`
        would reject it on the first condition while the SQL loaders' second
        condition said it was a live observation. This function writes market
        observations and nothing else, so both flags are now constants of the
        function rather than one constant and one argument.
        """
        dep_date = datetime.strptime(departure_date, "%Y-%m-%d").date()
        day_of_week = dep_date.weekday()
        month = dep_date.month

        isocal = dep_date.isocalendar()
        week_of_year = isocal[1] if isinstance(isocal, tuple) else isocal.week
        is_weekend = day_of_week >= 5

        # A negative horizon means the caller is recording a departure that has
        # already happened. Clipping it to 0 silently relabels the row as
        # "departing today", so reject it instead — every caller computes this
        # from a date it controls.
        days_val = int(days_until_dep)
        if days_val < 0:
            raise ValueError(
                f"days_until_dep must be >= 0, got {days_val} for "
                f"{origin_code}-{destination_code} departing {departure_date}"
            )
        urgency = round(1 / (days_val + 1), 4)

        if is_holiday is None:
            is_holiday = (dep_date.month, dep_date.day) in {(1, 1), (1, 26), (8, 15), (10, 2), (12, 25)}

        # `flight_number` used to fall back to f"{airline_code}1000" here — a
        # fabricated identifier, inside the function whose docstring promises
        # missing attributes become SQL NULL, and directly against the caller in
        # flight_search_service.py which passes None specifically to preserve the
        # NULL. It also gave every unidentified flight on a carrier the same
        # number, which is how the stored corpus ended up with one distinct
        # flight_number across 6,328 rows. Leave it None; get_db_payload drops
        # None values so the column stays NULL.
        if flight_number is not None:
            flight_number = str(flight_number).upper().strip() or None

        # `departure_time` was never persisted, and `hour_of_day` / `is_peak_hour`
        # are declared features computed from it. So every row loaded from
        # price_history had both NaN, for 100% of the training corpus, while the
        # serving path reads the hour straight off the provider's segment and
        # supplies it — the largest train/serve skew in the project, on a feature
        # airfare pricing actually turns on. Capturing it at ingest is the fix;
        # `hour_of_day`'s description in feature_metadata.py records the gap for
        # rows written before this.
        #
        # Normalised to a full timestamp, not just an hour, because
        # database.py:359-360 range-queries this column with
        # `{departure_date}T00:00:00`. A provider that reports a bare "06:00" is
        # combined with the departure date; anything else unparseable stays None
        # rather than being guessed into a plausible-looking datetime.
        departure_time = MarketDataController.normalize_departure_time(
            departure_time, departure_date
        )

        # `currency` defaulted to the literal "INR", and the one production caller
        # has never passed it — so every row this function has ever produced claimed
        # rupees whatever the provider quoted. That is not a harmless default: the
        # scraper finds the price line by testing it for '₹' *or* '$' and then
        # discards the symbol, so a page served in dollars arrives here as a bare
        # number and used to leave labelled INR. 156 stored rows at ₹58–₹105 are
        # that defect. Decoded now, and `None` when the caller cannot say — which
        # `get_db_payload` drops and `screen_observation_fares` refuses, rather than
        # a guess that reads like a measurement.
        currency = decode_currency(currency)

        if recorded_at is None:
            recorded_at = datetime.now(timezone.utc).isoformat()

        if search_timestamp is None:
            search_timestamp = recorded_at

        if not booking_date:
            try:
                booking_date = datetime.fromisoformat(search_timestamp.replace("Z", "+00:00")).date().isoformat()
            except Exception:
                booking_date = datetime.now(timezone.utc).date().isoformat()

        if not route:
            route = f"{origin_code.upper()}-{destination_code.upper()}"

        # `data_source` used to default to the literal "GOOGLE_FLIGHTS" while the
        # caller passed the real origin as `provider`, so the two columns
        # disagreed about the same fact on every row and the more specific one
        # was the one nobody queried. Default to the provider actually used.
        if not data_source:
            data_source = provider or "UNKNOWN"

        return {
            "origin_code": origin_code.upper().strip(),
            "destination_code": destination_code.upper().strip(),
            "airline_code": airline_code.upper().strip(),
            "flight_number": flight_number,
            "departure_time": departure_time,
            "cabin_class": cabin_class,
            "price": float(price),
            "currency": currency,
            "departure_date": departure_date,
            "days_until_dep": days_val,
            "day_of_week": day_of_week,
            "month": month,
            "week_of_year": week_of_year,
            "is_holiday": bool(is_holiday),
            "is_weekend": bool(is_weekend),
            "seats_available": seats_available,
            "recorded_at": recorded_at,
            "search_session_id": search_session_id,
            "search_timestamp": search_timestamp,
            # The provenance pair, stated together because they are one fact.
            # `backend/domain/provenance.py` is the single definition of what they
            # mean; every row this function produces came from a provider response
            # in the live search path, which is the only thing that makes `is_live`
            # true here.
            "is_live": True,
            "data_source": data_source,
            "is_synthetic": False,
            # Consumed as the XGBoost sample weight (`model_trainer.py:248`,
            # `price_model.py:1105`). It is a constant, so it currently expresses
            # no weighting scheme at all — every row this path writes is weighted
            # identically, and the column only looks like a policy. 2.0 rather than
            # 1.0 because the rows already stored carry 2.0: writing a smaller
            # number here would quietly weight the older, partly-seeded block twice
            # as heavily as newly observed fares. Either define a real scheme or
            # drop the column; do not change this value alone.
            "training_weight": 2.0,
            "urgency": urgency,
            
            # Real historical collection extensions
            "provider": provider,
            "search_id": search_id,
            "snapshot_id": snapshot_id,
            "collector_version": collector_version,
            "booking_date": booking_date,
            "duration": duration,
            "stops": stops,
            "terminal": terminal,
            "route": route,
            
            # Zero fabrication placeholder overrides
            "price_change_1d": None,
            "price_change_3d": None,
            "demand_score": None,
            "seasonality_factor": None
        }

    @staticmethod
    def get_db_payload(payload: dict) -> dict:
        """Filter out non-database columns before inserting into Supabase/PostgreSQL."""
        db_keys = {
            "origin_code", "destination_code", "airline_code", "flight_number",
            "cabin_class", "price", "currency", "departure_date", "days_until_dep",
            "day_of_week", "month", "week_of_year", "is_holiday", "is_weekend",
            "seats_available", "recorded_at", "search_session_id", "search_timestamp",
            "is_live", "data_source", "is_synthetic", "training_weight", "urgency",
            "provider", "search_id", "snapshot_id", "collector_version", "booking_date",
            "duration", "stops", "terminal", "route", "departure_time",
        }
        return {k: v for k, v in payload.items() if k in db_keys and v is not None}

    # ── departure_time normalisation ──────────────────────────────────────
    # Kept as a named staticmethod rather than inlined so the serving path and
    # any future backfill use one rule. Returns None for anything it cannot read
    # as a real departure instant; it never invents one.
    _TIME_ONLY = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)(?::([0-5]\d))?$")

    @staticmethod
    def normalize_departure_time(
        value: Optional[Any], departure_date: Optional[str]
    ) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None

        # Already a datetime: trust the date it carries, even if it disagrees
        # with departure_date — a red-eye leg legitimately departs the day after
        # the date the itinerary is filed under, and silently rewriting it to
        # departure_date would move the flight.
        if "T" in text or " " in text:
            try:
                parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            except ValueError:
                return None
            return parsed.isoformat()

        # Time only, e.g. "06:00" or "18:45:00" — needs the date to mean anything.
        match = MarketDataController._TIME_ONLY.match(text)
        if not match or not departure_date:
            return None
        try:
            dep_date = datetime.strptime(departure_date, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return None
        hour, minute = int(match.group(1)), int(match.group(2))
        second = int(match.group(3) or 0)
        return datetime.combine(
            dep_date, datetime.min.time().replace(hour=hour, minute=minute, second=second)
        ).isoformat()
