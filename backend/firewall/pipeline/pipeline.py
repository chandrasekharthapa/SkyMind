import uuid
import time
from typing import List

from backend.firewall.context import RequestContext
from backend.firewall.pipeline.stages import (
    BaseStage, 
    NormalizationStage, 
    GuardrailStage, 
    RiskStage, 
    PolicyStage, 
    AuditStage
)
from backend.firewall.observability import get_tracer

tracer = get_tracer()

class Pipeline:
    """Executes a series of stages sequentially against a RequestContext."""
    
    def __init__(self, stages: List[BaseStage]):
        self.stages = stages
        
    async def execute(self, context: RequestContext) -> RequestContext:
        with tracer.start_as_current_span("Pipeline.execute") as span:
            span.set_attribute("request_id", context.request_id)
            
            start_time = time.time()
            for stage in self.stages:
                await stage.execute(context)
                
                # Fast fail if a decision has been reached and it's a BLOCK
                # (Optimization: We don't need to run tools if the policy says BLOCK)
                if context.decision and not context.decision.is_safe:
                    # Ensure audit still runs if we abort early
                    if not isinstance(stage, AuditStage):
                        await AuditStage().execute(context)
                    break
                    
            context.timings["total_pipeline"] = (time.time() - start_time) * 1000
            return context

class PolicyPlatform:
    """Enterprise AI Gateway entry point."""
    
    def __init__(self, config, policy_loader):
        self.config = config
        self.policy_loader = policy_loader
        
        # Build the standard pipeline
        self.pipeline = Pipeline([
            NormalizationStage(),
            GuardrailStage(config),
            RiskStage(),
            PolicyStage(policy_loader),
            AuditStage()
        ])
        
    async def evaluate_messages(self, messages: list) -> RequestContext:
        """Helper to create a context and run the pipeline."""
        context = RequestContext(
            request_id=str(uuid.uuid4()),
            messages=messages
        )
        return await self.pipeline.execute(context)
