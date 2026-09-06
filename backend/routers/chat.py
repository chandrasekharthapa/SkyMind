"""SkyMind Chat Endpoint.

Pipeline: User -> Firewall -> Domain Classifier -> Governance Decision
         -> (if ALLOW) ChatbotService -> Response Validator -> User
         -> (if REDIRECT/LIMIT/REFUSE) Deterministic message -> User

A thin orchestrator router focusing strictly on request validation, firewall protection,
domain classification, and governance redirect rules.
"""

import os
import json
import logging
from typing import List, Dict, Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.services.eval_logger import log_chat_evaluation
from backend.firewall import FirewallConfig, PolicyPlatform, PolicyLoader
from backend.governance.classifier import classify_message
from backend.governance.engine import GovernancePolicyLoader
from backend.governance.models import GovernanceActionEnum
from backend.services.chatbot_service import chatbot_service

router = APIRouter()
logger = logging.getLogger(__name__)

# Enterprise Firewall Configs
firewall_config = FirewallConfig()
# No path argument: `PolicyLoader` resolves `backend/policy.yaml` from its own
# `__file__`. This read `PolicyLoader(file_path="policy.yaml")`, relative to the
# working directory, which from the repository root — the only place this app can be
# launched from — is a file that does not exist. The loader then substituted an
# empty policy, and an empty policy makes `RuleEngine` return `is_safe=True` for
# every request, including the ones the guardrails below flag as UNSAFE.
firewall_policy_loader = PolicyLoader()
policy_platform = PolicyPlatform(config=firewall_config, policy_loader=firewall_policy_loader)

# Domain Governance Policy Loader (hot-reloads from YAML)
governance_loader = GovernancePolicyLoader()
LLM_MODEL_ID = "meta/llama-3.1-70b-instruct"


class ChatMessage(BaseModel):
    role: str = Field(..., pattern="^(user|assistant|system)$")
    content: str

class ChatRequest(BaseModel):
    messages: List[ChatMessage]


@router.post("/chat", tags=["AI Concierge"])
async def chat_endpoint(request: ChatRequest):
    messages = request.messages[-10:]

    # Extract latest query to execute classification and safety checks
    user_messages = [msg for msg in messages if msg.role == "user"]
    latest_query = user_messages[-1].content.strip() if user_messages else ""

    session_id = f"sess_{os.urandom(8).hex()}"

    # ── Stage 1: Firewall ─────────────────────────────────────────
    try:
        context = await policy_platform.evaluate_messages(
            [{"role": "user", "content": latest_query}]
        )
        firewall_decision = context.decision

        if not firewall_decision.is_safe:
            violation = firewall_decision.violations[0] if firewall_decision.violations else "unknown"
            log_chat_evaluation(session_id, "INTERCEPTED", violation, [], LLM_MODEL_ID)

            if violation == "jailbreak-detect":
                msg = "I can't process that request. How can I help you with flights or travel?"
            elif violation == "topic-control":
                msg = "I specialize in aviation intelligence — flights, airlines, airports, and airfare trends. How can I help?"
            else:
                msg = "I wasn't able to process that. Feel free to ask me about flights or travel planning."

            # Debug logs
            logger.info(json.dumps({
                "query": latest_query,
                "domain": "unknown",
                "confidence": 0.0,
                "governance_action": "BLOCK",
                "acknowledgement": msg,
                "llm_called": False
            }))

            return StreamingResponse(
                iter([msg.encode("utf-8")]),
                media_type="text/plain",
            )
    except Exception as e:
        logger.warning(f"Firewall check failed (fail-open): {e}")

    # ── Stage 2: Domain Governance ────────────────────────────────
    try:
        classification = classify_message(latest_query)
        gov_decision = governance_loader.get_action(classification.domain)

        # Redirect if governance classification is anything other than ALLOW
        if gov_decision.action != GovernanceActionEnum.ALLOW:
            ack = gov_decision.acknowledgement or (
                "I'm designed to help with aviation and travel. "
                "Ask me about flights, airlines, or airfare trends."
            )
            log_chat_evaluation(
                session_id, "GOVERNANCE_REDIRECT",
                f"domain:{classification.domain.value}",
                [], LLM_MODEL_ID,
            )

            # Debug logs
            logger.info(json.dumps({
                "query": latest_query,
                "domain": classification.domain.value,
                "confidence": classification.confidence,
                "governance_action": gov_decision.action.value,
                "acknowledgement": ack,
                "llm_called": False
            }))

            return StreamingResponse(
                iter([ack.encode("utf-8")]),
                media_type="text/plain",
            )
    except Exception as e:
        logger.warning(f"Governance classification failed (fail-open): {e}")

    # ── Stage 3: LLM Generation (Aviation-only Allowed Path) ──────
    logger.info(json.dumps({
        "query": latest_query,
        "domain": classification.domain.value if 'classification' in locals() else "aviation",
        "confidence": classification.confidence if 'classification' in locals() else 1.0,
        "governance_action": gov_decision.action.value if 'gov_decision' in locals() else "ALLOW",
        "acknowledgement": None,
        "llm_called": True
    }))

    # Delegate streaming entirely to chatbot service
    messages_payload = [{"role": msg.role, "content": msg.content} for msg in messages]
    
    return StreamingResponse(
        chatbot_service.chat_stream(session_id, messages_payload),
        media_type="text/plain"
    )
