"""Training Eligibility Service.

Row-level restatement of what the training loaders select in SQL, for callers
holding rows already in memory. It is applied by `training_dataset_builder`
immediately after `database.get_training_dataset()`, so in production it is a
second pass over rows the database predicate has already accepted.

That is why it must apply the *same* predicate. It did not. This module used to
check `is_synthetic` and nothing else, and its docstring said it "replaces legacy
`WHERE is_live = TRUE` overloading" — which was wrong in both halves. The
`is_live` condition was not replaced: it is still applied by both loaders, and on
this corpus it is the condition doing the real work, because the migration that
added `is_synthetic` defaulted it to FALSE and so labelled the seeded rows
authentic. A reader who believed this docstring would conclude the `is_live`
predicate was vestigial and could be dropped from `database.py`, which would
re-admit the entire fabricated block into training.

The predicate, the fare window and the flag decoding now come from
`backend.domain.provenance`, shared with `database._PROVENANCE_SQL`, its Supabase
mirror, and `forecast_evaluation_scheduler`. Four hand-copies of one rule is how
they drifted.
"""

from typing import Dict, Any, Union
import pandas as pd

from backend.domain.provenance import (
    LIVE_KEY,
    MAX_PLAUSIBLE_FARE,
    MIN_PLAUSIBLE_FARE,
    SYNTHETIC_KEY,
    decode_flag,
    fare_is_plausible,
    has_authentic_provenance,
)


# Re-exported under their historical names: `test_route_catalog` imports them and
# they read naturally at the call sites below. One definition, in
# `backend.domain.provenance`.
MIN_PRICE_BOUND = MIN_PLAUSIBLE_FARE
MAX_PRICE_BOUND = MAX_PLAUSIBLE_FARE

MANDATORY_KEYS = ("origin_code", "destination_code", "airline_code", "departure_date")

# `departure_time` is deliberately absent from `MANDATORY_KEYS`, even though it is the
# per-flight component of `BOOKING_CURVE_KEYS` and every label depends on it.
#
# The reason is what absence costs here versus downstream. When a mandatory column is
# missing, `filter_training_eligible_dataframe` returns `df_out.iloc[0:0]` — an empty
# frame, silently. `attach_future_target`, which is the next stop and the thing that
# actually needs the column, raises `ValueError` naming the missing curve-key columns.
# Adding `departure_time` here would replace a named, locatable error with zero rows
# and no stated reason, and "the corpus has no eligible rows" reads as a fact about
# the data rather than about a missing column.
#
# So eligibility grades what it can grade — provenance, fare plausibility, and the
# four columns that identify a route and a departure date — and the curve identity is
# enforced where it is used. Do not "complete" this tuple without also making the
# missing-column branch below say which column it refused on.


def is_training_eligible(record: Union[Dict[str, Any], pd.Series]) -> bool:
    """Determines if a single observation record is eligible for ML training."""
    # 1. Provenance: non-synthetic *and* live, decoded the same way the loaders
    #    filter and fail-closed on anything unreadable. This was a bare
    #    `record.get("is_synthetic", False)` — absent meant authentic, which is
    #    the assumption that let a defaulted-in label pass for observed data.
    if not has_authentic_provenance(record):
        return False

    # 2. Valid price check
    if not fare_is_plausible(record.get("price")):
        return False

    # 3. Departure horizon / chronology check
    days_until_dep = record.get("days_until_dep")
    if days_until_dep is not None and not pd.isna(days_until_dep):
        try:
            if float(days_until_dep) < 0:
                return False
        except (ValueError, TypeError):
            pass

    # 4. Mandatory attributes check
    for key in MANDATORY_KEYS:
        val = record.get(key)
        if not val or pd.isna(val):
            return False

    return True


def filter_training_eligible_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Filters a pandas DataFrame returning only eligible training observations.

    Vectorised counterpart to `is_training_eligible`, and it must agree with it:
    the two used to differ on absent provenance columns, on string flag values,
    and on NaN prices.
    """
    if df.empty:
        return df.copy()

    df_out = df.copy()

    # 1. Provenance mask. Both columns are required — a frame that does not
    #    carry them cannot be shown to be observed data, and the previous
    #    `else pd.Series(True, ...)` treated their absence as a pass.
    #
    #    `.map(decode_flag)` rather than a string comparison: this frame may have
    #    come through `database._engineer_features`, and the loaders return real
    #    bools, while a CSV round-trip returns "true"/"false" and a defaulted
    #    column returns None. The old `astype(str).str.lower().isin([...])` read
    #    None as the string "none" — not in the true-list, therefore not
    #    synthetic, therefore eligible.
    if SYNTHETIC_KEY in df_out.columns:
        mask_synth = df_out[SYNTHETIC_KEY].map(decode_flag).eq(False)
    else:
        mask_synth = pd.Series(False, index=df_out.index)

    if LIVE_KEY in df_out.columns:
        mask_live = df_out[LIVE_KEY].map(decode_flag).eq(True)
    else:
        mask_live = pd.Series(False, index=df_out.index)

    # 2. Valid price mask. `notna()` is explicit because `NaN >= 800` is False
    #    but `NaN <= 60000` is also False, and relying on that is relying on an
    #    accident.
    price = pd.to_numeric(df_out["price"], errors="coerce")
    mask_price = price.notna() & (price >= MIN_PRICE_BOUND) & (price <= MAX_PRICE_BOUND)

    # 3. Days until dep mask — absent or NaN is unknown, not ineligible, which is
    #    what `is_training_eligible` does with it too.
    if "days_until_dep" in df_out.columns:
        days = pd.to_numeric(df_out["days_until_dep"], errors="coerce")
        mask_days = days.isna() | (days >= 0)
    else:
        mask_days = pd.Series(True, index=df_out.index)

    # 4. Mandatory keys mask. `notna()` alone accepted the empty string, which
    #    `is_training_eligible`'s `if not val` rejects; `.ne("")` closes that.
    mask_keys = pd.Series(True, index=df_out.index)
    for key in MANDATORY_KEYS:
        if key not in df_out.columns:
            return df_out.iloc[0:0].copy()
        col = df_out[key]
        mask_keys &= col.notna() & (col.astype(str).str.strip() != "")

    eligible_mask = mask_synth & mask_live & mask_price & mask_days & mask_keys
    return df_out[eligible_mask].copy()
