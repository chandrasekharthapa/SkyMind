from typing import Optional
from .models import GuardrailStatus

class NeMoResponseParser:
    """Deterministic parser for NVIDIA NeMo Guardrails output."""
    
    @staticmethod
    def parse(response_text: str) -> GuardrailStatus:
        """
        Parses the raw text response from NeMo guardrails.
        Replaces brittle string matching with explicit mapping.
        """
        # NeMo models typically output variations of 'safe', 'no', or 'violates'
        text = response_text.strip().lower()
        
        # Exact structured matches if the model supports it
        if text in ["safe", "no"]:
            return GuardrailStatus.SAFE
        if text in ["unsafe", "violate", "violates", "yes"]:
            return GuardrailStatus.UNSAFE
            
        # Fallback keyword matching with strict boundaries
        if "safe" in text and "violate" not in text and "unsafe" not in text:
            return GuardrailStatus.SAFE
        if "violate" in text or "unsafe" in text:
            return GuardrailStatus.UNSAFE
            
        # If the output is completely unexpected (e.g., hallucination), mark as UNKNOWN
        return GuardrailStatus.UNKNOWN
