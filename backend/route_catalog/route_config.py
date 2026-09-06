"""Route Configuration Loader.

Loads the centralized domestic route catalog and collector configuration
from backend/route_catalog/routes.yaml (with JSON fallback).
Provides deterministic batching and helper accessors.
"""

import os
import json
import logging
from typing import List, Tuple, Dict, Any, Optional

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

logger = logging.getLogger(__name__)

CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))
YAML_PATH = os.path.join(CONFIG_DIR, "routes.yaml")
JSON_PATH = os.path.join(CONFIG_DIR, "routes.json")

DEFAULT_DEPARTURE_BUCKETS = [1, 2, 3, 5, 7, 10, 14, 21, 30, 45, 60, 75, 90]
DEFAULT_BATCH_SIZE = 8
DEFAULT_MAX_WORKERS = 4
DEFAULT_RETRY_ATTEMPTS = 3
DEFAULT_RETRY_BACKOFF = 30

BASELINE_CONFIG: Dict[str, Any] = {
    "collector": {
        "batch_size": DEFAULT_BATCH_SIZE,
        "max_workers": DEFAULT_MAX_WORKERS,
        "retry_attempts": DEFAULT_RETRY_ATTEMPTS,
        "retry_backoff_seconds": DEFAULT_RETRY_BACKOFF,
        "departure_buckets": DEFAULT_DEPARTURE_BUCKETS,
    },
    "routes": [
        {"origin": "DEL", "destination": "BOM", "enabled": True, "priority": 100},
        {"origin": "BOM", "destination": "DEL", "enabled": True, "priority": 100},
        {"origin": "DEL", "destination": "BLR", "enabled": True, "priority": 95},
        {"origin": "BLR", "destination": "DEL", "enabled": True, "priority": 95},
    ],
}


def routes_from(raw: Any) -> List[Tuple[str, str]]:
    """The enabled, well-formed routes in a raw config payload, deterministically ordered.

    Module-level and used twice: `load_config` accepts a config file only if this
    returns something, and `get_active_routes` answers with it. One predicate, so
    "the catalogue loaded" cannot mean something different from "the catalogue has
    routes to collect".
    """
    if not isinstance(raw, dict):
        return []
    raw_routes = raw.get("routes")
    if not isinstance(raw_routes, list):
        return []

    enabled_routes = []
    for r in raw_routes:
        if not isinstance(r, dict):
            continue
        if not r.get("enabled", True):
            continue
        orig = str(r.get("origin", "")).strip().upper()
        dest = str(r.get("destination", "")).strip().upper()
        try:
            priority = int(r.get("priority", 50))
        except (TypeError, ValueError):
            # A typo in one route's priority must not take out the catalogue, but
            # it must not be silent either: the order routes are collected in is
            # what this field decides.
            logger.warning(
                "[RouteCatalogConfig] %s->%s has a non-numeric priority %r; using 50.",
                orig, dest, r.get("priority"))
            priority = 50
        if len(orig) == 3 and len(dest) == 3 and orig != dest:
            enabled_routes.append((priority, orig, dest))

    # Highest priority first, then origin, then destination.
    enabled_routes.sort(key=lambda x: (-x[0], x[1], x[2]))

    unique_routes = []
    seen = set()
    for _, orig, dest in enabled_routes:
        key = (orig, dest)
        if key not in seen:
            seen.add(key)
            unique_routes.append(key)
    return unique_routes


class RouteCatalogConfig:
    """Centralized, configuration-driven route catalog & collector hyperparameters."""

    def __init__(self, yaml_file: str = YAML_PATH, json_file: str = JSON_PATH):
        self.yaml_file = yaml_file
        self.json_file = json_file
        self._raw_config: Dict[str, Any] = {}
        # Which file the live catalogue actually came from. Nothing downstream
        # could previously tell the 52-route file apart from the 4-route built-in
        # baseline, so a run that collected 4 routes looked like a normal run.
        self.config_source: str = "unloaded"
        self.load_config()

    def load_config(self) -> None:
        """Load the catalogue from YAML, else JSON, else the built-in baseline.

        A source is accepted only if it parses to a mapping that yields at least
        one usable route, by the same `routes_from` predicate `get_active_routes`
        answers with. This used to be `self._raw_config = yaml.safe_load(f) or {}`
        followed by `logger.info("Successfully loaded...")` and a `return`, so an
        empty routes.yaml, a comments-only one, or one whose top level is not a
        mapping was reported as a *successful* load, left the catalogue with zero
        routes, and skipped the JSON file beside it holding all 52. Downstream the
        scheduler failed closed with "no routes to collect" — right behaviour,
        wrong file to go looking at, because the log said the catalogue had loaded.
        """
        candidates: List[Tuple[str, str, Any]] = []
        if HAS_YAML:
            candidates.append(("YAML", self.yaml_file, yaml.safe_load))
        elif os.path.exists(self.yaml_file):
            logger.warning(
                "[RouteCatalogConfig] PyYAML is not installed, so %s cannot be read; "
                "trying the JSON catalogue instead.", self.yaml_file)
        candidates.append(("JSON", self.json_file, json.load))

        for label, path, parse in candidates:
            if not os.path.exists(path):
                continue
            try:
                with open(path, "r", encoding="utf-8") as f:
                    raw = parse(f)
            except Exception as e:
                logger.warning(
                    "[RouteCatalogConfig] %s catalogue %s is unreadable (%s: %s).",
                    label, path, type(e).__name__, e)
                continue

            usable = routes_from(raw)
            if not usable:
                logger.error(
                    "[RouteCatalogConfig] %s catalogue %s parsed as %s and yields no usable "
                    "route; not accepting it as the catalogue.", label, path, type(raw).__name__)
                continue

            self._raw_config = raw
            self.config_source = path
            logger.info(
                "[RouteCatalogConfig] Loaded %d route(s) from %s (%s).", len(usable), path, label)
            return

        self._raw_config = dict(BASELINE_CONFIG)
        self.config_source = "builtin-baseline"
        logger.error(
            "[RouteCatalogConfig] No usable route catalogue at %s or %s. Falling back to the "
            "built-in %d-route baseline; collection will cover those routes only.",
            self.yaml_file, self.json_file, len(routes_from(self._raw_config)))

    def get_collector_config(self) -> Dict[str, Any]:
        """Returns collector configuration block, or {} if it is not a mapping.

        `self._raw_config.get("collector", {})` returned whatever was there, so a
        `collector:` written as a list or a string raised AttributeError inside
        `get_batch_size` — a crash three frames from the typo that caused it.
        """
        collector = self._raw_config.get("collector")
        return collector if isinstance(collector, dict) else {}

    def get_departure_buckets(self) -> List[int]:
        """Returns ordered departure horizon buckets.

        Validated rather than returned as-is: `departure_buckets: []` made the
        collector run zero searches per route, which reads downstream as an
        ingestion run that scraped nothing rather than as a config with no horizons
        in it.
        """
        collector = self.get_collector_config()
        raw = collector.get("departure_buckets", DEFAULT_DEPARTURE_BUCKETS)
        buckets: List[int] = []
        if isinstance(raw, list):
            for value in raw:
                if isinstance(value, bool) or not isinstance(value, int):
                    continue
                if value >= 0 and value not in buckets:
                    buckets.append(value)
        if not buckets:
            logger.error(
                "[RouteCatalogConfig] departure_buckets in %s is %r, which contains no usable "
                "horizon; using the built-in %d.", self.config_source, raw,
                len(DEFAULT_DEPARTURE_BUCKETS))
            return list(DEFAULT_DEPARTURE_BUCKETS)
        return buckets

    def get_batch_size(self) -> int:
        """Returns batch size for automatic route chunking."""
        collector = self.get_collector_config()
        return int(collector.get("batch_size", DEFAULT_BATCH_SIZE))

    def get_worker_count(self) -> int:
        """Returns maximum worker concurrency limit."""
        collector = self.get_collector_config()
        return int(collector.get("max_workers", DEFAULT_MAX_WORKERS))

    def get_retry_attempts(self) -> int:
        """Returns max retry attempts per failed collection."""
        collector = self.get_collector_config()
        return int(collector.get("retry_attempts", DEFAULT_RETRY_ATTEMPTS))

    def get_retry_backoff_seconds(self) -> int:
        """Returns backoff delay between retry attempts."""
        collector = self.get_collector_config()
        return int(collector.get("retry_backoff_seconds", DEFAULT_RETRY_BACKOFF))

    def get_active_routes(self) -> List[Tuple[str, str]]:
        """Enabled routes, highest priority first, then origin, then destination.

        Delegates to the module-level `routes_from`, which `load_config` also uses
        to decide whether a config file is usable at all.
        """
        return routes_from(self._raw_config)

    def create_route_batches(self, batch_size: Optional[int] = None) -> List[List[Tuple[str, str]]]:
        """
        Deterministically chunks active routes into batches of specified size.
        If batch_size is None, uses batch_size from collector config.
        """
        bs = batch_size or self.get_batch_size()
        if bs <= 0:
            bs = DEFAULT_BATCH_SIZE

        routes = self.get_active_routes()
        batches = []
        for i in range(0, len(routes), bs):
            batches.append(routes[i:i + bs])
        return batches


# Global singleton instance
route_catalog_config = RouteCatalogConfig()
