from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field

class RuleAction(str, Enum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    REVIEW = "REVIEW"

class RuleCondition(BaseModel):
    """Recursive condition model supporting logical operators and base matches."""

    # `and`, `or` and `not` are Python keywords, so the fields are named
    # `*_cond` and aliased. `populate_by_name` lets both spellings work.
    #
    # This was a Pydantic V1 `class Config` block carrying
    # `allow_population_by_field_name`, which V2 renamed to `populate_by_name` —
    # so under the pinned `pydantic>=2.7.0` the setting was ignored and the three
    # composite fields could only be populated by their aliases. It is also the
    # UserWarning the app prints on every boot. The dropped `json_encoders` entry
    # was keyed by the string "RuleCondition" rather than by the type, so it never
    # matched anything in V1 either, and V2 removed the hook.
    model_config = ConfigDict(populate_by_name=True)

    # Base matches
    guardrail: Optional[str] = None
    verdict: Optional[str] = None
    risk_gt: Optional[float] = None
    confidence_gt: Optional[float] = None
    # Logical composites
    and_cond: Optional[List["RuleCondition"]] = Field(default=None, alias="and")
    or_cond: Optional[List["RuleCondition"]] = Field(default=None, alias="or")
    not_cond: Optional["RuleCondition"] = Field(default=None, alias="not")

# Resolve forward references for the recursive model.
RuleCondition.model_rebuild()

class Rule(BaseModel):
    id: str
    priority: int = 0
    enabled: bool = True
    match: RuleCondition
    action: RuleAction

class PolicyConfig(BaseModel):
    version: str = "1.0"
    default_action: RuleAction = RuleAction.ALLOW
    rules: List[Rule] = Field(default_factory=list)
