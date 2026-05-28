"""Provider auth models and route registry for The Synthetic Firm."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from synthetic_firm.time_utils import utc_iso

PROVIDERS = frozenset({"kimi-code", "kimi-platform", "openai-codex", "openai-api-key"})
AUTH_STATUSES = frozenset(
    {
        "not_started",
        "pending_user_login",
        "pending_device_authorization",
        "connected",
        "failed",
        "expired",
        "revoked",
        "unavailable",
    }
)
CREDENTIAL_STORAGE = frozenset(
    {
        "provider_owned_cli",
        "environment_variable",
        "local_keychain_reference",
        "external_secret_manager_reference",
        "none",
    }
)


class ProviderAuthError(ValueError):
    """Raised when provider auth metadata is unsafe or unsupported."""


@dataclass(frozen=True)
class ProviderRoute:
    provider: str
    model: str
    auth: str
    route_type: str
    safe_summary: str


@dataclass(frozen=True)
class ProviderAuthSession:
    session_id: str
    provider: str
    auth_method: str
    requested_by: str
    status: str
    created_at: str
    updated_at: str
    expires_at: str | None
    login_url_present: bool
    device_code_present: bool
    account_label: str | None
    model_route: str
    credential_storage: str
    safe_summary: str
    last_error_redacted: str | None = None


def provider_routes() -> dict[str, ProviderRoute]:
    return {
        "kimi-code": ProviderRoute(
            provider="kimi-code",
            model="kimi-for-coding",
            auth="TSF_KIMI_CODE_API_KEY or provider-owned Kimi CLI auth",
            route_type="Kimi Code membership route",
            safe_summary="Kimi Code uses stable model id kimi-for-coding.",
        ),
        "kimi-platform": ProviderRoute(
            provider="kimi-platform",
            model="kimi-k2.6",
            auth="TSF_KIMI_PLATFORM_API_KEY",
            route_type="Kimi Platform API route",
            safe_summary="Kimi Platform is separate from Kimi Code membership billing.",
        ),
        "openai-codex": ProviderRoute(
            provider="openai-codex",
            model="codex-managed",
            auth="provider-owned Codex CLI sign-in",
            route_type="OpenAI Codex route",
            safe_summary="OpenAI Codex is not a generic OpenAI API adapter.",
        ),
        "openai-api-key": ProviderRoute(
            provider="openai-api-key",
            model="configurable",
            auth="TSF_OPENAI_API_KEY",
            route_type="OpenAI API-key route",
            safe_summary="OpenAI API key route is separate from ChatGPT/Codex sign-in.",
        ),
    }


def get_provider_route(provider: str) -> ProviderRoute:
    normalized = normalize_provider(provider)
    return provider_routes()[normalized]


def normalize_provider(provider: str) -> str:
    normalized = str(provider or "").strip().lower()
    if normalized not in PROVIDERS:
        raise ProviderAuthError(f"Unknown provider: {provider}")
    return normalized


def create_auth_session(
    *,
    provider: str,
    auth_method: str,
    requested_by: str,
    status: str,
    model_route: str,
    credential_storage: str,
    safe_summary: str,
    expires_at: str | None = None,
    login_url_present: bool = False,
    device_code_present: bool = False,
    account_label: str | None = None,
    last_error_redacted: str | None = None,
    session_id: str | None = None,
) -> ProviderAuthSession:
    normalized_provider = normalize_provider(provider)
    normalized_status = str(status or "").strip().lower()
    if normalized_status not in AUTH_STATUSES:
        raise ProviderAuthError(f"Unsupported auth status: {status}")
    storage = str(credential_storage or "").strip()
    if storage not in CREDENTIAL_STORAGE:
        raise ProviderAuthError(f"Unsupported credential storage: {credential_storage}")
    now = utc_iso()
    return ProviderAuthSession(
        session_id=session_id or f"auth_{uuid4().hex[:12]}",
        provider=normalized_provider,
        auth_method=_required(auth_method, "auth_method"),
        requested_by=_required(requested_by, "requested_by"),
        status=normalized_status,
        created_at=now,
        updated_at=now,
        expires_at=expires_at,
        login_url_present=bool(login_url_present),
        device_code_present=bool(device_code_present),
        account_label=account_label,
        model_route=_required(model_route, "model_route"),
        credential_storage=storage,
        safe_summary=_required(safe_summary, "safe_summary"),
        last_error_redacted=last_error_redacted,
    )


def session_to_dict(session: ProviderAuthSession) -> dict[str, Any]:
    return session.__dict__.copy()


def route_to_dict(route: ProviderRoute) -> dict[str, str]:
    return route.__dict__.copy()


def _required(value: str, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ProviderAuthError(f"{name} is required")
    return text
