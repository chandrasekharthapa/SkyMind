"""Stable itinerary id generator for the SkyMind dataset export path.

An itinerary is one booking curve at one cabin: the five components of
`BOOKING_CURVE_KEYS` plus `cabin_class`, hashed to sixteen hex characters. The id is
derived from the curve key rather than a list typed out here, because two things in
`backend/dataset` *delete rows* on the strength of it —

  * `plugins/time_series_plugin.py` groups by `itinerary_id`, checks that each
    group's timestamps ascend, and drops every row of any itinerary that fails; and
  * `snapshot.compute_snapshot_sequences` numbers observations within an id, so the
    shipped `snapshot_sequence` column means "how many times this itinerary has been
    observed".

The per-flight component used to be `flight_number`, and `attach_itinerary_id_to_row`
passed `row.get("flight_number") or None` into `str(...).upper()` — so an absent
flight number hashed the literal `"NONE"`. Google Flights publishes no flight number,
so that was every row: all of a carrier's departures on one route, date and cabin
collapsed onto a single id. Measured on a live 65-flight DEL-BOM fetch, 29 IndiGo
departures became one itinerary. The consequences are not cosmetic — the chronology
plugin saw one "itinerary" whose timestamps restart 29 times, declared it corrupted,
and deleted all 29 rows; and `snapshot_sequence` counted sibling departures as repeat
observations of one flight, which is the same number `statistics.py` publishes as
snapshot density per itinerary.

Nothing here substitutes a value for a missing component. `generate_itinerary_id`
raises rather than hash a placeholder, because a placeholder is what produced the
collapse above, and `attach_itinerary_id_to_row` leaves `itinerary_id` absent so the
consumers' own missing-column branches decide what to do.
"""

import hashlib
from typing import Dict, Any, Optional

from backend.dataset.dates import parse_to_date
from backend.services.booking_curve_definition import (
    BOOKING_CURVE_KEYS,
    curve_identity_from_record,
    curve_identity_is_complete,
)

# The cabin is not part of the curve identity — one flight quoted in two cabins is
# two price series, but `BOOKING_CURVE_KEYS` is the key the *training* path groups
# on and the corpus has one cabin. It stays in the hash because it has always been
# in it and because dropping it would merge two series if a cabin column ever
# arrives populated.
ITINERARY_CABIN_KEY = "cabin_class"
DEFAULT_CABIN = "ECONOMY"

ITINERARY_ID_LENGTH = 16


def _canonical(key: str, value: Any) -> str:
    """One component of the hash input, normalised.

    `departure_date` goes through `parse_to_date` so that `2026-08-15`,
    `2026-08-15T00:00:00Z` and a `date` object give one id. Everything else is
    upper-cased and stripped, which is what the previous implementation did to all
    five of its inputs — including the date, whose parse it did separately.
    """
    if key == "departure_date":
        return parse_to_date(value).strftime("%Y-%m-%d")
    return str(value).strip().upper()


def generate_itinerary_id(record: Dict[str, Any]) -> str:
    """The 16-character itinerary id for `record`.

    Takes a record rather than six positional arguments. The old signature was
    `(origin, destination, departure_date, airline, flight_number, cabin)` — six
    strings in a fixed order, with the per-flight component in the fifth slot — which
    is the shape that made the key impossible to change in one place. Callers now
    hand over the row and the key is read from `BOOKING_CURVE_KEYS`.

    Raises `ValueError` when the curve identity is incomplete. The alternative is to
    hash a placeholder for the missing component, which is the exact defect this
    module's header describes.
    """
    identity = curve_identity_from_record(record)
    if not curve_identity_is_complete(identity):
        absent = [k for k in BOOKING_CURVE_KEYS if not identity.get(k)]
        raise ValueError(
            "Cannot build an itinerary id: the record is missing "
            f"{', '.join(absent)}. Hashing a placeholder for an absent component "
            "collapses distinct departures onto one id, and two plugins delete rows "
            "on the strength of that id."
        )

    cabin = record.get(ITINERARY_CABIN_KEY) or DEFAULT_CABIN
    parts = [_canonical(key, identity[key]) for key in BOOKING_CURVE_KEYS]
    parts.append(_canonical(ITINERARY_CABIN_KEY, cabin))

    raw_string = ":".join(parts)
    return hashlib.md5(raw_string.encode("utf-8")).hexdigest()[:ITINERARY_ID_LENGTH]


def attach_itinerary_id_to_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Attach `itinerary_id` to `row`, or leave it absent.

    Returns the row unchanged when the curve identity is incomplete. It does not
    raise, because the export path processes a corpus row by row and one unidentified
    observation is not a reason to abandon the rest; and it does not invent an id,
    because the consumers all have a missing-column branch and a wrong id is worse
    than no id. `doctor.py` reports the absence as a warning.
    """
    if row.get("itinerary_id"):
        return row
    try:
        row["itinerary_id"] = generate_itinerary_id(row)
    except (ValueError, TypeError, AttributeError):
        # TypeError/AttributeError cover `parse_to_date` on a value that is present
        # but not a date. Same treatment: no id rather than a fabricated one.
        pass
    return row


def itinerary_id_of(record: Dict[str, Any]) -> Optional[str]:
    """`generate_itinerary_id`, or None when the record cannot be identified."""
    try:
        return generate_itinerary_id(record)
    except (ValueError, TypeError, AttributeError):
        return None
