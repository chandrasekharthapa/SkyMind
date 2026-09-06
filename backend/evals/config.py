"""Central Evaluation Configuration for SkyMind Copilot Evaluation Platform.

Defines EvaluationConfig model loaded from environment variables and CLI parameters.
No evaluator hardcodes configuration; all settings read from EvaluationConfig.
"""

import os
import hashlib
from typing import Optional
from pydantic import BaseModel, Field

#: `backend/evals/`, resolved from this file rather than from the process's working
#: directory. The default was the relative string "backend/evals/results", which has
#: two separate consequences. Run from the repository root it wrote *into the tracked
#: tree* — `git ls-files backend/evals/results` returns 32 committed report.md /
#: summary.json files from a 2026-07-24 run, and every eval run since has been adding
#: more, so executing the suite modifies version-controlled content. Run from
#: `backend/` it silently created `backend/backend/evals/results` instead, which is the
#: same failure the `backend/backend/` tripwire in `.gitignore` records for two other
#: services. Anchoring fixes the second; gitignoring the directory fixes the first.
_EVALS_DIR = os.path.dirname(os.path.abspath(__file__))

#: Default destination for evaluation run artifacts. Gitignored.
RESULTS_DIR = os.path.join(_EVALS_DIR, "results")


def default_output_directory() -> str:
    """Absolute results directory, overridable by `EVAL_OUTPUT_DIR`.

    The override exists for CI, which wants artifacts under its own workspace path,
    and for tests, which must not write beside the shipped code at all. It is read at
    construction time rather than import time so a test can set it with monkeypatch.
    """
    return os.getenv("EVAL_OUTPUT_DIR", "").strip() or RESULTS_DIR


class EvaluationConfig(BaseModel):
    dataset_version: str = Field(default="2.0.0", description="Version of evaluation dataset e.g. 2.0.0")
    evaluation_version: str = Field(default="1.0.0", description="Version of evaluation runner software")
    planner_runner: str = Field(default="hybrid", description="Target planner runner: hybrid, openai, or rule_based")
    judge_runner: str = Field(default="openai", description="Target judge runner: openai or disabled")
    llm_evaluator_provider: str = Field(default_factory=lambda: os.getenv("LLM_EVALUATOR_PROVIDER", "openai"))
    llm_evaluator_model: str = Field(default_factory=lambda: os.getenv("LLM_EVALUATOR_MODEL", "gpt-4o-mini"))
    parallelism: int = Field(default=5, ge=1, le=20, description="Max concurrent evaluation workers")
    seed: int = Field(default=42, description="Random seed for reproducible sampling")
    temperature: float = Field(default=0.0, ge=0.0, le=1.0)
    langsmith_project: str = Field(default_factory=lambda: os.getenv("LANGSMITH_PROJECT", "skymind-concierge"))
    enable_llm_metrics: bool = Field(default=True, description="Enable offline LLM-as-a-judge metrics")
    enable_deterministic_metrics: bool = Field(default=True, description="Enable non-LLM deterministic metrics")
    tier: str = Field(default="smoke", description="Evaluation tier: smoke, full, nightly, or regression")
    output_directory: str = Field(default_factory=default_output_directory,
                                 description="Local artifact output path (absolute)")
    git_sha: str = Field(default_factory=lambda: os.getenv("GIT_SHA", "local_development"))
    git_branch: str = Field(default_factory=lambda: os.getenv("GIT_BRANCH", "main"))

    @property
    def config_hash(self) -> str:
        """Returns deterministic MD5 hash of current configuration state."""
        raw = f"{self.dataset_version}:{self.planner_runner}:{self.llm_evaluator_model}:{self.tier}:{self.seed}"
        return hashlib.md5(raw.encode("utf-8")).hexdigest()[:10]


default_config = EvaluationConfig()
