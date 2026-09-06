"""Strict Calendar Date Subtraction Engine for SkyMind Dataset Pipeline.

Permanently eliminates off-by-one errors caused by timestamp float subtraction or floor rounding.
Always computes: days_until_dep = (departure_date.date() - recorded_at.date()).days
"""

from datetime import datetime, date, timezone
from typing import Union, Dict, Any
import pandas as pd


class UnparseableTimestamp(ValueError):
    """`parse_to_date` was handed a value it cannot read.

    A distinct type so callers can tell "this row's date is malformed" apart from
    "this row's date disagrees with its `days_until_dep`". Those are different
    findings about the corpus and they used to arrive as the same `False`.
    """


def parse_to_date(val: Union[str, date, datetime, pd.Timestamp]) -> date:
    """Parses input into a datetime.date object with zero time component.

    Accepts what Postgres and Supabase actually emit, which is wider than
    `datetime.fromisoformat` accepts before Python 3.11. A `timestamptz` exported
    from `price_history` reads `2026-07-23 08:43:28.003237+00` — a **two-digit**
    UTC offset. `fromisoformat` requires `+HH:MM`, so on Python 3.10 every row of
    a real export raised `ValueError: Invalid isoformat string`, and the previous
    implementation had no other path to fall back to.

    That was not a cosmetic parser gap. `engineer_dataset_features` calls this on
    `recorded_at` for every row, so the whole `backend/dataset` v2.0 feature build
    aborted on the first row of any genuine export; it only ever ran to completion
    against fixtures whose timestamps happened to be `fromisoformat`-shaped.
    `validate_days_until_dep_row` caught the same error and returned `False`, so
    the dataset doctor reported all 35,894 rows of a real corpus as calendar
    mismatches when the true figure is 14,257 — and would have reported a
    different number on Python 3.11, where the string parses. A check whose result
    depends on the interpreter's minor version is not measuring the data.

    `pd.to_datetime` handles the two-digit offset, `Z`, `T` or space separators,
    and bare dates, so it is tried first and the hand-rolled paths remain as a
    fallback for anything it declines.
    """
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, pd.Timestamp):
        return val.date()

    if val is None:
        raise UnparseableTimestamp("cannot parse a date from None")

    str_val = str(val).strip()
    if not str_val or str_val.lower() in {"nan", "nat", "none", "null"}:
        raise UnparseableTimestamp(f"cannot parse a date from {str_val!r}")

    # pandas is already a hard dependency of this package and its parser accepts
    # the Postgres offset forms; `utc=True` keeps a tz-aware value comparable and
    # `.date()` then reports the UTC calendar day, which is the day the row's
    # `recorded_at` names.
    try:
        ts = pd.to_datetime(str_val, utc=True, errors="raise")
        if ts is not pd.NaT:
            return ts.date()
    except (ValueError, TypeError, OverflowError):
        pass

    if "T" in str_val or " " in str_val:
        cleaned = str_val.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(cleaned).date()
        except ValueError:
            pass

    try:
        return datetime.strptime(str_val[:10], "%Y-%m-%d").date()
    except ValueError as exc:
        raise UnparseableTimestamp(
            f"cannot parse a date from {str_val!r}: {exc}"
        ) from exc


def compute_calendar_days_until_dep(departure_date: Union[str, date, datetime, pd.Timestamp],
                                    recorded_at: Union[str, date, datetime, pd.Timestamp]) -> int:
    """Computes exact integer days_until_dep using calendar date subtraction.
    
    Formula: (departure_date.date() - recorded_at.date()).days
    """
    dep_d = parse_to_date(departure_date)
    rec_d = parse_to_date(recorded_at)
    return (dep_d - rec_d).days


def classify_days_until_dep_row(row: Dict[str, Any]) -> str:
    """One of `"ok"`, `"mismatch"`, `"unreadable"` for `row`'s `days_until_dep`.

    Three outcomes because there are three states, and `validate_days_until_dep_row`
    collapsed them into two. A row whose timestamp could not be parsed was
    indistinguishable from a row whose stored `days_until_dep` disagreed with its
    dates, so the doctor's "N date mismatches" line counted parser failures as
    corpus defects — and named the corpus as the thing at fault.

    `"unreadable"` covers a missing `departure_date`, a missing observation time, a
    missing or non-integer `days_until_dep`, and a timestamp `parse_to_date`
    declines. `"mismatch"` is reserved for the case where both dates were read and
    the stored integer is not their difference.
    """
    dep_date = row.get("departure_date")
    # `search_timestamp` first, `recorded_at` second — the order
    # `booking_curve_definition.ORDERING_TIMESTAMP_KEY` /
    # `FALLBACK_TIMESTAMP_KEY` establish, and the order the writer uses:
    # `ingestion_controller` derives `booking_date` from `search_timestamp` and
    # only falls back to the insert time. This read them the other way round, so
    # a row whose search crossed midnight before it was written (a search at
    # 23:58 recorded at 00:03) was measured against the wrong calendar day and a
    # correctly computed `days_until_dep` was reported invalid by one.
    rec_at = row.get("search_timestamp") or row.get("recorded_at")
    claimed_days = row.get("days_until_dep")

    if dep_date is None or rec_at is None or claimed_days is None:
        return "unreadable"

    try:
        claimed = int(claimed_days)
    except (TypeError, ValueError):
        return "unreadable"

    try:
        expected_days = compute_calendar_days_until_dep(dep_date, rec_at)
    except (UnparseableTimestamp, ValueError, TypeError, OverflowError):
        return "unreadable"

    return "ok" if claimed == expected_days else "mismatch"


def validate_days_until_dep_row(row: Dict[str, Any]) -> bool:
    """True when `row['days_until_dep']` equals exact calendar date subtraction.

    Kept as the boolean face of `classify_days_until_dep_row` for callers that only
    need "is this row sound". Both `"mismatch"` and `"unreadable"` are False here,
    which is the right answer to that question — but a caller *reporting* on a
    corpus should use the classifier, because the two failures have different
    causes and different fixes.
    """
    return classify_days_until_dep_row(row) == "ok"
