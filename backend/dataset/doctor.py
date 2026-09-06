"""SkyMind Dataset Doctor — data-readiness diagnostic for the training corpus.

Usage:
    python -m backend.dataset.doctor
    python -m backend.dataset.doctor --file backend/dataset/exports/flight_price_dataset_v2.0.csv

Two things about this tool were wrong, and both matter because this is what an
operator runs to answer "can I train a model yet?".

**It fabricated its own input.** When the export file was absent and
`database.get_training_dataset()` raised, it built a one-row frame in place —
`DEL→BOM, 2026-08-15, ₹4500, 6E101, days_until_dep=30` — and ran every check
against that, then printed a verdict about "Dataset v2.0". Those numbers were
literals in this file, not a sample of anything, and the one row satisfies every
check it was graded by. A diagnostic that invents a patient reports on the
invention. There is now no fallback frame: if there is neither an export nor a
reachable corpus, that is the finding.

**The verdict overstated its own scope.** Six schema and integrity checks cannot
establish that a dataset is "100% production-ready for ML", which is what the
PASS line claimed, and the docstring advertised "10 diagnostic health checks" for
the six that exist. What actually decides trainability is the shape of the booking
curves: `TrainingPolicy` needs `min_shifted_rows` labelled rows, and a row is only
labelled if its curve carries a later observation, so a corpus of one-observation
curves yields zero training rows however many rows it holds. That is check 7 now,
and the verdict names the corpus it graded, where it came from, and how many rows
it had.
"""

import sys
import os
import argparse
import logging
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from backend.dataset.dates import classify_days_until_dep_row
from backend.dataset.schema import MANDATORY_RAW_COLUMNS, PROHIBITED_EMPTY_COLUMNS
# Module-level because `CURVE_KEYS` below is derived from it at import time.
# `booking_curve_definition` imports nothing from this project — pandas and numpy
# only — so it cannot cycle back through `doctor`.
from backend.services.booking_curve_definition import BOOKING_CURVE_KEYS
from backend.services.training_policy import training_policy

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("dataset_doctor")

DEFAULT_EXPORT_PATH = "backend/dataset/exports/flight_price_dataset_v2.0.csv"

EXIT_PASS, EXIT_WARN, EXIT_FAIL = 0, 1, 2

# The columns that identify one booking curve — one flight on one departure date,
# observed repeatedly. It is the unit that decides whether a row can carry a
# supervised label, so a diagnostic that groups on a different key than the
# labeller does is measuring a different corpus than the one training will see.
#
# Taken from `booking_curve_definition` rather than re-typed. The comment here used
# to claim "`booking_curve_definition` uses the same identity" beside a hand-typed
# list, which is a claim no import enforced: when the per-flight component changed
# from `flight_number` to `departure_time` on 2026-09-03 this list would have kept
# naming a column the provider never populates, so every one of a carrier's
# departures on a route and date would have pooled into a single "curve" — and both
# uses below are inflated by exactly that pooling. `booking_curve_shape` would have
# reported longer curves and more `rows_on_multi_observation_curves` than exist,
# which is the upper bound the docstring tells the reader to trust; and the
# duplicate-snapshot check would have counted sibling departures that share a fare
# as copies of each other.
CURVE_KEYS = list(BOOKING_CURVE_KEYS)


def _load_corpus(filepath: Optional[str]) -> Tuple[pd.DataFrame, str]:
    """Return the frame to diagnose and a description of where it came from.

    Raises `RuntimeError` when there is nothing to grade. That is the honest
    outcome — it used to be the branch that fabricated a row.
    """
    if filepath:
        if not os.path.isfile(filepath):
            raise RuntimeError(f"no such dataset file: '{filepath}'")
        return pd.read_csv(filepath), f"export file '{filepath}'"

    if os.path.isfile(DEFAULT_EXPORT_PATH):
        return (pd.read_csv(DEFAULT_EXPORT_PATH),
                f"export file '{DEFAULT_EXPORT_PATH}'")

    from backend.database.database import database as db
    try:
        df = db.get_training_dataset()
    except Exception as exc:
        raise RuntimeError(
            f"no export at '{DEFAULT_EXPORT_PATH}' and the live corpus could not "
            f"be read: {type(exc).__name__}: {exc}"
        ) from exc

    if df is None or df.empty:
        raise RuntimeError(
            f"no export at '{DEFAULT_EXPORT_PATH}' and the live corpus returned no "
            f"eligible rows (live, non-synthetic, plausible fare). Nothing to "
            f"diagnose and nothing to train on."
        )
    return df, "live price_history corpus"


def booking_curve_shape(df: pd.DataFrame) -> Dict[str, Any]:
    """How many rows could carry a supervised label, and how the curves are shaped.

    A lifted function rather than a block inside the report so it can be asserted
    on directly. `rows_on_multi_observation_curves` is an **upper bound** on the
    training rows a build would produce, not an estimate: a row also needs its
    later observation to fall at or after `t + horizon` days, which this does not
    check. An upper bound is the useful direction — when it is already below
    `min_shifted_rows`, no horizon can clear the policy and training will be
    refused for every one of them.

    It is only an upper bound while the key is whole. Grouping on a subset of
    `CURVE_KEYS` pools distinct flights into one curve, which lengthens curves and
    moves rows out of `single_observation_curves` — so a partial key inflates the
    figure in the direction that makes an untrainable corpus look trainable.
    `curve_keys_missing` names what was absent, because a reader given only the
    positive list has to diff it against the key themselves to know whether the
    bound holds. Every frame collected before migration 001 is missing
    `departure_time`, so this is the common case, not an edge one.
    """
    present = [k for k in CURVE_KEYS if k in df.columns]
    missing = [k for k in CURVE_KEYS if k not in df.columns]
    if not present or df.empty:
        return {"rows": int(len(df)), "curve_keys_present": present,
                "curve_keys_missing": missing,
                "curves": 0, "longest_curve": 0,
                "single_observation_curves": 0,
                "rows_on_multi_observation_curves": 0}

    sizes = df.groupby(present, dropna=False).size()
    return {
        "rows": int(len(df)),
        "curve_keys_present": present,
        "curve_keys_missing": missing,
        "curves": int(len(sizes)),
        "longest_curve": int(sizes.max()),
        "single_observation_curves": int((sizes == 1).sum()),
        "rows_on_multi_observation_curves": int(sizes[sizes >= 2].sum()),
    }


def _labelled_rows_by_horizon(
    df: pd.DataFrame,
) -> Tuple[Dict[int, int], List[str]]:
    """Rows the shipped labeller actually returns, per declared training horizon.

    Calls the two functions the training path calls and nothing else:
    `filter_training_eligible_dataframe`, which is the single definition of "this
    row may be trained on" (live, non-synthetic, plausible fare, mandatory keys
    present), and `attach_future_target`, which is the single definition of the
    label. Reimplementing either here would produce a diagnostic that agrees with
    a training run only by coincidence, and this repository has already shipped
    two separately-written copies of that join that disagreed.

    Returns `({horizon: labelled_rows}, [errors])`. The errors are the `ValueError`s
    `attach_future_target` raises for a corpus it cannot label at all — missing
    curve-key columns, a horizon under `MIN_TRAINABLE_HORIZON_DAYS`, every
    observation timestamp NULL — reported rather than swallowed, because each names
    a different corpus defect and none of them means "no data".

    One divergence from a real build, stated so the number is not read as more
    than it is: `TrainingDatasetBuilder` also runs `deduplicate_session_aware`
    before labelling. Deduplication only removes rows, so these counts are an
    upper bound on what a build receives, never an under-report — the safe
    direction for a floor check.
    """
    from backend.services.booking_curve_definition import (
        SUPPORTED_TRAINING_HORIZONS,
        attach_future_target,
    )
    from backend.services.training_eligibility import (
        filter_training_eligible_dataframe,
    )

    per_horizon: Dict[int, int] = {}
    errors: List[str] = []

    eligible = filter_training_eligible_dataframe(df)
    if eligible.empty:
        errors.append(
            f"no training-eligible rows among {len(df)}: every row is excluded by "
            f"the live/non-synthetic/plausible-fare rule, so no horizon can be "
            f"labelled"
        )
        return per_horizon, errors

    for h in SUPPORTED_TRAINING_HORIZONS:
        try:
            per_horizon[int(h)] = int(len(attach_future_target(eligible, int(h))))
        except ValueError as exc:
            errors.append(f"horizon {int(h)} cannot be labelled: {exc}")

    return per_horizon, errors


def run_dataset_doctor(filepath: str = None) -> int:
    """Diagnose the training corpus. Returns 0 (pass), 1 (warnings), 2 (fail)."""
    print("=" * 68)
    print("       SkyMind -- Dataset Doctor")
    print("=" * 68)

    try:
        df, source = _load_corpus(filepath)
    except RuntimeError as exc:
        print(f" [FAIL] Corpus not available: {exc}")
        print("-" * 68)
        print(" DATASET DOCTOR RESULT: FAIL (nothing to diagnose)")
        return EXIT_FAIL

    print(f" Source: {source}")
    print(f" Rows:   {len(df)}")
    print("-" * 68)

    issues: List[str] = []
    warnings: List[str] = []
    checks = 0

    # 1. A frame with no rows passes every integrity check below vacuously, so it
    #    is refused here rather than graded. This is the same shape as an R² of
    #    1.0 over an empty fold: no counter-example found is not evidence.
    checks += 1
    if len(df) == 0:
        print(" [FAIL] Non-empty corpus:          0 rows")
        issues.append("corpus is empty")
    else:
        print(f" [OK]   Non-empty corpus:          PASS ({len(df)} rows)")

    # 2. Schema & mandatory columns
    checks += 1
    missing_cols = [c for c in MANDATORY_RAW_COLUMNS if c not in df.columns]
    if not missing_cols:
        print(f" [OK]   Mandatory columns:         PASS ({len(MANDATORY_RAW_COLUMNS)} present)")
    else:
        print(f" [FAIL] Mandatory columns:         missing {missing_cols}")
        issues.append(f"missing mandatory columns: {missing_cols}")

    # 3. Prohibited empty columns. A column that is absent altogether used to be
    #    counted towards "0 empty columns detected" — a claim about columns that
    #    are not there. Absence is reported under its own name; whether it should
    #    block an export is a schema decision, not this tool's to make.
    checks += 1
    empty_p_cols = [c for c in PROHIBITED_EMPTY_COLUMNS
                    if c in df.columns and df[c].isna().all()]
    absent_p_cols = [c for c in PROHIBITED_EMPTY_COLUMNS if c not in df.columns]
    if empty_p_cols:
        print(f" [FAIL] Prohibited empty columns:  wholly null {empty_p_cols}")
        issues.append(f"empty columns: {empty_p_cols}")
    elif absent_p_cols:
        print(f" [WARN] Prohibited empty columns:  {absent_p_cols} not present at all")
        warnings.append(f"columns absent, so never derived: {absent_p_cols}")
    else:
        print(" [OK]   Prohibited empty columns:  PASS (all present and populated)")

    # 4. days_until_dep calendar subtraction
    checks += 1
    if "days_until_dep" not in df.columns:
        print(" [WARN] Calendar subtraction:      no 'days_until_dep' column to check")
        warnings.append("no days_until_dep column")
    else:
        # Counted by outcome rather than by `not validate(...)`. The boolean form
        # returns False both for "the stored integer disagrees with the dates" and
        # for "the timestamp could not be read", and this line used to add them
        # together and print the total as "date mismatches". On a real Supabase
        # export that read 35,894 of 35,894 — because `parse_to_date` could not
        # parse a `+00` offset on Python 3.10, not because any row disagreed. The
        # true mismatch count for that corpus is 14,257, all off by exactly one
        # day, from `days_until_dep` being computed in IST against a `recorded_at`
        # stored in UTC. Two different findings with two different fixes.
        verdicts = Counter(
            classify_days_until_dep_row(row) for row in df.to_dict(orient="records")
        )
        mismatches = verdicts["mismatch"]
        unreadable = verdicts["unreadable"]
        if mismatches == 0 and unreadable == 0:
            print(" [OK]   Calendar subtraction:      PASS (0 off-by-one errors)")
        else:
            parts = []
            if mismatches:
                parts.append(f"{mismatches} date mismatches")
            if unreadable:
                parts.append(f"{unreadable} unreadable timestamps")
            print(f" [FAIL] Calendar subtraction:      {', '.join(parts)}")
            issues.extend(
                f"{mismatches} days_until_dep mismatches" if kind == "mismatch"
                else f"{unreadable} rows with an unreadable departure or observation date"
                for kind in ("mismatch", "unreadable") if verdicts[kind]
            )

    # 5. Duplicate snapshots
    #
    # A duplicate is one curve identity, at one observation time, at one fare,
    # recorded twice. The identity has to be whole for the question to mean
    # anything: on a narrower key two of a carrier's departures that share a fare
    # are indistinguishable, and `PASS (0 over 6 keys)` would be printed over a key
    # that cannot tell them apart. Missing components are named rather than
    # dropped, which is what `duplicate_plugin` — the code that acts on this
    # judgement by deleting rows — now does too.
    checks += 1
    dedup_keys = CURVE_KEYS + ["recorded_at", "price"]
    actual_keys = [k for k in dedup_keys if k in df.columns]
    missing_identity = [k for k in CURVE_KEYS if k not in df.columns]
    dups = (int(df.duplicated(subset=actual_keys).sum())
            if actual_keys and not missing_identity else 0)
    if not actual_keys:
        print(" [WARN] Duplicate snapshots:       no key columns to deduplicate on")
        warnings.append("no columns to check duplicates against")
    elif missing_identity:
        print(" [WARN] Duplicate snapshots:       not checked, no curve identity "
              f"({', '.join(missing_identity)} absent)")
        warnings.append(
            "duplicate snapshots unchecked: the frame is missing "
            f"{', '.join(missing_identity)}, so two departures of one carrier on a "
            "route and date cannot be distinguished"
        )
    elif dups == 0:
        print(f" [OK]   Duplicate snapshots:       PASS (0 over {len(actual_keys)} keys)")
    else:
        print(f" [WARN] Duplicate snapshots:       {dups} duplicate rows")
        warnings.append(f"{dups} duplicate snapshots")

    # 6. Price positivity
    checks += 1
    if "price" not in df.columns:
        print(" [FAIL] Price positivity:          no 'price' column")
        issues.append("no price column")
    else:
        prices = pd.to_numeric(df["price"], errors="coerce")
        invalid = int((prices <= 0).sum())
        unparsed = int(prices.isna().sum())
        if invalid == 0 and unparsed == 0:
            print(f" [OK]   Price positivity:          PASS (all {len(prices)} fares > 0)")
        else:
            print(f" [FAIL] Price positivity:          {invalid} non-positive, "
                  f"{unparsed} unparseable")
            issues.append(f"{invalid} non-positive and {unparsed} unparseable fares")

    # 7. Stable itinerary id
    checks += 1
    if "itinerary_id" in df.columns:
        print(f" [OK]   Stable itinerary id:       PASS ({df['itinerary_id'].nunique()} unique)")
    else:
        print(" [WARN] Stable itinerary id:       column 'itinerary_id' missing")
        warnings.append("missing itinerary_id column")

    # 8. Booking-curve shape — the check that answers "can I train yet?". None of
    #    the checks above looks at it, and it is the one that decides: a row is
    #    only labelled if its own curve carries a later observation.
    checks += 1
    shape = booking_curve_shape(df)
    floor = training_policy.min_shifted_rows
    labelled_ceiling = shape["rows_on_multi_observation_curves"]
    print(f" ...    Booking curves:            {shape['curves']} curve(s), longest "
          f"{shape['longest_curve']} observation(s), "
          f"{shape['single_observation_curves']} seen once")
    if not shape["curve_keys_present"]:
        print(" [WARN] Trainable rows:            cannot tell — no curve key columns")
        warnings.append("no curve key columns, so trainability is unknown")
    elif labelled_ceiling < floor:
        print(f" [WARN] Trainable rows:            at most {labelled_ceiling}, "
              f"below the {floor} TrainingPolicy requires")
        warnings.append(
            f"at most {labelled_ceiling} labellable rows against a floor of {floor}: "
            f"training will be refused for every horizon"
        )
    else:
        print(f" [OK]   Trainable rows:            PASS (at most {labelled_ceiling} "
              f"labellable, floor {floor})")

    # 9. What each horizon actually gets, from the shipped labeller.
    #
    # The ceiling above is an upper bound over all horizons at once: it counts
    # every row whose curve carries *any* later observation. It answers "could a
    # label exist", not "does one exist for the horizon being trained". Those
    # diverge enormously in practice. On a 35,894-row export whose ceiling is
    # 13,226 the shipped labeller returns 149 rows at 1 day, 2,114 at 3 days and 1
    # at 7 days, because the corpus was collected on nine calendar days with 82%
    # of the rows on two of them — a `PASS (at most 13226)` line beside that is
    # true and still leaves the reader with the wrong conclusion.
    #
    # `attach_future_target` is the one definition of the label, so this reports
    # what training will actually receive rather than a second estimate of it.
    checks += 1
    if not shape["curve_keys_present"]:
        print(" [WARN] Per-horizon labels:        cannot tell — no curve key columns")
        warnings.append("no curve key columns, so per-horizon label counts are unknown")
    else:
        per_horizon, label_errors = _labelled_rows_by_horizon(df)
        # Every error, not just the first, and as an issue rather than a warning:
        # each one is a horizon that cannot be labelled at all, which is a harder
        # finding than a horizon that is merely short of rows.
        for msg in label_errors:
            print(f" [FAIL] Per-horizon labels:        {msg}")
            issues.append(msg)
        if per_horizon:
            rendered = ", ".join(f"{h}d={n}" for h, n in sorted(per_horizon.items()))
            starved = sorted(h for h, n in per_horizon.items() if n < floor)
            if not starved:
                print(f" [OK]   Per-horizon labels:        PASS ({rendered}; floor {floor})")
            else:
                # A warning, and deliberately the same grade check 8 gives the same
                # fact. Both lines say "this corpus is too small to train"; graded
                # differently they had one tool return FAIL and PARTIAL for one
                # finding, and the FAIL was the one the exit code carried.
                #
                # FAIL has to keep meaning "the corpus is damaged". A corpus
                # collected honestly from the first day is short of 100 labels at
                # every horizon for weeks — that is the expected reading during
                # collection, not a defect, and if it renders as FAIL then FAIL is
                # the normal state and stops telling the operator anything. The
                # shortfall is still named per horizon, the verdict still says
                # PARTIAL rather than PASS, and EXIT_WARN is still non-zero, so
                # nothing that gates on a zero exit code begins to pass.
                print(f" [WARN] Per-horizon labels:        {rendered} — "
                      f"horizon(s) {starved} below the floor of {floor}")
                warnings.append(
                    f"horizon(s) {starved} have fewer than {floor} labelled rows "
                    f"({rendered}); training will be refused for them however many "
                    f"raw rows the corpus holds"
                )
        elif not label_errors:
            print(" [FAIL] Per-horizon labels:        no horizon returned any "
                  "labelled rows")
            issues.append("no declared horizon can be labelled from this corpus")

    print("-" * 68)

    # The verdict states what was graded and how far the checks reach. It used to
    # read "PASS (Dataset v2.0 is 100% production-ready for ML)", which is a claim
    # about model readiness that schema and integrity checks cannot support.
    scope = f"{checks} schema, integrity and curve-shape checks over {len(df)} row(s)"
    if issues:
        print(f" DATASET DOCTOR RESULT: FAIL — {scope}")
        for issue in issues:
            print(f"  - {issue}")
        return EXIT_FAIL

    if warnings:
        print(f" DATASET DOCTOR RESULT: PARTIAL — {scope}, with warnings")
        for warn in warnings:
            print(f"  - {warn}")
        return EXIT_WARN

    print(f" DATASET DOCTOR RESULT: PASS — {scope} found no defects.")
    print(" This is a data-integrity verdict, not a model-readiness one: whether a")
    print(" fitted model is servable is decided by the acceptance gate in")
    print(" backend/ml/price_model.py, which measures skill against a baseline.")
    return EXIT_PASS


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SkyMind Dataset Doctor CLI")
    parser.add_argument("--file", help="Path to exported dataset file", default=None)
    args = parser.parse_args()

    sys.exit(run_dataset_doctor(filepath=args.file))
