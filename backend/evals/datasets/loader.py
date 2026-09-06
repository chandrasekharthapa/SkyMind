"""Versioned Dataset Loader for SkyMind Evaluation Platform.

`load_dataset` used to call `validate_dataset_schema`, log the errors at ERROR level
and return the records anyway, with no value returned or recorded that a caller could
branch on. A dataset with duplicate IDs, a missing `expected` block or no provenance
fields therefore produced a full evaluation run and a report whose "Benchmark
Validity" line was computed without reference to whether the benchmark's own schema
had held. The errors are now recorded on `last_schema_errors` so the environment
inspector can report them, and `strict=True` refuses the load outright.

**`version` was a dead parameter.** The directory was hardcoded — `v_dir =
os.path.join(self.base_dir, "v2.0")` — and `version` appeared only inside log and
error strings. So `load_dataset(version="3.1.4")` returned the v2.0 corpus and
reported success, and every report stamped "Dataset Version: <whatever config
said>" over records nothing had checked the provenance of. `_resolve_version_dir`
makes the argument select a directory, and the legacy `benchmark_dataset_v1.json`
fallback now applies only to the 1.x version it actually contains rather than to
any version whose directory happens to be absent.

The manifest is cross-checked too. `datasets/v2.0/metadata.json` declared
`total_records: 120` and `tiers.smoke: 25` beside a corpus of 15 records and 6
smoke cases, and nothing in the codebase read the file, so the numbers in
`evals/README.md` were traceable to a manifest that had never been true. A
declared count that disagrees with the corpus is now a schema error, which is the
same channel a malformed record travels down.
"""

import os
import json
import logging
import re
from typing import List, Dict, Any, Optional
from backend.evals.datasets.validator import validate_dataset_schema

logger = logging.getLogger(__name__)

# `2.0.0` lives in `v2.0`: the directory carries major.minor, the version carries
# the patch level too. Anything that is not a dotted numeric version resolves to no
# directory at all, which is the correct answer for a version that does not exist.
_VERSION_RE = re.compile(r"^(\d+)\.(\d+)")

# The converted legacy corpus stamps `dataset_version: "1.0.0"` on every record, so
# it is the 1.x dataset and only a 1.x request may be served from it.
_LEGACY_MAJOR = "1"


class DatasetSchemaError(RuntimeError):
    """Raised by `load_dataset(strict=True)` when the dataset violates its schema."""


class DatasetLoader:
    """Loads and filters versioned JSONL evaluation datasets."""

    def __init__(self, base_dir: Optional[str] = None):
        self.base_dir = base_dir or os.path.dirname(os.path.abspath(__file__))
        # Populated by every `load_dataset` call: [] means "validated, no errors",
        # and a non-empty list is the reason the benchmark is not fully valid.
        self.last_schema_errors: List[str] = []
        self.last_source: str = "none"

    def load_jsonl(self, filepath: str) -> List[Dict[str, Any]]:
        """Reads a JSONL file and returns parsed records."""
        if not os.path.isfile(filepath):
            logger.warning(f"[DatasetLoader] File not found: '{filepath}'")
            return []
        records = []
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        return records

    def _resolve_version_dir(self, version: str) -> Optional[str]:
        """The directory holding `version`, or None if there is no such directory.

        Returning None is what makes the parameter real: a version nobody has
        published has no corpus, and the caller must be told that rather than
        handed whichever corpus happens to be on disk.
        """
        match = _VERSION_RE.match(str(version or "").strip())
        if not match:
            return None
        candidate = os.path.join(self.base_dir, f"v{match.group(1)}.{match.group(2)}")
        return candidate if os.path.isdir(candidate) else None

    def _manifest_errors(self, v_dir: str, version: str,
                         records: List[Dict[str, Any]]) -> List[str]:
        """Ways `metadata.json` disagrees with the corpus sitting next to it.

        An absent manifest is not an error — an unstamped corpus is just unstamped.
        A manifest that states a count or a version the corpus contradicts is,
        because every downstream report quotes it as provenance.
        """
        path = os.path.join(v_dir, "metadata.json")
        if not os.path.isfile(path):
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            return [f"metadata.json beside the corpus could not be read: {exc}"]

        errors: List[str] = []
        declared_version = manifest.get("dataset_version")
        if declared_version and str(declared_version) != str(version):
            errors.append(f"metadata.json declares dataset_version "
                          f"'{declared_version}' but version '{version}' was requested")
        declared_total = manifest.get("total_records")
        if isinstance(declared_total, int) and declared_total != len(records):
            errors.append(f"metadata.json declares total_records={declared_total} "
                          f"but {len(records)} record(s) are present in golden.jsonl")
        return errors

    def load_dataset(self, version: str = "2.0.0", tier: Optional[str] = None,
                     strict: bool = False) -> List[Dict[str, Any]]:
        """Loads the corpus for `version`, filtered to `tier`.

        Records the schema-validation outcome on `self.last_schema_errors` in every
        branch, so a caller can tell "validated clean" from "not validated" from
        "validated and failed". With `strict=True`, a schema failure raises
        `DatasetSchemaError` instead of being logged and ignored.
        """
        self.last_schema_errors = []
        v_dir = self._resolve_version_dir(version)
        golden_file = os.path.join(v_dir, "golden.jsonl") if v_dir else None

        if not golden_file or not os.path.isfile(golden_file):
            # The legacy corpus is a 1.x corpus — every record it converts is stamped
            # `dataset_version: "1.0.0"` — so it answers a 1.x request and nothing
            # else. Serving it for an unknown version is how `version` came to be
            # decorative: the fallback fired whenever the directory was missing,
            # which is always true of a version that does not exist.
            legacy_path = os.path.join(os.path.dirname(self.base_dir), "benchmark_dataset_v1.json")
            wants_legacy = str(version or "").strip().split(".")[0] == _LEGACY_MAJOR
            if wants_legacy and os.path.isfile(legacy_path):
                with open(legacy_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    records = []
                    for tc in data.get("test_cases", []):
                        records.append({
                            "id": tc.get("id"),
                            "dataset_version": "1.0.0",
                            "source": "human",
                            "reviewed": True,
                            "difficulty": "medium",
                            "priority": "high",
                            "tier": "smoke" if tc.get("id") in ("TC_001", "TC_002", "TC_009") else "full",
                            "regression": tc.get("is_adversarial", False),
                            "created_by": "legacy_v1",
                            "tags": [tc.get("category", "general")],
                            "inputs": {"query": tc.get("query", "")},
                            "expected": {
                                "intent": tc.get("expected_intent"),
                                "entities": tc.get("expected_entities", {}),
                                "required_tools": tc.get("expected_tools", []),
                                "requires_clarification": False
                            }
                        })
                    self.last_source = f"legacy:{os.path.basename(legacy_path)}"
                    # The converted records are built here, so they are validated
                    # here too rather than trusted for having been constructed.
                    valid, errors = validate_dataset_schema(records)
                    if not valid:
                        self.last_schema_errors = errors
                        if strict:
                            raise DatasetSchemaError(
                                f"legacy dataset failed schema validation with "
                                f"{len(errors)} error(s): {errors[:3]}")
                        logger.error(f"[DatasetLoader] Legacy dataset schema errors: {errors}")
                    return records
            self.last_source = "missing"
            self.last_schema_errors = [
                f"no corpus for dataset version '{version}': no 'v<major>.<minor>' "
                f"directory under '{self.base_dir}' holds a golden.jsonl for it"
            ]
            if strict:
                raise DatasetSchemaError(self.last_schema_errors[0])
            logger.warning("[DatasetLoader] %s", self.last_schema_errors[0])
            return []

        self.last_source = os.path.relpath(golden_file, self.base_dir)
        records = self.load_jsonl(golden_file)
        valid, errors = validate_dataset_schema(records)
        problems = list(errors) if not valid else []
        problems.extend(self._manifest_errors(v_dir, version, records))
        if problems:
            self.last_schema_errors = problems
            if strict:
                raise DatasetSchemaError(
                    f"dataset version '{version}' failed validation with "
                    f"{len(problems)} error(s): {problems[:3]}")
            logger.error(f"[DatasetLoader] Validation failed for dataset version '{version}': {problems}")

        if tier:
            filtered = [r for r in records if r.get("tier") == tier or tier == "full"]
            return filtered

        return records


dataset_loader = DatasetLoader()
