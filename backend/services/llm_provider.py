"""LLM Provider Abstraction Layer.

Provides a unified, provider-agnostic interface for streaming generation
and structured Pydantic schema generation across NVIDIA, OpenAI, Anthropic, Google, and Local LLM backends.
"""

import os
import json
import logging
from abc import ABC, abstractmethod
from typing import List, Dict, Any, AsyncGenerator, Optional, Type
from pydantic import BaseModel
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


class LLMProvider(ABC):
    """Abstract Base Class for all LLM Provider Adapters."""

    @abstractmethod
    async def generate_stream(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        **options: Any
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Streams completion chunks and tool calls from target provider."""
        pass

    @abstractmethod
    async def generate_structured(
        self,
        messages: List[Dict[str, Any]],
        response_schema: Type[BaseModel],
        **options: Any
    ) -> BaseModel:
        """Generates a structured Pydantic model response."""
        pass


class NVIDIAAdapter(LLMProvider):
    """NVIDIA Llama infrastructure adapter."""

    def __init__(self, client: Optional[AsyncOpenAI] = None):
        self.base_url = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
        self.api_key = os.getenv("NVIDIA_API_KEY", "").strip()
        self.model_id = os.getenv("NVIDIA_MODEL_ID", "meta/llama-3.1-70b-instruct")
        self.client = client

    def _get_client(self) -> AsyncOpenAI:
        if self.client is None:
            if not self.api_key:
                raise RuntimeError("NVIDIA_API_KEY is not configured.")
            self.client = AsyncOpenAI(base_url=self.base_url, api_key=self.api_key)
        return self.client

    async def generate_stream(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        **options: Any
    ) -> AsyncGenerator[Dict[str, Any], None]:
        kwargs = {"model": self.model_id, "messages": messages, "stream": True}
        if tools:
            kwargs["tools"] = tools

        response = await self._get_client().chat.completions.create(**kwargs)
        async for chunk in response:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            payload = {}
            if delta.content:
                payload["content"] = delta.content
            if delta.tool_calls:
                payload["tool_calls"] = delta.tool_calls
            if payload:
                yield payload

    async def generate_structured(
        self,
        messages: List[Dict[str, Any]],
        response_schema: Type[BaseModel],
        **options: Any
    ) -> BaseModel:
        response = await self._get_client().chat.completions.create(
            model=self.model_id,
            messages=messages,
            response_format={"type": "json_object"},
            stream=False
        )
        content = response.choices[0].message.content or "{}"
        return response_schema.model_validate_json(content)


class OpenAIAdapter(LLMProvider):
    """Standard OpenAI provider adapter (for example, gpt-4o-mini)."""

    def __init__(self, client: Optional[AsyncOpenAI] = None):
        self.api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.model_id = os.getenv("OPENAI_MODEL_ID", "gpt-4o-mini")
        self.client = client

    def _get_client(self) -> AsyncOpenAI:
        if self.client is None:
            if not self.api_key:
                raise RuntimeError("OPENAI_API_KEY is not configured.")
            self.client = AsyncOpenAI(api_key=self.api_key)
        return self.client

    async def generate_stream(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        **options: Any
    ) -> AsyncGenerator[Dict[str, Any], None]:
        kwargs = {"model": self.model_id, "messages": messages, "stream": True}
        if tools:
            kwargs["tools"] = tools

        response = await self._get_client().chat.completions.create(**kwargs)
        async for chunk in response:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            payload = {}
            if delta.content:
                payload["content"] = delta.content
            if delta.tool_calls:
                payload["tool_calls"] = delta.tool_calls
            if payload:
                yield payload

    async def generate_structured(
        self,
        messages: List[Dict[str, Any]],
        response_schema: Type[BaseModel],
        **options: Any
    ) -> BaseModel:
        response = await self._get_client().beta.chat.completions.parse(
            model=self.model_id,
            messages=messages,
            response_format=response_schema
        )
        return response.choices[0].message.parsed


class AnthropicAdapter(LLMProvider):
    """Anthropic Claude Provider Adapter (e.g., claude-3-5-sonnet)."""

    def __init__(self):
        self.api_key = os.getenv("ANTHROPIC_API_KEY", "")
        self.model_id = os.getenv("ANTHROPIC_MODEL_ID", "claude-3-5-sonnet-20241022")

    async def generate_stream(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        **options: Any
    ) -> AsyncGenerator[Dict[str, Any], None]:
        if False:  # Preserve the abstract async-generator protocol for callers.
            yield {}
        raise NotImplementedError("Anthropic streaming is not implemented.")

    async def generate_structured(
        self,
        messages: List[Dict[str, Any]],
        response_schema: Type[BaseModel],
        **options: Any
    ) -> BaseModel:
        raise NotImplementedError("Anthropic structured output adapter available in Phase 2.")


class GoogleAdapter(LLMProvider):
    """Google Gemini Provider Adapter (e.g., gemini-1.5-pro)."""

    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY", "")
        self.model_id = os.getenv("GOOGLE_MODEL_ID", "gemini-1.5-pro")

    async def generate_stream(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        **options: Any
    ) -> AsyncGenerator[Dict[str, Any], None]:
        if False:  # Preserve the abstract async-generator protocol for callers.
            yield {}
        raise NotImplementedError("Google Gemini streaming is not implemented.")

    async def generate_structured(
        self,
        messages: List[Dict[str, Any]],
        response_schema: Type[BaseModel],
        **options: Any
    ) -> BaseModel:
        raise NotImplementedError("Google Gemini structured output adapter available in Phase 2.")


class LocalAdapter(LLMProvider):
    """OpenAI-compatible local provider adapter (for example, Ollama)."""

    def __init__(self, client: Optional[AsyncOpenAI] = None):
        self.base_url = os.getenv("LOCAL_LLM_URL", "http://localhost:11434/v1")
        self.model_id = os.getenv("LOCAL_MODEL_ID", "llama3")
        self.client = client

    def _get_client(self) -> AsyncOpenAI:
        if self.client is None:
            # Local OpenAI-compatible servers commonly require a non-empty but
            # non-secret bearer value. It is created only when a call is made.
            self.client = AsyncOpenAI(base_url=self.base_url, api_key="local")
        return self.client

    async def generate_stream(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        **options: Any
    ) -> AsyncGenerator[Dict[str, Any], None]:
        response = await self._get_client().chat.completions.create(
            model=self.model_id,
            messages=messages,
            stream=True
        )
        async for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                yield {"content": chunk.choices[0].delta.content}

    async def generate_structured(
        self,
        messages: List[Dict[str, Any]],
        response_schema: Type[BaseModel],
        **options: Any
    ) -> BaseModel:
        response = await self._get_client().chat.completions.create(
            model=self.model_id,
            messages=messages,
            response_format={"type": "json_object"},
            stream=False
        )
        return response_schema.model_validate_json(response.choices[0].message.content or "{}")


_PROVIDER_MAP = {
    "nvidia": NVIDIAAdapter,
    "openai": OpenAIAdapter,
    "anthropic": AnthropicAdapter,
    "google": GoogleAdapter,
    "local": LocalAdapter,
}


def get_llm_provider(name: Optional[str] = None) -> LLMProvider:
    """Resolve the configured adapter without opening a network client."""
    provider_key = (name or os.getenv("LLM_PROVIDER", "nvidia")).strip().lower()
    try:
        adapter_cls = _PROVIDER_MAP[provider_key]
    except KeyError as exc:
        supported = ", ".join(sorted(_PROVIDER_MAP))
        raise ValueError(
            f"Unsupported LLM provider {provider_key!r}; choose one of: {supported}."
        ) from exc
    logger.info("[LLMProvider] Selected adapter %s.", adapter_cls.__name__)
    return adapter_cls()
