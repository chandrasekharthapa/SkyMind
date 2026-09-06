from backend.firewall.guardrails.base import BaseGuardrail
from backend.firewall.models import GuardrailResult
from backend.firewall.client import NVIDIAClientProvider
from backend.firewall.parser import NeMoResponseParser

class JailbreakGuardrail(BaseGuardrail):
    name = "jailbreak-detect"
    
    async def _execute(self, prompt: str) -> GuardrailResult:
        client = NVIDIAClientProvider.get_client(self.config)
        
        response = await client.chat.completions.create(
            model="nvidia/nemoguard-jailbreak-detect",
            messages=[{"role": "user", "content": prompt}]
        )
        
        raw_text = response.choices[0].message.content or ""
        status = NeMoResponseParser.parse(raw_text)
        
        return GuardrailResult(
            name=self.name,
            status=status,
            raw_response=raw_text
        )
