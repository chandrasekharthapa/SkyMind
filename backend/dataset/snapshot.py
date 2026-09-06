"""Snapshot Metadata & Sequence Tracker for SkyMind Dataset Pipeline.

Attaches snapshot sequence numbers and version provenance metadata to observations.
"""

import logging
from typing import Dict, Any
import pandas as pd
from backend.dataset.config import default_dataset_config
from backend.dataset.dates import parse_to_date
from backend.services.booking_curve_definition import (
    observed_at_of_record,
    ordering_timestamps,
)

logger = logging.getLogger(__name__)


def attach_snapshot_metadata(row: Dict[str, Any], sequence: int = 1) -> Dict[str, Any]:
    """Attaches versioning and snapshot metadata fields to observation dictionary."""
    # This was:
    #
    #     rec_at = row.get("recorded_at") or row.get("search_timestamp") \
    #         or datetime.now(timezone.utc).isoformat()
    #
    # Two defects in one line. The preference was inverted — `recorded_at` is the
    # insert time, while the writer treats `search_timestamp` as when the fare was
    # observed and derives `booking_date` from it — and a row carrying neither was
    # stamped with the moment the exporter ran. That is a fabricated observation
    # time written into `snapshot_time` and `snapshot_date`, the two columns
    # downstream consumers order the curve by, and it is indistinguishable in the
    # exported CSV from a genuinely recorded one.
    observed = observed_at_of_record(row)
    row["snapshot_time"] = observed.isoformat() if observed is not None else None
    row["snapshot_date"] = (
        parse_to_date(observed).strftime("%Y-%m-%d") if observed is not None else None
    )
    row["snapshot_sequence"] = sequence
    row["collector_version"] = default_dataset_config.collector_version
    row["pipeline_version"] = default_dataset_config.pipeline_version
    row["feature_version"] = default_dataset_config.feature_version
    row["dataset_version"] = default_dataset_config.dataset_version
    row["schema_version"] = default_dataset_config.schema_version

    return row


def compute_snapshot_sequences(df: pd.DataFrame) -> pd.DataFrame:
    """Computes 1-indexed snapshot_sequence per itinerary_id ordered chronologically by snapshot_time."""
    if df.empty or "itinerary_id" not in df.columns:
        return df

    # `ts_col = "snapshot_time" if ... else ("recorded_at" if ... else None)` picked
    # one column by presence and read only that. `snapshot_time` is now None for a
    # row with no observation time, so a present-but-empty column would have made
    # every sequence number depend on frame order instead of chronology. Resolve
    # per row: `snapshot_time` where it was recorded above, otherwise the same
    # coalesce the canonical definition applies.
    # `format="ISO8601"` because line 34 writes this column with
    # `observed.isoformat()`, and `isoformat()` omits the microseconds field when
    # it is zero. So the column holds both `...T10:00:00.123456+00:00` and
    # `...T10:00:01+00:00`, and without the format pandas infers one shape from
    # the first non-null value and coerces every row of the other shape to NaT.
    # Those rows would then fall into the `unorderable` branch below and lose
    # their sequence number, on a column this module itself wrote correctly.
    order = pd.to_datetime(df.get("snapshot_time"), errors="coerce", utc=True,
                           format="ISO8601") \
        if "snapshot_time" in df.columns else None
    fallback = ordering_timestamps(df)
    if order is None:
        resolved = fallback
    else:
        resolved = pd.Series(order.values, index=df.index,
                             dtype="datetime64[ns, UTC]").fillna(fallback)

    df_sorted = df.assign(_snapshot_order=resolved)
    unorderable = int(df_sorted["_snapshot_order"].isna().sum())
    if unorderable:
        # A row that cannot be placed on the curve gets no sequence number rather
        # than an arbitrary one: `snapshot_sequence` is read as "this was the nth
        # observation of this itinerary", which a frame-order number is not.
        logger.warning(
            "[snapshot] %d of %d row(s) carry no usable observation time; their "
            "snapshot_sequence is left null rather than assigned by frame order.",
            unorderable, len(df_sorted),
        )

    df_sorted = df_sorted.sort_values(by=["itinerary_id", "_snapshot_order"])
    df_sorted["snapshot_sequence"] = (
        df_sorted[df_sorted["_snapshot_order"].notna()]
        .groupby("itinerary_id")
        .cumcount()
        + 1
    )
    return df_sorted.drop(columns=["_snapshot_order"])
