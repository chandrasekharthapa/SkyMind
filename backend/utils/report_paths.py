"""Where a generated report is allowed to land, and how a failed write is seen.

Four services — `historical_data_audit`, `feature_validation`, `drift_detection`
and `production_readiness` — each defined their own destination as

    sys_dir = os.path.dirname(os.path.abspath(__file__))
    REPORT_PATH = os.path.join(os.path.dirname(sys_dir), "..", "<name>.json")

which resolves to the repository root. All four of those files are tracked, so
*running the test suite rewrote version-controlled files*. A full-suite sweep on
2026-09-01 replaced a committed `historical_data_report.json` reading
`total_observations: 1000, status: "PASS"` with one reading `0` and `"FAIL"`, and
did the same to `drift_report.json`, `feature_validation_report.json` and
`production_readiness_report.json`. Nothing in the codebase reads any of the four
— they are write-only artifacts — so the fix is to send them somewhere a run is
expected to write, rather than into the tree that records what the project is.

The default is `backend/reports/`, gitignored. It is anchored to this file rather
than to the process's working directory, so `python -m backend.run_pipeline` from
the repository root and `pytest` from `backend/` agree on one location. (That is
the same failure mode as the `backend/backend/` tripwire in `.gitignore`, arrived
at from the opposite direction: anchoring alone is not enough if the anchor
points at tracked content.)

Every writer also accepts an explicit destination, so a test can point at
`tmp_path` and then assert against the file the run actually produced instead of
against whatever version control happens to be holding at that path.
"""

import json
import logging
import os
from typing import Any, Dict

logger = logging.getLogger(__name__)

_UTILS_DIR = os.path.dirname(os.path.abspath(__file__))

#: `backend/`, resolved from this file.
BACKEND_DIR = os.path.dirname(_UTILS_DIR)

#: Default destination for every generated report. Gitignored.
REPORTS_DIR = os.path.join(BACKEND_DIR, "reports")


def report_path(name: str) -> str:
    """Absolute default path for a generated report.

    `name` is the bare filename the service has always used, e.g.
    ``"drift_report.json"``, so the artifact keeps its name and only its
    directory changes.
    """
    return os.path.join(REPORTS_DIR, name)


def write_report(report: Dict[str, Any], path: str) -> None:
    """Write `report` to `path` as JSON, recording the outcome in `report`.

    A failed write used to be a `logger.warning` and nothing else, in four
    separate copies of this function. A caller holding the returned dict could
    not tell whether the artifact it describes exists on disk — and
    `production_readiness` embeds these sub-reports verbatim in its own output,
    so the ambiguity propagated. On success the report gains
    ``report_written_to``; on failure ``report_write_error``.

    The write stays non-fatal on purpose: an audit that measured the data
    correctly should not become a 500 because a disk was full. The distinction
    now shows up in the artifact instead of only in a log nobody is reading.

    ``report_written_to`` is set *before* the dump so that the file on disk and
    the dict handed back are the same document — a test can round-trip one
    against the other. It is removed again if the write fails.
    """
    report["report_written_to"] = path
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w") as fh:
            json.dump(report, fh, indent=2)
    except Exception as err:
        report.pop("report_written_to", None)
        report["report_write_error"] = f"{type(err).__name__}: {err}"
        logger.warning("Failed to write %s: %s", path, err)
