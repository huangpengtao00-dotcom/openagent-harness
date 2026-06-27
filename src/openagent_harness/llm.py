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
_DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
_DEFAULT_MODEL = "deepseek-v4-flash"
_CHAT_COMPLETIONS_WIRE_API = "chat_completions"
_RESPONSES_WIRE_API = "responses"
_RETRYABLE_HTTP_STATUS_CODES = {429, 502, 503, 504}
_DEFAULT_PROVIDER_MAX_RETRIES = 2
_DEFAULT_PROVIDER_RETRY_BACKOFF_SECONDS = 0.35

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


class ProviderTransientError(RuntimeError):
    """Provider returned a retryable transport/server error."""

    def __init__(self, status_code: int | None, message: str, *, attempts: int) -> None:
        self.status_code = status_code
        self.attempts = attempts
        super().__init__(message)


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


def _env_first_with_name(*names: str) -> tuple[str | None, str | None]:
    for name in names:
        value = os.getenv(name)
        if value:
            return value, name
    return None, None


def _looks_like_openai_model(model: str) -> bool:
    normalized = model.lower()
    return normalized.startswith(("gpt-", "o1", "o3", "o4", "o5", "chatgpt-", "codex-"))


def _truthy(value: str | None) -> bool:
    return bool(value and value.strip().lower() in {"1", "true", "yes", "on"})


def _normalize_wire_api(value: str | None) -> str:
    normalized = (value or _CHAT_COMPLETIONS_WIRE_API).strip().lower().replace("-", "_")
    if normalized in {"chat", "chat_completion", "chat_completions"}:
        return _CHAT_COMPLETIONS_WIRE_API
    if normalized == _RESPONSES_WIRE_API:
        return _RESPONSES_WIRE_API
    raise ValueError(f"Unsupported wire_api={value!r}. Expected chat_completions or responses.")


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
        wire_api: str | None = None,
        disable_response_storage: bool | None = None,
        provider_max_retries: int = _DEFAULT_PROVIDER_MAX_RETRIES,
        provider_retry_backoff_seconds: float = _DEFAULT_PROVIDER_RETRY_BACKOFF_SECONDS,
    ) -> None:
        self.model = model
        self.api_key, self.api_key_source = self._resolve_api_key(api_key, base_url)
        self.base_url, self.base_url_source = self._resolve_base_url(base_url)
        self.timeout_seconds = timeout_seconds
        self.max_tokens = max_tokens
        self.thinking = thinking
        self.reasoning_effort = reasoning_effort
        self.user_id = user_id
        self.wire_api = _normalize_wire_api(wire_api or env_first("OPENAGENT_WIRE_API", "OPENAI_WIRE_API"))
        self.disable_response_storage = (
            disable_response_storage
            if disable_response_storage is not None
            else _truthy(env_first("OPENAGENT_DISABLE_RESPONSE_STORAGE", "OPENAI_DISABLE_RESPONSE_STORAGE", "DISABLE_RESPONSE_STORAGE"))
        )
        self.provider_max_retries = max(0, int(provider_max_retries))
        self.provider_retry_backoff_seconds = max(0.0, float(provider_retry_backoff_seconds))

    def _resolve_api_key(self, api_key: str | None, base_url: str | None) -> tuple[str | None, str | None]:
        if api_key:
            return api_key, "direct"

        openagent_key, openagent_source = _env_first_with_name("OPENAGENT_API_KEY")
        if openagent_key:
            return openagent_key, openagent_source

        base_hint = (base_url or env_first("OPENAGENT_BASE_URL", "OPENAI_BASE_URL", "DEEPSEEK_BASE_URL") or "").lower()
        use_openai_first = _looks_like_openai_model(self.model) or "openai.com" in base_hint
        if use_openai_first:
            return _env_first_with_name("OPENAI_API_KEY", "DEEPSEEK_API_KEY")
        return _env_first_with_name("DEEPSEEK_API_KEY", "OPENAI_API_KEY")

    def _resolve_base_url(self, base_url: str | None) -> tuple[str, str]:
        if base_url:
            return base_url.rstrip("/"), "direct"

        openagent_base_url, openagent_source = _env_first_with_name("OPENAGENT_BASE_URL")
        if openagent_base_url:
            return openagent_base_url.rstrip("/"), openagent_source or "OPENAGENT_BASE_URL"

        if self.api_key_source == "OPENAI_API_KEY" or _looks_like_openai_model(self.model):
            openai_base_url, openai_source = _env_first_with_name("OPENAI_BASE_URL")
            return (openai_base_url or _DEFAULT_OPENAI_BASE_URL).rstrip("/"), openai_source or "openai_default"

        provider_base_url, provider_source = _env_first_with_name("DEEPSEEK_BASE_URL", "OPENAI_BASE_URL")
        return (provider_base_url or _DEFAULT_DEEPSEEK_BASE_URL).rstrip("/"), provider_source or "deepseek_default"

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def configuration_note(self) -> dict[str, str | bool | float | int | None]:
        return {
            "model": self.model,
            "base_url": self.base_url,
            "base_url_source": self.base_url_source,
            "wire_api": self.wire_api,
            "api_key_configured": self.is_configured(),
            "api_key_source": self.api_key_source,
            "timeout_seconds": self.timeout_seconds,
            "max_tokens": self.max_tokens,
            "thinking": self.thinking,
            "reasoning_effort": self.reasoning_effort,
            "disable_response_storage": self.disable_response_storage,
            "provider_max_retries": self.provider_max_retries,
            "provider_retry_backoff_seconds": self.provider_retry_backoff_seconds,
        }

    def chat(self, messages: list[ChatMessage], *, response_format_json: bool = False) -> LLMResponse:
        if not self.api_key:
            raise RuntimeError("LLM API key is not configured. Set OPENAGENT_API_KEY, DEEPSEEK_API_KEY, or OPENAI_API_KEY.")

        if self.wire_api == _RESPONSES_WIRE_API:
            return self._chat_via_responses(messages, response_format_json=response_format_json)

        return self._chat_via_chat_completions(messages, response_format_json=response_format_json)

    def _chat_via_chat_completions(self, messages: list[ChatMessage], *, response_format_json: bool = False) -> LLMResponse:
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
        if self.disable_response_storage:
            payload["store"] = False
        if self.user_id:
            payload["user_id"] = self.user_id

        raw = self._post_json("/chat/completions", payload)
        choice = raw.get("choices", [{}])[0]
        message = choice.get("message", {})
        content = message.get("content") or ""
        usage = self._parse_usage(raw, messages, content)
        return LLMResponse(content=content, usage=usage, raw=raw)

    def _chat_via_responses(self, messages: list[ChatMessage], *, response_format_json: bool = False) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": self.model,
            "input": [
                {
                    "role": message.role,
                    "content": message.content,
                }
                for message in messages
            ],
            "max_output_tokens": self.max_tokens,
        }
        if response_format_json:
            payload["text"] = {"format": {"type": "json_object"}}
        if self.reasoning_effort:
            payload["reasoning"] = {"effort": self.reasoning_effort}
        if self.disable_response_storage:
            payload["store"] = False
        if self.user_id:
            payload["user"] = self.user_id

        raw = self._post_json("/responses", payload)
        content = self._extract_responses_content(raw)
        usage = self._parse_usage(raw, messages, content)
        return LLMResponse(content=content, usage=usage, raw=raw)

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        started = time.monotonic()
        last_transient: ProviderTransientError | None = None
        total_attempts = self.provider_max_retries + 1
        for attempt in range(1, total_attempts + 1):
            request = urllib.request.Request(
                f"{self.base_url}{path}",
                data=body,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                    raw_data = response.read().decode("utf-8")
                raw = json.loads(raw_data)
                sanitized = sanitize_mapping(raw)
                if attempt > 1:
                    sanitized.setdefault("_provider_retry", {"attempts": attempt})
                return sanitized
            except urllib.error.HTTPError as exc:
                details = sanitize_mapping({"details": exc.read().decode("utf-8", errors="replace")})["details"]
                if exc.code not in _RETRYABLE_HTTP_STATUS_CODES:
                    raise RuntimeError(f"LLM API HTTP {exc.code}: {details}") from exc
                message = f"LLM provider transient HTTP {exc.code} after {attempt}/{total_attempts} attempts: {details}"
                last_transient = ProviderTransientError(exc.code, message, attempts=attempt)
                if attempt >= total_attempts:
                    raise last_transient from exc
            except urllib.error.URLError as exc:
                message = f"LLM provider request failed after {round(time.monotonic() - started, 4)}s and {attempt}/{total_attempts} attempts: {exc}"
                last_transient = ProviderTransientError(None, message, attempts=attempt)
                if attempt >= total_attempts:
                    raise last_transient from exc

            time.sleep(self.provider_retry_backoff_seconds * attempt)

        if last_transient is not None:
            raise last_transient
        raise RuntimeError("LLM API request failed without a provider response.")

    def _extract_responses_content(self, raw: dict[str, Any]) -> str:
        if isinstance(raw.get("output_text"), str):
            return str(raw["output_text"])

        chunks: list[str] = []
        for item in raw.get("output") or []:
            if not isinstance(item, dict):
                continue
            for content_item in item.get("content") or []:
                if not isinstance(content_item, dict):
                    continue
                if content_item.get("type") == "output_text" and isinstance(content_item.get("text"), str):
                    chunks.append(str(content_item["text"]))
        return "".join(chunks)

    def _parse_usage(self, raw: dict[str, Any], messages: list[ChatMessage], content: str) -> ModelUsage:
        usage = raw.get("usage") or {}
        fallback_prompt = estimate_tokens_from_text("\n".join(m.content for m in messages))
        fallback_completion = estimate_tokens_from_text(content)

        prompt_tokens = _safe_int(usage.get("prompt_tokens", usage.get("input_tokens")), fallback_prompt)
        completion_tokens = _safe_int(usage.get("completion_tokens", usage.get("output_tokens")), fallback_completion)
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
