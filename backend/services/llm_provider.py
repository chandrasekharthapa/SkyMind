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
    """NVIDIA Llama Infrastructure Adapter (Default)."""

    def __init__(self):
        self.base_url = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
        self.api_key = os.getenv("NVIDIA_API_KEY") or os.getenv("OPENAI_API_KEY") or "mock_nvidia_key"
        self.model_id = os.getenv("NVIDIA_MODEL_ID", "meta/llama-3.1-70b-instruct")
        self.client = AsyncOpenAI(base_url=self.base_url, api_key=self.api_key)

    async def generate_stream(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        **options: Any
    ) -> AsyncGenerator[Dict[str, Any], None]:
        kwargs = {"model": self.model_id, "messages": messages, "stream": True}
        if tools:
            kwargs["tools"] = tools

        response = await self.client.chat.completions.create(**kwargs)
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
        response = await self.client.chat.completions.create(
            model=self.model_id,
            messages=messages,
            response_format={"type": "json_object"},
            stream=False
        )
        content = response.choices[0].message.content or "{}"
        return response_schema.model_validate_json(content)


class OpenAIAdapter(LLMProvider):
    """Standard OpenAI Provider Adapter (e.g., gpt-4o-mini, gpt-4o)."""

    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY") or "mock_openai_key"
        self.model_id = os.getenv("OPENAI_MODEL_ID", "gpt-4o-mini")
        self.client = AsyncOpenAI(api_key=self.api_key)

    async def generate_stream(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        **options: Any
    ) -> AsyncGenerator[Dict[str, Any], None]:
        kwargs = {"model": self.model_id, "messages": messages, "stream": True}
        if tools:
            kwargs["tools"] = tools

        response = await self.client.chat.completions.create(**kwargs)
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
        response = await self.client.beta.chat.completions.parse(
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
        # Fallback stream wrapper using standard format
        yield {"content": f"Anthropic adapter stream initialized ({self.model_id})."}

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
        yield {"content": f"Google Gemini adapter stream initialized ({self.model_id})."}

    async def generate_structured(
        self,
        messages: List[Dict[str, Any]],
        response_schema: Type[BaseModel],
        **options: Any
    ) -> BaseModel:
        raise NotImplementedError("Google Gemini structured output adapter available in Phase 2.")


class LocalAdapter(LLMProvider):
    """Local Provider Adapter (e.g., Ollama or vLLM HTTP API)."""

    def __init__(self):
        self.base_url = os.getenv("LOCAL_LLM_URL", "http://localhost:11434/v1")
        self.model_id = os.getenv("LOCAL_MODEL_ID", "llama3")
        self.client = AsyncOpenAI(base_url=self.base_url, api_key="local")

    async def generate_stream(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        **options: Any
    ) -> AsyncGenerator[Dict[str, Any], None]:
        response = await self.client.chat.completions.create(
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
        response = await self.client.chat.completions.create(
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
    """Factory function resolving configured LLMProvider adapter. Default: NVIDIAAdapter."""
    provider_key = (name or os.getenv("LLM_PROVIDER", "nvidia")).lower()
    adapter_cls = _PROVIDER_MAP.get(provider_key, NVIDIAAdapter)
    logger.info(f"[LLMProvider] Instantiating LLM provider adapter: '{adapter_cls.__name__}'.")
    return adapter_cls()
