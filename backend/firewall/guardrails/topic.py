from backend.firewall.guardrails.base import BaseGuardrail
from backend.firewall.models import GuardrailResult
from backend.firewall.client import NVIDIAClientProvider
from backend.firewall.parser import NeMoResponseParser

class TopicGuardrail(BaseGuardrail):
    name = "topic-control"
    
    async def _execute(self, prompt: str) -> GuardrailResult:
        client = NVIDIAClientProvider.get_client(self.config)
        
        response = await client.chat.completions.create(
            model="nvidia/llama-3.1-nemoguard-8b-topic-control",
            messages=[
                {"role": "system", "content": "Allowed topic: Indian aviation markets, flight pricing analysis, and real-world route metadata forecasting."},
                {"role": "user", "content": prompt}
            ]
        )
        
        raw_text = response.choices[0].message.content or ""
        status = NeMoResponseParser.parse(raw_text)
        
        return GuardrailResult(
            name=self.name,
            status=status,
            raw_response=raw_text
        )
