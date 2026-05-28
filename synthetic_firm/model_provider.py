"""Safe model provider route resolution for bounded agent reasoning."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

from synthetic_firm.provider_auth_redaction import redact_auth_text

MODEL_PROVIDERS = frozenset({"dry-run", "kimi-code", "kimi-platform", "openai-api"})


class ModelProviderError(ValueError):
    """Raised when model provider configuration fails closed."""


@dataclass(frozen=True)
class ModelProviderRoute:
    provider: str
    model: str
    base_url: str | None
    api_key_env: str | None
    connected: bool
    dry_run: bool
    timeout_seconds: float
    max_input_chars: int
    max_output_chars: int
    safe_summary: str

    def public_status(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "model": self.model,
            "connected": self.connected,
            "dry_run": self.dry_run,
            "credential_storage": "environment_variable" if self.api_key_env and self.connected else "none",
            "safe_summary": self.safe_summary,
        }


def resolve_model_provider(env: Mapping[str, str] | None = None) -> ModelProviderRoute:
    env_map = env if env is not None else os.environ
    provider = _provider_name(env_map.get("TSF_MODEL_PROVIDER") or "dry-run")
    dry_run = _bool(env_map.get("TSF_MODEL_DRY_RUN"), default=True) or provider == "dry-run"
    timeout = _float(env_map.get("TSF_MODEL_TIMEOUT_SECONDS"), default=60.0)
    max_input = _int(env_map.get("TSF_MODEL_MAX_INPUT_CHARS"), default=12000)
    max_output = _int(env_map.get("TSF_MODEL_MAX_OUTPUT_CHARS"), default=4000)
    if provider == "dry-run":
        return ModelProviderRoute(
            provider="dry-run",
            model="dry-run",
            base_url=None,
            api_key_env=None,
            connected=True,
            dry_run=True,
            timeout_seconds=timeout,
            max_input_chars=max_input,
            max_output_chars=max_output,
            safe_summary="Dry-run model provider is active. No live model call will be made.",
        )
    if provider == "kimi-code":
        key_env = _first_present(env_map, ("TSF_KIMI_CODE_API_KEY", "TSF_KIMI_API_KEY"))
        connected = key_env is not None
        return ModelProviderRoute(
            provider=provider,
            model="kimi-for-coding",
            base_url="https://api.kimi.com/coding/v1",
            api_key_env=key_env or "TSF_KIMI_CODE_API_KEY",
            connected=connected,
            dry_run=dry_run,
            timeout_seconds=timeout,
            max_input_chars=max_input,
            max_output_chars=max_output,
            safe_summary=(
                "Kimi Code route is configured with model kimi-for-coding."
                if connected
                else "Kimi Code route is unavailable because no TSF Kimi Code API key is present."
            ),
        )
    if provider == "kimi-platform":
        model = env_map.get("TSF_KIMI_PLATFORM_MODEL", "kimi-k2.6").strip() or "kimi-k2.6"
        base_url = env_map.get("TSF_KIMI_PLATFORM_BASE_URL", "https://api.moonshot.ai/v1").strip()
        connected = bool(env_map.get("TSF_KIMI_PLATFORM_API_KEY", "").strip())
        return ModelProviderRoute(
            provider=provider,
            model=model,
            base_url=base_url,
            api_key_env="TSF_KIMI_PLATFORM_API_KEY",
            connected=connected,
            dry_run=dry_run,
            timeout_seconds=timeout,
            max_input_chars=max_input,
            max_output_chars=max_output,
            safe_summary=(
                "Kimi Platform route is configured separately from Kimi Code."
                if connected
                else "Kimi Platform route is unavailable because TSF_KIMI_PLATFORM_API_KEY is not present."
            ),
        )
    if provider == "openai-api":
        model = env_map.get("TSF_OPENAI_MODEL", "gpt-5.5").strip() or "gpt-5.5"
        connected = bool(env_map.get("TSF_OPENAI_API_KEY", "").strip())
        return ModelProviderRoute(
            provider=provider,
            model=model,
            base_url=None,
            api_key_env="TSF_OPENAI_API_KEY",
            connected=connected,
            dry_run=dry_run,
            timeout_seconds=timeout,
            max_input_chars=max_input,
            max_output_chars=max_output,
            safe_summary=(
                "OpenAI API route is configured. It is separate from ChatGPT/Codex browser sign-in."
                if connected
                else "OpenAI API route is unavailable because TSF_OPENAI_API_KEY is not present."
            ),
        )
    raise ModelProviderError(f"Unsupported model provider: {provider}")


def provider_status(env: Mapping[str, str] | None = None) -> dict[str, object]:
    return resolve_model_provider(env).public_status()


def provider_api_key(route: ModelProviderRoute, env: Mapping[str, str] | None = None) -> str:
    env_map = env if env is not None else os.environ
    if not route.api_key_env:
        raise ModelProviderError("Provider route does not use an API key")
    value = env_map.get(route.api_key_env, "").strip()
    if not value:
        raise ModelProviderError(f"Provider credential is missing: {route.api_key_env}")
    return value


def safe_provider_error(exc: Exception) -> str:
    return redact_auth_text(str(exc))


def _provider_name(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in MODEL_PROVIDERS:
        raise ModelProviderError(f"Unknown model provider: {value}")
    return normalized


def _first_present(env: Mapping[str, str], names: tuple[str, ...]) -> str | None:
    for name in names:
        if env.get(name, "").strip():
            return name
    return None


def _bool(value: str | None, *, default: bool) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _float(value: str | None, *, default: float) -> float:
    try:
        return float(value) if value not in {None, ""} else default
    except ValueError as exc:
        raise ModelProviderError("TSF_MODEL_TIMEOUT_SECONDS must be numeric") from exc


def _int(value: str | None, *, default: int) -> int:
    try:
        parsed = int(value) if value not in {None, ""} else default
    except ValueError as exc:
        raise ModelProviderError("Model character limits must be integers") from exc
    if parsed <= 0:
        raise ModelProviderError("Model character limits must be positive")
    return parsed
