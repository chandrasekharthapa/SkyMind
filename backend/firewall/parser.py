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


class PromptGuardParser:
    """Reads Llama Prompt Guard 2's verdict.

    The model is a classifier, not a chat model. Groq returns its result as the
    message text; depending on the serving stack that is the attack probability
    ("0.9993") or a label ("MALICIOUS" / "BENIGN", or "LABEL_1" / "LABEL_0").
    All are accepted. Anything else is UNKNOWN, never SAFE, so a format change
    shows up in the logs instead of silently passing every prompt.
    """

    _UNSAFE_LABELS = {"malicious", "jailbreak", "injection", "label_1", "unsafe"}
    _SAFE_LABELS = {"benign", "label_0", "safe"}

    @classmethod
    def parse(cls, response_text: str, threshold: float = 0.8) -> GuardrailStatus:
        text = (response_text or "").strip().lower()
        try:
            score = float(text)
        except ValueError:
            score = None
        if score is not None:
            if not 0.0 <= score <= 1.0:
                return GuardrailStatus.UNKNOWN
            return GuardrailStatus.UNSAFE if score >= threshold else GuardrailStatus.SAFE
        word = text.strip(" .\"'")
        if word in cls._UNSAFE_LABELS:
            return GuardrailStatus.UNSAFE
        if word in cls._SAFE_LABELS:
            return GuardrailStatus.SAFE
        return GuardrailStatus.UNKNOWN
