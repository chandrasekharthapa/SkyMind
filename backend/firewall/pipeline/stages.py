import time
import asyncio
from abc import ABC, abstractmethod
from typing import List

from backend.firewall.context import RequestContext
from backend.firewall.config import FirewallConfig
from backend.firewall.discovery import GuardrailDiscovery
from backend.firewall.rules.engine import RuleEngine
from backend.firewall.risk import RiskEngine
from backend.firewall.audit import AuditService
from backend.firewall.observability import get_tracer

tracer = get_tracer()

class BaseStage(ABC):
    """Abstract base class for all pipeline stages."""
    
    @abstractmethod
    async def execute(self, context: RequestContext):
        pass

class NormalizationStage(BaseStage):
    async def execute(self, context: RequestContext):
        with tracer.start_as_current_span("NormalizationStage"):
            start = time.time()
            # In a real app, this might strip PII, trim whitespace, etc.
            prompt = ""
            for msg in context.messages:
                if msg.get("role") == "user":
                    prompt += msg.get("content", "") + " "
            
            context.normalized_prompt = prompt.strip()
            context.timings["normalization"] = (time.time() - start) * 1000

class GuardrailStage(BaseStage):
    def __init__(self, config: FirewallConfig):
        self.config = config
        self.guardrails = GuardrailDiscovery.discover(config)
        self.semaphore = asyncio.Semaphore(config.concurrency_limit)
        
    async def execute(self, context: RequestContext):
        with tracer.start_as_current_span("GuardrailStage"):
            start = time.time()
            
            async def bounded_execute(guardrail):
                async with self.semaphore:
                    # In a real app, circuit breaker would wrap this
                    return await guardrail.evaluate(context.normalized_prompt)
                    
            tasks = [bounded_execute(g) for g in self.guardrails]
            results = await asyncio.gather(*tasks)
            
            context.guardrail_results.extend(results)
            context.timings["guardrails"] = (time.time() - start) * 1000

class RiskStage(BaseStage):
    def __init__(self):
        self.risk_engine = RiskEngine()
        
    async def execute(self, context: RequestContext):
        with tracer.start_as_current_span("RiskStage"):
            start = time.time()
            context.risk_score = self.risk_engine.calculate(context)
            context.timings["risk"] = (time.time() - start) * 1000

class PolicyStage(BaseStage):
    def __init__(self, policy_loader):
        self.policy_loader = policy_loader
        
    async def execute(self, context: RequestContext):
        with tracer.start_as_current_span("PolicyStage"):
            start = time.time()
            policy = self.policy_loader.get_policy()
            engine = RuleEngine(policy)
            context.decision = engine.evaluate(context)
            context.timings["policy"] = (time.time() - start) * 1000

class AuditStage(BaseStage):
    async def execute(self, context: RequestContext):
        with tracer.start_as_current_span("AuditStage"):
            start = time.time()
            AuditService.emit(context)
            context.timings["audit"] = (time.time() - start) * 1000
