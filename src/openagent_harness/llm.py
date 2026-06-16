from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

from .env import sanitize_mapping


_DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
_DEFAULT_MODEL = "deepseek-v4-flash"

# USD per 1M tokens. Keep this table small and explicit so the budget gate is auditable.
# Values mirror the public DeepSeek API pricing page at the time this project was written.
_DEEPSEEK_PRICING_PER_1M = {
    "deepseek-v4-flash": {"input_cache_miss": 0.14, "input_cache_hit": 0.0028, "output": 0.28},
    "deepseek-v4-pro": {"input_cache_miss": 0.435, "input_cache_hit": 0.003625, "output": 0.87},
    # Deprecated compatibility names. They are left here so old configs still get a cost estimate.
    "deepseek-chat": {"input_cache_miss": 0.14, "input_cache_hit": 0.0028, "output": 0.28},
    "deepseek-reasoner": {"input_cache_miss": 0.14, "input_cache_hit": 0.0028, "output": 0.28},
}


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str

    def to_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass(frozen=True)
class ModelUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0

    def to_dict(self) -> dict[str, int | float]:
        return asdict(self)


@dataclass(frozen=True)
class LLMResponse:
    content: str
    usage: ModelUsage = field(default_factory=ModelUsage)
    raw: dict[str, Any] = field(default_factory=dict)


class LLMClient(Protocol):
    def chat(self, messages: list[ChatMessage], *, response_format_json: bool = False) -> LLMResponse:
        ...


def env_first(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return None


def env_first_name(*names: str) -> str | None:
    for name in names:
        if os.getenv(name):
            return name
    return None


def estimate_tokens_from_text(text: str) -> int:
    """Cheap deterministic fallback. Good enough for budget safety, not billing."""
    if not text:
        return 0
    # DeepSeek docs describe tokens roughly as character/word units. This conservative ratio avoids under-budgeting.
    return max(1, int(len(text) * 0.6))




def _safe_int(value: object, fallback: int) -> int:
    """Parse provider usage counters without crashing on sanitized or nonstandard fields."""
    if isinstance(value, bool):
        return fallback
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return fallback
    return fallback

def estimate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int, *, cache_hit: bool = False) -> float:
    pricing = _DEEPSEEK_PRICING_PER_1M.get(model)
    if not pricing:
        return 0.0
    input_key = "input_cache_hit" if cache_hit else "input_cache_miss"
    cost = (prompt_tokens / 1_000_000) * pricing[input_key] + (completion_tokens / 1_000_000) * pricing["output"]
    return round(cost, 8)


class OpenAICompatibleClient:
    """Minimal OpenAI-compatible chat client for DeepSeek or any compatible endpoint.

    The project intentionally uses the Python standard library here. Interview demos should not fail
    because optional SDK packages are missing, and the request payload remains easy to inspect.
    """

    def __init__(
        self,
        model: str = _DEFAULT_MODEL,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout_seconds: float = 60.0,
        max_tokens: int = 2048,
        thinking: str | None = None,
        reasoning_effort: str | None = None,
        user_id: str | None = None,
    ) -> None:
        self.model = model
        self.base_url = (base_url or env_first("OPENAGENT_BASE_URL", "DEEPSEEK_BASE_URL") or _DEFAULT_DEEPSEEK_BASE_URL).rstrip("/")
        self.api_key = api_key or env_first("OPENAGENT_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY")
        self.api_key_source = "direct" if api_key else env_first_name("OPENAGENT_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY")
        self.timeout_seconds = timeout_seconds
        self.max_tokens = max_tokens
        self.thinking = thinking
        self.reasoning_effort = reasoning_effort
        self.user_id = user_id

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def configuration_note(self) -> dict[str, str | bool | float | int | None]:
        return {
            "model": self.model,
            "base_url": self.base_url,
            "api_key_configured": self.is_configured(),
            "api_key_source": self.api_key_source,
            "timeout_seconds": self.timeout_seconds,
            "max_tokens": self.max_tokens,
            "thinking": self.thinking,
            "reasoning_effort": self.reasoning_effort,
        }

    def chat(self, messages: list[ChatMessage], *, response_format_json: bool = False) -> LLMResponse:
        if not self.api_key:
            raise RuntimeError("LLM API key is not configured. Set OPENAGENT_API_KEY or DEEPSEEK_API_KEY.")

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [message.to_dict() for message in messages],
            "max_tokens": self.max_tokens,
        }
        if response_format_json:
            payload["response_format"] = {"type": "json_object"}
        if self.thinking:
            payload["thinking"] = {"type": self.thinking}
        if self.reasoning_effort:
            payload["reasoning_effort"] = self.reasoning_effort
        if self.user_id:
            payload["user_id"] = self.user_id

        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        started = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw_data = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            details = sanitize_mapping({"details": exc.read().decode("utf-8", errors="replace")})["details"]
            raise RuntimeError(f"LLM API HTTP {exc.code}: {details}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"LLM API request failed after {round(time.monotonic() - started, 4)}s: {exc}") from exc

        raw = json.loads(raw_data)
        raw = sanitize_mapping(raw)
        choice = raw.get("choices", [{}])[0]
        message = choice.get("message", {})
        content = message.get("content") or ""
        usage = self._parse_usage(raw, messages, content)
        return LLMResponse(content=content, usage=usage, raw=raw)

    def _parse_usage(self, raw: dict[str, Any], messages: list[ChatMessage], content: str) -> ModelUsage:
        usage = raw.get("usage") or {}
        fallback_prompt = estimate_tokens_from_text("\n".join(m.content for m in messages))
        fallback_completion = estimate_tokens_from_text(content)

        prompt_tokens = _safe_int(usage.get("prompt_tokens"), fallback_prompt)
        completion_tokens = _safe_int(usage.get("completion_tokens"), fallback_completion)
        total_tokens = _safe_int(usage.get("total_tokens"), prompt_tokens + completion_tokens)
        return ModelUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            estimated_cost_usd=estimate_cost_usd(self.model, prompt_tokens, completion_tokens),
        )


class ReplayLLMClient:
    """Deterministic LLM double used in tests and offline demos."""

    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls: list[list[ChatMessage]] = []

    def chat(self, messages: list[ChatMessage], *, response_format_json: bool = False) -> LLMResponse:
        self.calls.append(messages)
        if not self.responses:
            raise RuntimeError("ReplayLLMClient has no responses left.")
        content = self.responses.pop(0)
        prompt_tokens = estimate_tokens_from_text("\n".join(message.content for message in messages))
        completion_tokens = estimate_tokens_from_text(content)
        return LLMResponse(
            content=content,
            usage=ModelUsage(prompt_tokens, completion_tokens, prompt_tokens + completion_tokens, 0.0),
            raw={"replay": True, "response_format_json": response_format_json},
        )
