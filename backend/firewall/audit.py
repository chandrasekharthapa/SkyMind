import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict

from backend.firewall.context import RequestContext

# Use a separate logger for audits to write to a dedicated file in a real system
audit_logger = logging.getLogger("firewall.audit")
audit_logger.setLevel(logging.INFO)

# In a true enterprise setup, this goes to an ELK stack, Splunk, or immutable S3 bucket
# Here we ensure it's written in structured JSON format
if not audit_logger.handlers:
    handler = logging.FileHandler("firewall_audit.log")
    formatter = logging.Formatter('%(message)s')
    handler.setFormatter(formatter)
    audit_logger.addHandler(handler)

class AuditService:
    """Emits immutable audit records for every firewall decision."""
    
    @staticmethod
    def emit(context: RequestContext):
        """Serializes the context trace into a JSON audit record."""
        
        # Build the immutable record
        record: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_id": context.request_id,
            "session_id": context.session_id,
            "user_id": context.user_id,
            "risk_score": context.risk_score,
            "decision": {
                "is_safe": context.decision.is_safe if context.decision else False,
                "violations": context.decision.violations if context.decision else []
            },
            "guardrail_results": [
                {
                    "name": res.name,
                    "status": res.status.value,
                    "latency_ms": res.latency_ms
                } for res in context.guardrail_results
            ],
            "policy_trace": context.policy_trace,
            "timings": context.timings
        }
        
        # Emit to the structured audit log
        audit_logger.info(json.dumps(record))
