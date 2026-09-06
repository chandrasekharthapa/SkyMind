from enum import Enum
from dataclasses import dataclass
from typing import Optional, Dict, Any

class DecisionActionEnum(str, Enum):
    ALLOW = "ALLOW"
    REDIRECT = "REDIRECT"
    REFUSE = "REFUSE"
    LIMIT = "LIMIT"
    SAFETY_OVERRIDE = "SAFETY_OVERRIDE"

@dataclass
class DecisionResult:
    action: DecisionActionEnum
    continue_pipeline: bool
    fallback_message: Optional[str] = None
    retry_allowed: bool = False
    retry_limit: int = 0
    reason_code: Optional[str] = None
    confidence: Optional[float] = None
    metadata: Optional[Dict[str, Any]] = None
