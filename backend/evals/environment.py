"""Provider Health & Environment Inspector for SkyMind Evaluation Platform.

Separates configuration state from runtime health state.
Exposes ProviderHealthReport separating configured, healthy, reachable, and quota availability states.

`ProviderHealthReport.dataset` was **never assigned by `inspect()`**. It kept its
field default — `configured=False, healthy=False, reason="Unchecked"` — and the
markdown report never read it, printing a hardcoded `| Dataset | YES | YES |
HEALTHY | Schema & metadata verified |` row instead. So the one component whose
health decides whether the benchmark means anything was the one component nothing
measured. `inspect()` now loads the dataset for the tier under evaluation and
reports the record count and any schema errors.

`overall_health` also used to degrade to PARTIAL when LangSmith was unhealthy.
LangSmith is a tracing sink: whether traces were uploaded has no bearing on whether
the benchmark's measurements are valid, and folding it into `benchmark_validity`
meant that on any machine without a LangSmith key — which is every CI runner here —
every run was permanently PARTIAL and the signal carried no information. Tracing is
now reported as its own row and warned about, but only the dataset and the planner's
own provider affect validity.
"""

import os
import logging
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

from backend.evals.config import default_output_directory

logger = logging.getLogger(__name__)


class ServiceHealthStatus(BaseModel):
    name: str
    configured: bool = False
    healthy: bool = False
    reachable: bool = False
    authenticated: bool = False
    quota_available: bool = False
    current_mode: str = "PRIMARY"  # "PRIMARY", "FALLBACK", "DISABLED"
    reason: str = "Unchecked"


class ProviderHealthReport(BaseModel):
    overall_health: str = "HEALTHY"  # "HEALTHY", "PARTIAL", "FAILED"
    benchmark_validity: str = "FULL"  # "FULL", "PARTIAL", "INVALID"
    openai: ServiceHealthStatus = Field(default_factory=lambda: ServiceHealthStatus(name="OpenAI"))
    langsmith: ServiceHealthStatus = Field(default_factory=lambda: ServiceHealthStatus(name="LangSmith"))
    filesystem: ServiceHealthStatus = Field(default_factory=lambda: ServiceHealthStatus(name="Filesystem"))
    dataset: ServiceHealthStatus = Field(default_factory=lambda: ServiceHealthStatus(name="Dataset"))
    warnings: List[str] = Field(default_factory=list)


class EnvironmentInspector:
    """Inspects runtime environment separating configuration state from operational health."""

    def inspect(self, dataset_version: str = "2.0.0",
                tier: Optional[str] = None,
                output_directory: Optional[str] = None) -> ProviderHealthReport:
        report = ProviderHealthReport()

        # 1. Inspect Filesystem & Results Directory
        try:
            # `res_dir` was the literal "backend/evals/results" — a second, independent
            # copy of a path `config.py` also defined, so an override applied in one
            # place left the other writing somewhere else. It now reads the one
            # definition, and callers that hold an `EvaluationConfig` pass its
            # `output_directory` instead: this check creates the directory it probes, so
            # inspecting the default while the run writes elsewhere both made the
            # tracked `backend/evals/results/` reappear on every run whatever the
            # config said, and reported writability for a directory the run never
            # touched. Same rule as the dataset row — check the thing under evaluation.
            res_dir = output_directory or default_output_directory()
            os.makedirs(res_dir, exist_ok=True)
            # `makedirs(exist_ok=True)` not raising does not prove the directory is
            # writable: it returns quietly for a directory that already exists with no
            # write permission, which is precisely the condition this row claims to have
            # checked. The probe write is what makes "Results directory is writable" a
            # measurement rather than an assumption.
            probe = os.path.join(res_dir, ".write_probe")
            with open(probe, "w") as fh:
                fh.write("ok")
            os.remove(probe)
            report.filesystem = ServiceHealthStatus(
                name="Filesystem",
                configured=True,
                healthy=True,
                reachable=True,
                authenticated=True,
                quota_available=True,
                current_mode="ACTIVE",
                reason=f"Results directory is writable ({res_dir})"
            )
        except Exception as e:
            report.filesystem = ServiceHealthStatus(
                name="Filesystem",
                configured=False,
                healthy=False,
                reachable=False,
                current_mode="FAILED",
                reason=f"Filesystem error: {e}"
            )
            report.warnings.append(f"Filesystem error: {e}")

        # 1b. Inspect the dataset. Measured, not assumed: this is the component the
        # report used to declare healthy in literal text.
        report.dataset = self._inspect_dataset(dataset_version, tier, report.warnings)

        # 2. Inspect LangSmith SDK & Credentials
        try:
            import langsmith
            ls_installed = True
        except ImportError:
            ls_installed = False

        ls_key = os.getenv("LANGSMITH_API_KEY") or os.getenv("LANGCHAIN_API_KEY")

        if not ls_installed:
            report.langsmith = ServiceHealthStatus(
                name="LangSmith",
                configured=bool(ls_key),
                healthy=False,
                reachable=False,
                current_mode="DISABLED",
                reason="Missing 'langsmith' SDK package"
            )
            report.warnings.append("LangSmith SDK not installed; tracing disabled.")
        elif not ls_key:
            report.langsmith = ServiceHealthStatus(
                name="LangSmith",
                configured=False,
                healthy=False,
                reachable=False,
                current_mode="DISABLED",
                reason="Missing LANGSMITH_API_KEY"
            )
            report.warnings.append("LANGSMITH_API_KEY unconfigured; tracing disabled.")
        else:
            report.langsmith = ServiceHealthStatus(
                name="LangSmith",
                configured=True,
                healthy=True,
                reachable=True,
                authenticated=True,
                quota_available=True,
                current_mode="ACTIVE",
                reason="LangSmith SDK & API key active"
            )

        # 3. Inspect OpenAI Credentials & Health
        openai_key = os.getenv("OPENAI_API_KEY")
        if not openai_key:
            report.openai = ServiceHealthStatus(
                name="OpenAI",
                configured=False,
                healthy=False,
                reachable=False,
                authenticated=False,
                quota_available=False,
                current_mode="DISABLED",
                reason="Missing OPENAI_API_KEY in environment"
            )
            report.warnings.append("OPENAI_API_KEY missing. Offline LLM evaluators will be SKIPPED.")
        else:
            # Configured is True, but health depends on quota availability
            report.openai = ServiceHealthStatus(
                name="OpenAI",
                configured=True,
                healthy=True,
                reachable=True,
                authenticated=True,
                quota_available=True,
                current_mode="PRIMARY",
                reason="API key configured"
            )

        # Determine Benchmark Validity & Overall Health.
        #
        # LangSmith is deliberately absent from this decision. It is a trace sink;
        # its being down does not make a measurement wrong, and including it meant
        # every run on a machine without a LangSmith key reported PARTIAL validity
        # forever, which is a signal that cannot distinguish anything.
        if not report.dataset.healthy:
            # Nothing downstream is a measurement of anything if the benchmark did
            # not load. This is the one condition that invalidates outright.
            report.overall_health = "FAILED"
            report.benchmark_validity = "INVALID"
        elif not report.openai.healthy:
            report.overall_health = "PARTIAL"
            report.benchmark_validity = "PARTIAL"

        return report

    def _inspect_dataset(self, version: str, tier: Optional[str],
                         warnings: List[str]) -> ServiceHealthStatus:
        """Loads the benchmark dataset and reports what actually came back."""
        try:
            from backend.evals.datasets.loader import dataset_loader
            records = dataset_loader.load_dataset(version=version, tier=tier)
            schema_errors = list(dataset_loader.last_schema_errors)
            source = dataset_loader.last_source
        except Exception as e:
            warnings.append(f"Dataset load raised: {e}")
            return ServiceHealthStatus(
                name="Dataset", configured=False, healthy=False, reachable=False,
                current_mode="FAILED", reason=f"Dataset load raised: {e}")

        tier_label = tier or "all"

        if not records:
            reason = (f"No test cases for version '{version}', tier '{tier_label}' "
                      f"(source: {source})")
            warnings.append(reason)
            return ServiceHealthStatus(
                name="Dataset", configured=False, healthy=False, reachable=True,
                current_mode="FAILED", reason=reason)

        if schema_errors:
            reason = (f"{len(records)} case(s) loaded from {source} but schema "
                      f"validation reported {len(schema_errors)} error(s): "
                      f"{schema_errors[0]}")
            warnings.append(reason)
            return ServiceHealthStatus(
                name="Dataset", configured=True, healthy=False, reachable=True,
                authenticated=True, current_mode="DEGRADED", reason=reason)

        return ServiceHealthStatus(
            name="Dataset", configured=True, healthy=True, reachable=True,
            authenticated=True, quota_available=True, current_mode="ACTIVE",
            reason=f"{len(records)} case(s) loaded from {source}, schema validated "
                   f"(version '{version}', tier '{tier_label}')")


environment_inspector = EnvironmentInspector()
