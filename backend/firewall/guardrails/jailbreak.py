import logging

from backend.firewall.guardrails.base import BaseGuardrail
from backend.firewall.models import GuardrailResult
from backend.firewall.client import GroqClientProvider, NVIDIAClientProvider
from backend.firewall.parser import NeMoResponseParser, PromptGuardParser

logger = logging.getLogger(__name__)


class JailbreakGuardrail(BaseGuardrail):
    """Prompt-injection and jailbreak check.

    NVIDIA removed nemoguard-jailbreak-detect from its hosted API (every call now
    answers 404), so with a Groq key this uses Meta's Llama Prompt Guard 2 on Groq
    instead. Without one it still tries the NVIDIA model, and the circuit breaker
    stops that from costing time on every request.
    """
    name = "jailbreak-detect"

    async def _execute(self, prompt: str) -> GuardrailResult:
        if self.config.groq_api_key:
            client = GroqClientProvider.get_client(self.config)
            response = await client.chat.completions.create(
                model=self.config.jailbreak_model_groq,
                messages=[{"role": "user", "content": prompt}],
            )
            raw_text = response.choices[0].message.content or ""
            status = PromptGuardParser.parse(raw_text, self.config.jailbreak_threshold)
            if status.value == "UNKNOWN":
                logger.warning(f"Prompt Guard returned an unrecognised verdict: {raw_text[:200]!r}")
        else:
            client = NVIDIAClientProvider.get_client(self.config)
            response = await client.chat.completions.create(
                model=self.config.jailbreak_model_nvidia,
                messages=[{"role": "user", "content": prompt}],
            )
            raw_text = response.choices[0].message.content or ""
            status = NeMoResponseParser.parse(raw_text)

        return GuardrailResult(
            name=self.name,
            status=status,
            raw_response=raw_text
        )
