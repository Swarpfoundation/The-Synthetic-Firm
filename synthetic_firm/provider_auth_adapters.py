"""Provider-specific safe auth adapters."""

from __future__ import annotations

import os
import shutil

from synthetic_firm.provider_auth import ProviderAuthSession, create_auth_session, get_provider_route, normalize_provider
from synthetic_firm.provider_auth_redaction import redact_auth_text


class ProviderAuthAdapterError(ValueError):
    """Raised when a provider adapter cannot produce safe metadata."""


def start_provider_auth(provider: str, *, requested_by: str, dry_run: bool = False) -> ProviderAuthSession:
    normalized = normalize_provider(provider)
    if normalized == "kimi-code":
        return _start_kimi_code(requested_by=requested_by, dry_run=dry_run)
    if normalized == "kimi-platform":
        return _status_kimi_platform(requested_by=requested_by)
    if normalized == "openai-codex":
        return _start_openai_codex(requested_by=requested_by, dry_run=dry_run)
    if normalized == "openai-api-key":
        return _status_openai_api_key(requested_by=requested_by)
    raise ProviderAuthAdapterError(f"Unsupported provider: {provider}")


def provider_auth_status(provider: str, *, requested_by: str = "system") -> ProviderAuthSession:
    normalized = normalize_provider(provider)
    if normalized == "kimi-code":
        return _status_kimi_code(requested_by=requested_by)
    if normalized == "kimi-platform":
        return _status_kimi_platform(requested_by=requested_by)
    if normalized == "openai-codex":
        return _status_openai_codex(requested_by=requested_by)
    if normalized == "openai-api-key":
        return _status_openai_api_key(requested_by=requested_by)
    raise ProviderAuthAdapterError(f"Unsupported provider: {provider}")


def _start_kimi_code(*, requested_by: str, dry_run: bool) -> ProviderAuthSession:
    route = get_provider_route("kimi-code")
    if _env_present("TSF_KIMI_CODE_API_KEY") or _env_present("TSF_KIMI_API_KEY"):
        return _status_kimi_code(requested_by=requested_by)
    kimi_path = shutil.which("kimi")
    if kimi_path:
        status = "pending_user_login" if dry_run else "pending_user_login"
        summary = "Run kimi login locally on the TSF machine, then run auth-status kimi-code."
        return create_auth_session(
            provider="kimi-code",
            auth_method="provider_cli_login",
            requested_by=requested_by,
            status=status,
            model_route=f"{route.provider}:{route.model}",
            credential_storage="provider_owned_cli",
            safe_summary=summary,
            login_url_present=False,
        )
    return create_auth_session(
        provider="kimi-code",
        auth_method="api_key_or_provider_cli",
        requested_by=requested_by,
        status="unavailable",
        model_route=f"{route.provider}:{route.model}",
        credential_storage="none",
        safe_summary="Kimi Code CLI is not available and no TSF Kimi Code API key is present.",
    )


def _status_kimi_code(*, requested_by: str) -> ProviderAuthSession:
    route = get_provider_route("kimi-code")
    if _env_present("TSF_KIMI_CODE_API_KEY") or _env_present("TSF_KIMI_API_KEY"):
        return create_auth_session(
            provider="kimi-code",
            auth_method="api_key",
            requested_by=requested_by,
            status="connected",
            model_route=f"{route.provider}:{route.model}",
            credential_storage="environment_variable",
            safe_summary="Kimi Code API key is present. Route uses kimi-for-coding.",
        )
    if shutil.which("kimi"):
        return create_auth_session(
            provider="kimi-code",
            auth_method="provider_cli_login",
            requested_by=requested_by,
            status="pending_user_login",
            model_route=f"{route.provider}:{route.model}",
            credential_storage="provider_owned_cli",
            safe_summary="Kimi Code CLI is available. Run kimi login locally to connect.",
        )
    return create_auth_session(
        provider="kimi-code",
        auth_method="api_key_or_provider_cli",
        requested_by=requested_by,
        status="unavailable",
        model_route=f"{route.provider}:{route.model}",
        credential_storage="none",
        safe_summary="Kimi Code is not connected.",
    )


def _status_kimi_platform(*, requested_by: str) -> ProviderAuthSession:
    route = get_provider_route("kimi-platform")
    configured_model = os.environ.get("TSF_KIMI_PLATFORM_MODEL", route.model).strip() or route.model
    connected = _env_present("TSF_KIMI_PLATFORM_API_KEY")
    return create_auth_session(
        provider="kimi-platform",
        auth_method="api_key",
        requested_by=requested_by,
        status="connected" if connected else "unavailable",
        model_route=f"kimi-platform:{configured_model}",
        credential_storage="environment_variable" if connected else "none",
        safe_summary=(
            "Kimi Platform API key is present. This is separate from Kimi Code membership."
            if connected
            else "Kimi Platform API key is not present."
        ),
    )


def _start_openai_codex(*, requested_by: str, dry_run: bool) -> ProviderAuthSession:
    route = get_provider_route("openai-codex")
    if not shutil.which("codex"):
        return create_auth_session(
            provider="openai-codex",
            auth_method="provider_cli_login",
            requested_by=requested_by,
            status="unavailable",
            model_route=f"{route.provider}:{route.model}",
            credential_storage="none",
            safe_summary="OpenAI Codex CLI is not available. Install/sign in manually, then run auth-status again.",
        )
    return create_auth_session(
        provider="openai-codex",
        auth_method="provider_cli_login",
        requested_by=requested_by,
        status="pending_device_authorization" if dry_run else "pending_user_login",
        model_route=f"{route.provider}:{route.model}",
        credential_storage="provider_owned_cli",
        safe_summary="Run codex --login locally and choose Sign in with ChatGPT. This is not generic OpenAI API access.",
        login_url_present=False,
        device_code_present=False,
    )


def _status_openai_codex(*, requested_by: str) -> ProviderAuthSession:
    route = get_provider_route("openai-codex")
    if shutil.which("codex"):
        return create_auth_session(
            provider="openai-codex",
            auth_method="provider_cli_login",
            requested_by=requested_by,
            status="pending_user_login",
            model_route=f"{route.provider}:{route.model}",
            credential_storage="provider_owned_cli",
            safe_summary="Codex CLI is available. TSF stores only provider-owned CLI metadata.",
        )
    return create_auth_session(
        provider="openai-codex",
        auth_method="provider_cli_login",
        requested_by=requested_by,
        status="unavailable",
        model_route=f"{route.provider}:{route.model}",
        credential_storage="none",
        safe_summary="OpenAI Codex CLI is not available. Install/sign in manually, then run auth-status again.",
    )


def _status_openai_api_key(*, requested_by: str) -> ProviderAuthSession:
    route = get_provider_route("openai-api-key")
    model = os.environ.get("TSF_OPENAI_MODEL", "gpt-5.5").strip() or "gpt-5.5"
    connected = _env_present("TSF_OPENAI_API_KEY")
    return create_auth_session(
        provider="openai-api-key",
        auth_method="api_key",
        requested_by=requested_by,
        status="connected" if connected else "unavailable",
        model_route=f"openai-api-key:{model}",
        credential_storage="environment_variable" if connected else "none",
        safe_summary=(
            "OpenAI API key is present. This route is separate from ChatGPT/Codex sign-in."
            if connected
            else "OpenAI API key is not present."
        ),
    )


def safe_provider_error(exc: Exception) -> str:
    return redact_auth_text(str(exc))


def _env_present(name: str) -> bool:
    return bool(os.environ.get(name, "").strip())
