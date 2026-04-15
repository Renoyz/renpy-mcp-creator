"""LLM provider wrappers for Anthropic and OpenAI-compatible APIs."""

import json
from abc import ABC, abstractmethod
from typing import Any

import httpx
from anthropic import Anthropic
from openai import OpenAI


class LLMResponse:
    """Normalized LLM response regardless of provider."""

    def __init__(
        self,
        content_blocks: list[dict[str, Any]],
        stop_reason: str | None,
        usage: dict[str, int] | None = None,
    ) -> None:
        self.content_blocks = content_blocks
        self.stop_reason = stop_reason
        self.usage = usage or {}

    @property
    def text(self) -> str:
        """Concatenate all text blocks."""
        return "".join(
            block.get("text", "")
            for block in self.content_blocks
            if block.get("type") == "text"
        )

    @property
    def tool_calls(self) -> list[dict[str, Any]]:
        """Return all tool_use / function_call blocks in normalized form."""
        calls: list[dict[str, Any]] = []
        for block in self.content_blocks:
            if block.get("type") == "tool_use":
                calls.append(
                    {
                        "id": block.get("id"),
                        "name": block.get("name"),
                        "arguments": block.get("input", {}),
                    }
                )
            elif block.get("type") == "function_call":
                calls.append(
                    {
                        "id": block.get("id"),
                        "name": block.get("name"),
                        "arguments": block.get("arguments", {}),
                    }
                )
        return calls


class BaseProvider(ABC):
    """Abstract base for LLM providers."""

    @property
    @abstractmethod
    def tool_format(self) -> str:
        """Return preferred tool format: 'anthropic' or 'openai'."""
        raise NotImplementedError

    @abstractmethod
    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        system: str | None = None,
        model: str | None = None,
        max_tokens: int = 1024,
        temperature: float | None = None,
    ) -> LLMResponse:
        raise NotImplementedError


class AnthropicProvider(BaseProvider):
    """Anthropic-compatible provider (Kimi Code, Claude, etc.)."""

    DEFAULT_MODEL = "claude-3-5-sonnet"
    tool_format = "anthropic"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        default_model: str = DEFAULT_MODEL,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.client = Anthropic(api_key=api_key, base_url=base_url, http_client=http_client)
        self.default_model = default_model

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        system: str | None = None,
        model: str | None = None,
        max_tokens: int = 1024,
        temperature: float | None = None,
    ) -> LLMResponse:
        kwargs: dict[str, Any] = {
            "model": model or self.default_model,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if system is not None:
            kwargs["system"] = system
        if tools is not None:
            kwargs["tools"] = tools
        if temperature is not None:
            kwargs["temperature"] = temperature

        response = self.client.messages.create(**kwargs)

        blocks: list[dict[str, Any]] = []
        for block in response.content:
            if block.type == "text":
                blocks.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    }
                )

        usage = {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        }

        return LLMResponse(
            content_blocks=blocks,
            stop_reason=response.stop_reason,
            usage=usage,
        )


class OpenAICompatibleProvider(BaseProvider):
    """OpenAI-compatible provider (DeepSeek, Qwen, DashScope, etc.)."""

    DEFAULT_MODEL = "deepseek-chat"
    tool_format = "openai"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        default_model: str = DEFAULT_MODEL,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.client = OpenAI(api_key=api_key, base_url=base_url, http_client=http_client)
        self.default_model = default_model

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        system: str | None = None,
        model: str | None = None,
        max_tokens: int = 1024,
        temperature: float | None = None,
    ) -> LLMResponse:
        openai_messages = list(messages)
        if system is not None:
            # Prepend system message if not already present
            if not openai_messages or openai_messages[0].get("role") != "system":
                openai_messages.insert(0, {"role": "system", "content": system})

        kwargs: dict[str, Any] = {
            "model": model or self.default_model,
            "messages": openai_messages,
        }
        if tools is not None:
            kwargs["tools"] = tools
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        if temperature is not None:
            kwargs["temperature"] = temperature

        response = self.client.chat.completions.create(**kwargs)

        choice = response.choices[0]
        message = choice.message

        blocks: list[dict[str, Any]] = []
        if message.content:
            blocks.append({"type": "text", "text": message.content})

        if message.tool_calls:
            for tc in message.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}
                blocks.append(
                    {
                        "type": "function_call",
                        "id": tc.id,
                        "name": tc.function.name,
                        "arguments": args,
                    }
                )

        usage = {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "total_tokens": response.usage.total_tokens,
        }

        return LLMResponse(
            content_blocks=blocks,
            stop_reason=choice.finish_reason,
            usage=usage,
        )
