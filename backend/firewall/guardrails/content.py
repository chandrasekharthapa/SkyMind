from backend.firewall.guardrails.base import BaseGuardrail
from backend.firewall.models import GuardrailResult
from backend.firewall.client import NVIDIAClientProvider
from backend.firewall.parser import NeMoResponseParser

class ContentSafetyGuardrail(BaseGuardrail):
    name = "content-safety"
    
    async def _execute(self, prompt: str) -> GuardrailResult:
        client = NVIDIAClientProvider.get_client(self.config)
        
        response = await client.chat.completions.create(
            model=self.config.content_model,
            messages=[{"role": "user", "content": prompt}]
        )
        
        raw_text = response.choices[0].message.content or ""
        status = NeMoResponseParser.parse(raw_text)
        
        return GuardrailResult(
            name=self.name,
            status=status,
            raw_response=raw_text
        )
