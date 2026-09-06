import json
import logging
import os
from datetime import datetime, timezone

from backend.utils.report_paths import REPORTS_DIR

# This was `os.path.join(..., "scratch", "evals")`, so the served application
# appended a runtime log to a tracked directory named `scratch` — and the 21 KB of
# history already in it was committed. `backend/reports/` is the destination
# `report_paths` established for generated artifacts and is gitignored, which is
# what an append-only log wants. The existing `chat_evaluations.jsonl` was moved
# here rather than discarded; it is now untracked, so `git rm --cached
# backend/scratch/evals/chat_evaluations.jsonl` is still owed.
LOGS_DIR = os.path.join(REPORTS_DIR, "evals")
os.makedirs(LOGS_DIR, exist_ok=True)

EVAL_LOG_FILE = os.path.join(LOGS_DIR, "chat_evaluations.jsonl")

logger = logging.getLogger("eval_logger")
logger.setLevel(logging.INFO)

def log_chat_evaluation(
    session_id: str,
    action: str,
    guardrail_status: str,
    tool_invocations: list,
    model_id: str,
    latency_ms: float = 0,
    metadata: dict = None
):
    """
    Logs evaluation metrics for the chat session, focusing on:
    - Tool Calling Accuracy
    - Contextual Grounding Faithfulness
    """
    if metadata is None:
        metadata = {}

    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "session_id": session_id,
        "action": action,
        "model_id": model_id,
        "guardrail_status": guardrail_status,
        "tools_invoked": tool_invocations,
        "latency_ms": latency_ms,
        "metadata": metadata
    }

    try:
        with open(EVAL_LOG_FILE, "a") as f:
            f.write(json.dumps(log_entry) + "\n")
        
        logger.info(f"Evaluation logged [Action: {action}, Guardrail: {guardrail_status}, Tools: {len(tool_invocations)}]")
    except Exception as e:
        logger.error(f"Failed to write eval log: {e}")
