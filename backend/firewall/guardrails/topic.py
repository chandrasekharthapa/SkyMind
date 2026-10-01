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
                # This was "Indian aviation markets, flight pricing analysis, and
                # real-world route metadata forecasting" — narrow enough that
                # ordinary air-travel questions (check-in times, baggage rules,
                # what a layover is) could be judged off-topic and blocked.
                {"role": "system", "content": (
                    "Allowed topic: air travel and aviation. This includes flight "
                    "search, fares and fare trends, airlines, airports, routes, "
                    "booking, check-in, baggage, travel documents and airport "
                    "procedures, aircraft, in-flight experience, delays and "
                    "cancellations, and general aviation knowledge. Greetings and "
                    "thanks are allowed. Anything unrelated to air travel is off-topic."
                )},
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
