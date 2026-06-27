from __future__ import annotations

from pathlib import Path
from typing import Any

from .agent_loop import AgentRunOutcome, JsonActionCodingAgent
from .llm import OpenAICompatibleClient
from .schema import TaskSpec


class ScriptedAgent:
    """Deterministic local agent for interviews where API spend is not worth it."""

    def apply(self, repo_dir: Path, goal: str) -> list[Path]:
        changed: list[Path] = []
        goal_lower = goal.lower()

        app_py = repo_dir / "app.py"
        if app_py.exists() and "zero" in goal_lower:
            text = app_py.read_text(encoding="utf-8")
            if "if b == 0:" not in text and "return a / b" in text:
                app_py.write_text(
                    text.replace("    return a / b\n", "    if b == 0:\n        return None\n    return a / b\n"),
                    encoding="utf-8",
                )
                changed.append(app_py)

        pager_py = repo_dir / "pager.py"
        if pager_py.exists() and "off-by-one" in goal_lower:
            text = pager_py.read_text(encoding="utf-8")
            if "start = number * size" in text:
                pager_py.write_text(
                    text.replace("    start = number * size\n", "    start = (number - 1) * size\n"),
                    encoding="utf-8",
                )
                changed.append(pager_py)

        cli_tool_py = repo_dir / "cli_tool.py"
        if cli_tool_py.exists() and "invalid cli" in goal_lower:
            text = cli_tool_py.read_text(encoding="utf-8")
            single_quote_marker = "    if '--help' in argv:\n        print('usage: cli-tool [--help]')\n        return 0\n"
            double_quote_marker = '    if "--help" in argv:\n        print("usage: cli-tool [--help]")\n        return 0\n'
            marker = single_quote_marker if single_quote_marker in text else double_quote_marker
            if "return 2" not in text and marker in text:
                cli_tool_py.write_text(
                    text.replace(marker, marker + "    if argv:\n        return 2\n"),
                    encoding="utf-8",
                )
                changed.append(cli_tool_py)

        blog_py = repo_dir / "blog.py"
        if blog_py.exists() and "slug conflict" in goal_lower:
            text = blog_py.read_text(encoding="utf-8")
            marker = "def create_post(existing_slugs, slug):\n"
            if "status': 409" not in text and marker in text:
                blog_py.write_text(
                    text.replace(marker, marker + "    if slug in existing_slugs:\n        return {'status': 409, 'slug': slug}\n"),
                    encoding="utf-8",
                )
                changed.append(blog_py)

        csv_cleaner_py = repo_dir / "csv_cleaner.py"
        if csv_cleaner_py.exists() and "utf-8 bom" in goal_lower:
            text = csv_cleaner_py.read_text(encoding="utf-8")
            if "lstrip('\\ufeff')" not in text and "return value.strip()" in text:
                csv_cleaner_py.write_text(
                    text.replace("    return value.strip()\n", "    return value.lstrip('\\ufeff').strip()\n"),
                    encoding="utf-8",
                )
                changed.append(csv_cleaner_py)

        cache_py = repo_dir / "cache.py"
        if cache_py.exists() and "expired" in goal_lower:
            text = cache_py.read_text(encoding="utf-8")
            old = '    return item["value"]\n'
            new = (
                '    if item.get("expires_at", float("inf")) <= now:\n'
                '        del store[key]\n'
                '        return None\n'
                '    return item["value"]\n'
            )
            if "del store[key]" not in text and old in text:
                cache_py.write_text(text.replace(old, new), encoding="utf-8")
                changed.append(cache_py)

        retry_py = repo_dir / "retry_policy.py"
        if retry_py.exists() and "retry" in goal_lower and "client errors" in goal_lower:
            text = retry_py.read_text(encoding="utf-8")
            old = "    return attempt < max_attempts\n"
            new = (
                "    if attempt >= max_attempts:\n"
                "        return False\n"
                "    if status_code in {408, 429}:\n"
                "        return True\n"
                "    if 500 <= status_code < 600:\n"
                "        return True\n"
                "    return False\n"
            )
            if "status_code in {408, 429}" not in text and old in text:
                retry_py.write_text(text.replace(old, new), encoding="utf-8")
                changed.append(retry_py)



        http_client_py = repo_dir / "http_client.py"
        if http_client_py.exists() and "429" in goal_lower:
            text = http_client_py.read_text(encoding="utf-8")
            old = "RETRYABLE_STATUSES = {500, 502, 503, 504}\n"
            new = "RETRYABLE_STATUSES = {429, 500, 502, 503, 504}\n"
            if old in text and "{429," not in text:
                http_client_py.write_text(text.replace(old, new), encoding="utf-8")
                changed.append(http_client_py)

        config_loader_py = repo_dir / "config_loader.py"
        if config_loader_py.exists() and "nested" in goal_lower and "headers" in goal_lower:
            text = config_loader_py.read_text(encoding="utf-8")
            old = """def load_config(user_config: dict | None) -> dict:\n    \"\"\"Merge user configuration over defaults.\"\"\"\n    config = DEFAULTS.copy()\n    if user_config:\n        config.update(user_config)\n    return config\n"""
            new = """def _deep_merge(base: dict, override: dict) -> dict:\n    merged = {}\n    for key, value in base.items():\n        if isinstance(value, dict):\n            merged[key] = _deep_merge(value, {})\n        else:\n            merged[key] = value\n    for key, value in override.items():\n        if isinstance(value, dict) and isinstance(merged.get(key), dict):\n            merged[key] = _deep_merge(merged[key], value)\n        else:\n            merged[key] = value\n    return merged\n\n\ndef load_config(user_config: dict | None) -> dict:\n    \"\"\"Merge user configuration over defaults without mutating DEFAULTS.\"\"\"\n    return _deep_merge(DEFAULTS, user_config or {})\n"""
            if old in text and "def _deep_merge" not in text:
                config_loader_py.write_text(text.replace(old, new), encoding="utf-8")
                changed.append(config_loader_py)

        error_response_py = repo_dir / "error_response.py"
        if error_response_py.exists() and "leaks" in goal_lower:
            text = error_response_py.read_text(encoding="utf-8")
            old = """    return {\"status_code\": 500, \"body\": {\"error\": str(exc)}}\n"""
            new = """    message = str(exc) if debug else \"internal server error\"\n    return {\"status_code\": 500, \"body\": {\"error\": message}}\n"""
            if old in text and "internal server error" not in text:
                error_response_py.write_text(text.replace(old, new), encoding="utf-8")
                changed.append(error_response_py)

        return changed


class ApiAgent:
    """DeepSeek/OpenAI-compatible coding agent adapter with a guarded local tool loop."""

    def __init__(
        self,
        model: str,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout_seconds: float = 60.0,
        max_tokens: int = 2048,
        thinking: str | None = None,
        reasoning_effort: str | None = None,
        wire_api: str | None = None,
        disable_response_storage: bool | None = None,
    ) -> None:
        self.model = model
        self.client = OpenAICompatibleClient(
            model=model,
            base_url=base_url,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            max_tokens=max_tokens,
            thinking=thinking,
            reasoning_effort=reasoning_effort,
            wire_api=wire_api,
            disable_response_storage=disable_response_storage,
        )

    def configuration_note(self) -> dict[str, Any]:
        config = self.client.configuration_note()
        config.update(
            {
                "reason": "API mode is wired but disabled until a key and budget are approved.",
                "next_step": "Set DEEPSEEK_API_KEY and run with budget.enable_llm_calls=true or --allow-llm-calls.",
            }
        )
        return config

    def is_configured(self) -> bool:
        return self.client.is_configured()

    def apply(self, repo_dir: Path, spec: TaskSpec, *, failure_context: str | None = None) -> AgentRunOutcome:
        max_steps = int(spec.budget.get("max_steps", 8))
        prompt_char_budget = int(spec.budget.get("prompt_char_budget", 40_000))
        return JsonActionCodingAgent(
            self.client,
            max_steps=max_steps,
            prompt_char_budget=prompt_char_budget,
            adaptive=True,
        ).apply(repo_dir, spec, failure_context=failure_context)
