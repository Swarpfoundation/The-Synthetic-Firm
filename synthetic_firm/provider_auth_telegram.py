"""Telegram-safe provider auth handoff messages."""

from __future__ import annotations

from synthetic_firm.provider_auth import ProviderAuthSession, get_provider_route
from synthetic_firm.provider_auth_redaction import is_safe_login_url, redact_auth_text


def format_auth_handoff(
    session: ProviderAuthSession,
    *,
    login_url: str | None = None,
    device_code: str | None = None,
) -> str:
    route = get_provider_route(session.provider)
    lines = [
        "The Synthetic Firm provider auth handoff",
        f"Provider: {session.provider}",
        f"Route: {route.route_type}",
        f"Model route: {session.model_route}",
        "",
        f"Status: {session.status}",
        f"Action: {session.safe_summary}",
    ]
    if login_url and is_safe_login_url(login_url):
        lines.append(f"Login URL: {login_url}")
    elif login_url:
        lines.append("Login URL was not sent because it may contain sensitive material.")
    if device_code:
        lines.append(f"Device code present: {bool(device_code)}")
    lines.extend(
        [
            "",
            "Never paste provider tokens, API keys, cookies, or authorization codes into chat.",
            f"Follow up: synthetic-firm auth-status {session.provider}",
        ]
    )
    return redact_auth_text("\n".join(lines))


def format_auth_status(session: ProviderAuthSession) -> str:
    return redact_auth_text(
        "\n".join(
            [
                "The Synthetic Firm provider auth status",
                f"Provider: {session.provider}",
                f"Status: {session.status}",
                f"Model route: {session.model_route}",
                f"Credential storage: {session.credential_storage}",
                f"Summary: {session.safe_summary}",
            ]
        )
    )
