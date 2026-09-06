from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class GuardrailStatus(str, Enum):
    SAFE = "SAFE"
    UNSAFE = "UNSAFE"
    ERROR = "ERROR"
    UNKNOWN = "UNKNOWN"

class GuardrailResult(BaseModel):
    name: str = Field(..., description="The name of the guardrail (e.g., 'jailbreak-detect')")
    status: GuardrailStatus = Field(..., description="The evaluated status")
    raw_response: str = Field(..., description="The raw textual response from the underlying model")
    latency_ms: float = Field(default=0.0, description="Execution time in milliseconds")
    error: Optional[str] = Field(default=None, description="Error message if status is ERROR")

class FirewallDecision(BaseModel):
    is_safe: bool = Field(..., description="True if the prompt passed all policy requirements")
    violations: List[str] = Field(default_factory=list, description="List of guardrail names that failed")
    details: List[GuardrailResult] = Field(default_factory=list, description="Detailed results from all executed guardrails")
    execution_time_ms: float = Field(default=0.0, description="Total firewall execution time in milliseconds")
