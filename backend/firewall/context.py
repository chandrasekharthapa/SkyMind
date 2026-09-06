from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from backend.firewall.models import GuardrailResult, FirewallDecision

class RequestContext(BaseModel):
    """
    Core state object that flows through the entire pipeline.
    Read and written by every stage.
    """
    request_id: str = Field(..., description="Unique ID for this request")
    session_id: str = Field(default="", description="Optional session ID")
    user_id: str = Field(default="", description="Optional user ID")
    
    # Input
    messages: List[Dict[str, str]] = Field(default_factory=list, description="Original messages")
    normalized_prompt: str = Field(default="", description="Prompt normalized for evaluation")
    
    # Pipeline State
    guardrail_results: List[GuardrailResult] = Field(default_factory=list, description="Results from guardrails")
    policy_trace: List[Dict[str, Any]] = Field(default_factory=list, description="Audit trace of rules evaluated")
    risk_score: float = Field(default=0.0, description="Cumulative risk score")
    
    # Tool/LLM State
    tool_calls: List[Dict[str, Any]] = Field(default_factory=list, description="Requested tool calls")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary metadata from plugins")
    timings: Dict[str, float] = Field(default_factory=dict, description="Execution times per stage")
    
    # Final Output
    decision: Optional[FirewallDecision] = Field(default=None, description="The final policy decision")
