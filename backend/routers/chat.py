"""SkyMind Chat Endpoint.

Pipeline: User -> Rate limit -> Firewall -> Domain Classifier -> Governance Decision
         -> (if ALLOW) ChatbotService -> Response Validator -> User
         -> (if REDIRECT/LIMIT/REFUSE) Deterministic message -> User

A thin orchestrator router focusing strictly on request validation, firewall protection,
domain classification, and governance redirect rules.

Every response carries `X-SkyMind-Message-Type`: "notice" for a fixed message from
this router (blocked, redirected, rate-limited, too long) and "answer" for the
assistant's reply. The widget used to tell them apart by checking whether a chunk
contained the word "SkyMind", which also matched any real answer mentioning the
product and cut it off mid-sentence.
"""

import hmac
import os
import json
import time
import logging
from collections import deque
from typing import Any, Deque, Dict, List, Literal, Optional

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator

from backend.services.eval_logger import log_chat_evaluation
from backend.firewall import FirewallConfig, PolicyPlatform, PolicyLoader
from backend.firewall.models import GuardrailStatus
from backend.governance.classifier import classify_message
from backend.governance.engine import GovernancePolicyLoader
from backend.governance.models import DomainEnum, GovernanceActionEnum
from backend.services.chatbot_service import chatbot_service, LLM_MODEL_ID

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

HISTORY_WINDOW = 10
MAX_USER_MESSAGE_CHARS = int(os.getenv("CHAT_MAX_MESSAGE_CHARS", "2000"))

FALLBACK_BLOCK_MESSAGE = "I wasn't able to process that. Feel free to ask me about flights or travel planning."
UNAVAILABLE_MESSAGE = "The assistant is temporarily unavailable. Please try again in a moment."


# ── Rate limiting ─────────────────────────────────────────────────────
# Every allowed turn costs hosted-model calls and can start a live scrape, and the
# endpoint is unauthenticated. A per-client sliding window, in process: the
# backend runs as a single instance, so nothing needs to be shared.

RATE_LIMIT_PER_MINUTE = int(os.getenv("CHAT_RATE_LIMIT_PER_MINUTE", "10"))
RATE_LIMIT_PER_HOUR = int(os.getenv("CHAT_RATE_LIMIT_PER_HOUR", "60"))
_MAX_TRACKED_CLIENTS = 10_000


class _SlidingWindowLimiter:
    def __init__(self) -> None:
        self._hits: Dict[str, Deque[float]] = {}

    def allow(self, key: str, now: Optional[float] = None) -> bool:
        now = time.monotonic() if now is None else now
        hits = self._hits.setdefault(key, deque())
        while hits and now - hits[0] > 3600:
            hits.popleft()
        last_minute = sum(1 for t in hits if now - t <= 60)
        if last_minute >= RATE_LIMIT_PER_MINUTE or len(hits) >= RATE_LIMIT_PER_HOUR:
            return False
        hits.append(now)
        if len(self._hits) > _MAX_TRACKED_CLIENTS:
            for stale in [k for k, v in self._hits.items() if not v or now - v[-1] > 3600]:
                self._hits.pop(stale, None)
        return True


rate_limiter = _SlidingWindowLimiter()


def _is_eval_client(http_request: Request) -> bool:
    """The evaluation runner, identified by a shared secret (CHAT_EVAL_KEY), skips
    the rate limit — the golden dataset is 152 conversations and the per-client
    limit is 60 an hour. Unset by default, so nothing is exempt."""
    expected = os.getenv("CHAT_EVAL_KEY", "").strip()
    given = http_request.headers.get("X-SkyMind-Eval-Key", "").strip()
    return bool(expected) and bool(given) and hmac.compare_digest(expected, given)


# ── Request schema ────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    # "system" used to be accepted from the client. The service dropped it before
    # the model saw it, but it was still a client-controlled role on an
    # unauthenticated endpoint with nothing to gain from it.
    role: Literal["user", "assistant"]
    # Generous enough for a long table the assistant wrote earlier, which the
    # widget sends back as history; the latest user message has a tighter limit
    # checked in the handler so it can be answered with a message, not a 422.
    content: str = Field("", max_length=20_000)


class RouteContext(BaseModel):
    """The search page the widget is open on. Optional, and every field may be blank."""
    origin: Optional[str] = None
    destination: Optional[str] = None
    departure_date: Optional[str] = None
    cabin_class: Optional[str] = None

    @field_validator("origin", "destination", mode="before")
    @classmethod
    def _iata(cls, v: Any) -> Optional[str]:
        v = (str(v).strip().upper() if v is not None else "")
        return v if len(v) == 3 and v.isalpha() else None

    @field_validator("departure_date", mode="before")
    @classmethod
    def _date(cls, v: Any) -> Optional[str]:
        import re
        v = str(v).strip() if v is not None else ""
        return v if re.fullmatch(r"\d{4}-\d{2}-\d{2}", v) else None

    @field_validator("cabin_class", mode="before")
    @classmethod
    def _cabin(cls, v: Any) -> Optional[str]:
        v = str(v).strip().upper() if v is not None else ""
        return v if v in {"ECONOMY", "PREMIUM_ECONOMY", "BUSINESS", "FIRST"} else None


class ChatRequest(BaseModel):
    messages: List[ChatMessage] = Field(..., min_length=1, max_length=200)
    # The widget has always sent these; both were silently discarded, so every
    # turn started a fresh conversation context and "what about tomorrow?" had
    # no route to apply to.
    session_id: Optional[str] = Field(None, pattern=r"^[A-Za-z0-9_-]{6,64}$")
    route_context: Optional[RouteContext] = None


# ── Helpers ───────────────────────────────────────────────────────────

def _notice(text: str, status_code: int = 200) -> PlainTextResponse:
    return PlainTextResponse(
        text, status_code=status_code, headers={"X-SkyMind-Message-Type": "notice"}
    )


def _log_decision(query: str, **fields: Any) -> None:
    # Truncated: these lines go to the hosting provider's log store, and a full
    # message can carry names, phone numbers or booking references.
    logger.info(json.dumps({"query": query[:200], **fields}))


def _is_follow_up(
    earlier_user_messages: List[str],
    route_context: Optional[RouteContext],
    session_id: Optional[str],
) -> bool:
    """Whether an otherwise unclassifiable message continues a travel conversation.

    The classifier sees one message. "What about tomorrow?", "and the cheapest?"
    or "yes, book the 6 am one" contain no travel words, were classified UNKNOWN,
    and were answered with "I'm designed to assist with aviation and travel" in
    the middle of a flight search.
    """
    if route_context and (route_context.origin or route_context.destination):
        return True
    if session_id:
        ctx = chatbot_service.sessions.get(session_id)
        if ctx and (ctx.origin or ctx.destination):
            return True
    return any(
        classify_message(m).domain == DomainEnum.AVIATION for m in earlier_user_messages
    )


# ── Endpoint ──────────────────────────────────────────────────────────

@router.post("/chat", tags=["AI Concierge"])
async def chat_endpoint(request: ChatRequest, http_request: Request):
    client_key = http_request.client.host if http_request.client else "unknown"
    if not _is_eval_client(http_request) and not rate_limiter.allow(client_key):
        return _notice(
            "You're sending messages faster than I can answer. Please wait a minute and try again.",
            status_code=429,
        )

    messages = [m for m in request.messages[-HISTORY_WINDOW:] if m.content.strip()]
    user_messages = [m.content.strip() for m in messages if m.role == "user"]
    if not user_messages:
        return _notice("Ask me about flights, fares or airports to get started.")
    latest_query = user_messages[-1]
    if len(latest_query) > MAX_USER_MESSAGE_CHARS:
        return _notice(
            f"That message is too long — please keep it under {MAX_USER_MESSAGE_CHARS} characters."
        )

    session_id = request.session_id or f"sess_{os.urandom(8).hex()}"

    # ── Stage 1: Firewall ─────────────────────────────────────────
    # Every user message in the window, not just the latest. The history is
    # client-supplied, so screening only the newest message let earlier ones —
    # which go to the model verbatim — through unchecked. The pipeline's
    # normalisation stage joins user messages into one prompt.
    try:
        context = await policy_platform.evaluate_messages(
            [{"role": "user", "content": m} for m in user_messages]
        )
        firewall_decision = context.decision
    except Exception as e:
        # Fail closed. This is the pipeline itself breaking (guardrail errors are
        # caught inside it and reported below), and the old fail-open path sent
        # the request to the model unscreened.
        logger.error(f"Firewall pipeline failed; refusing request: {type(e).__name__}: {e}")
        log_chat_evaluation(session_id, "FIREWALL_ERROR", type(e).__name__, [], LLM_MODEL_ID)
        return _notice(UNAVAILABLE_MESSAGE, status_code=503)

    errored = [
        d.name for d in (firewall_decision.details or [])
        if getattr(d, "status", None) == GuardrailStatus.ERROR
    ]
    if errored:
        # `FirewallConfig.fail_open` existed but nothing read it: a guardrail that
        # timed out or errored was treated as a pass, silently. It is now logged
        # every time and honoured — FIREWALL_FAIL_OPEN=false makes an unavailable
        # guardrail block the request instead.
        logger.warning(f"Guardrail(s) unavailable for this request: {errored}")
        if not firewall_config.fail_open:
            log_chat_evaluation(session_id, "GUARDRAIL_UNAVAILABLE", ",".join(errored), [], LLM_MODEL_ID)
            return _notice(UNAVAILABLE_MESSAGE, status_code=503)

    if not firewall_decision.is_safe:
        violation = firewall_decision.violations[0] if firewall_decision.violations else "unknown"
        log_chat_evaluation(session_id, "INTERCEPTED", violation, [], LLM_MODEL_ID)
        if violation == "jailbreak-detect":
            msg = "I can't process that request. How can I help you with flights or travel?"
        elif violation == "topic-control":
            msg = "I specialize in aviation intelligence — flights, airlines, airports, and airfare trends. How can I help?"
        else:
            msg = FALLBACK_BLOCK_MESSAGE
        _log_decision(latest_query, governance_action="BLOCK", violation=violation, llm_called=False)
        return _notice(msg)

    # ── Stage 2: Domain Governance ────────────────────────────────
    try:
        classification = classify_message(latest_query)
        domain = classification.domain
        if domain == DomainEnum.UNKNOWN and _is_follow_up(
            user_messages[:-1], request.route_context, request.session_id
        ):
            domain = DomainEnum.AVIATION
        gov_decision = governance_loader.get_action(domain)
    except Exception as e:
        logger.error(f"Governance classification failed; refusing request: {type(e).__name__}: {e}")
        return _notice(UNAVAILABLE_MESSAGE, status_code=503)

    if gov_decision.action != GovernanceActionEnum.ALLOW:
        ack = gov_decision.acknowledgement or (
            "I'm designed to help with aviation and travel. "
            "Ask me about flights, airlines, or airfare trends."
        )
        log_chat_evaluation(session_id, "GOVERNANCE_REDIRECT", f"domain:{domain.value}", [], LLM_MODEL_ID)
        _log_decision(
            latest_query, domain=domain.value, confidence=classification.confidence,
            governance_action=gov_decision.action.value, llm_called=False,
        )
        return _notice(ack)

    # ── Stage 3: LLM Generation (Aviation-only Allowed Path) ──────
    _log_decision(
        latest_query, domain=domain.value, confidence=classification.confidence,
        governance_action="ALLOW", llm_called=True,
    )
    messages_payload = [{"role": m.role, "content": m.content} for m in messages]
    route = request.route_context.model_dump() if request.route_context else None

    return StreamingResponse(
        chatbot_service.chat_stream(session_id, messages_payload, route),
        media_type="text/plain",
        headers={"X-SkyMind-Message-Type": "answer"},
    )
