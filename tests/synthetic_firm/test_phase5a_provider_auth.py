from __future__ import annotations

import os

import pytest

from synthetic_firm.cli import main
from synthetic_firm.provider_auth import ProviderAuthError, get_provider_route, provider_routes, session_to_dict
from synthetic_firm.provider_auth_adapters import provider_auth_status, start_provider_auth
from synthetic_firm.provider_auth_redaction import is_safe_login_url, redact_auth_text
from synthetic_firm.provider_auth_store import list_auth_sessions, revoke_auth_metadata, save_auth_session
from synthetic_firm.provider_auth_telegram import format_auth_handoff
from synthetic_firm.runtime_permissions import RuntimePermissionError, validate_provider_auth_actor
from synthetic_firm.store import Store


def test_auth_sessions_persist_safe_metadata_and_schema_has_no_token_fields(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    store = Store()
    session = provider_auth_status("openai-api-key")
    save_auth_session(store, session)

    columns = [
        row["name"]
        for row in store.connection.execute("PRAGMA table_info(provider_auth_sessions)").fetchall()
    ]
    forbidden_fragments = ("token", "secret", "cookie", "credential_value", "access", "refresh")

    assert list_auth_sessions(store)[0].provider == "openai-api-key"
    assert not any(fragment in column for column in columns for fragment in forbidden_fragments)
    store.close()


def test_unknown_provider_rejected():
    with pytest.raises(ProviderAuthError):
        get_provider_route("chatgpt-browser-cookie")


def test_kimi_code_route_uses_stable_model_and_is_separate_from_platform():
    code = get_provider_route("kimi-code")
    platform = get_provider_route("kimi-platform")

    assert code.model == "kimi-for-coding"
    assert platform.model == "kimi-k2.6"
    assert code.route_type != platform.route_type


def test_kimi_code_env_key_reports_connected_without_printing_key(monkeypatch):
    monkeypatch.setenv("TSF_KIMI_CODE_API_KEY", "sk-kimi-sensitive-test-value")

    session = provider_auth_status("kimi-code")
    payload = str(session_to_dict(session))

    assert session.status == "connected"
    assert session.model_route == "kimi-code:kimi-for-coding"
    assert "sk-kimi-sensitive-test-value" not in payload


def test_kimi_code_missing_key_or_cli_unavailable_is_safe(monkeypatch):
    monkeypatch.delenv("TSF_KIMI_CODE_API_KEY", raising=False)
    monkeypatch.delenv("TSF_KIMI_API_KEY", raising=False)
    monkeypatch.setattr("shutil.which", lambda _cmd: None)

    session = provider_auth_status("kimi-code")

    assert session.status == "unavailable"
    assert "not connected" in session.safe_summary.lower()


def test_kimi_platform_api_key_route_separate_and_safe(monkeypatch):
    monkeypatch.setenv("TSF_KIMI_PLATFORM_API_KEY", "sk-platform-sensitive")

    session = provider_auth_status("kimi-platform")

    assert session.status == "connected"
    assert session.model_route.startswith("kimi-platform:")
    assert "sk-platform-sensitive" not in str(session_to_dict(session))


def test_openai_codex_unavailable_is_not_generic_api(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _cmd: None)

    session = provider_auth_status("openai-codex")

    assert session.status == "unavailable"
    assert session.model_route == "openai-codex:codex-managed"
    assert "generic OpenAI API" not in session.safe_summary


def test_openai_api_key_presence_detected_safely(monkeypatch):
    monkeypatch.setenv("TSF_OPENAI_API_KEY", "sk-sensitive-openai-value")

    session = provider_auth_status("openai-api-key")

    assert session.status == "connected"
    assert "sk-sensitive-openai-value" not in str(session_to_dict(session))


def test_no_browser_cookie_provider_or_actions_exist():
    assert "chatgpt-browser-cookie" not in provider_routes()
    assert not hasattr(__import__("synthetic_firm.provider_auth_adapters"), "browser_cookie_read")


def test_telegram_handoff_redacts_sensitive_url_and_warns():
    session = start_provider_auth("openai-codex", requested_by="founder", dry_run=True)
    message = format_auth_handoff(
        session,
        login_url="https://example.com/login?access_token=secret-token&state=safe",
    )

    assert "access_token=secret-token" not in message
    assert "not sent" in message
    assert "Never paste provider tokens" in message


@pytest.mark.parametrize(
    "raw",
    [
        "Bearer abc.def.secret",
        "api_key=sk-sensitive123456789",
        "refresh_token=refresh-secret",
        "cookie=sessionid-secret",
        "https://example.com/cb?code=abc123&access_token=tok",
    ],
)
def test_redaction_covers_secret_shapes(raw):
    redacted = redact_auth_text(raw)

    assert "secret" not in redacted.lower()
    assert "abc123" not in redacted
    assert "access_token=tok" not in redacted


def test_safe_login_url_classifier():
    assert is_safe_login_url("https://example.com/login") is True
    assert is_safe_login_url("https://example.com/login?token=sensitive") is False


def test_provider_auth_start_requires_control_actor():
    with pytest.raises(RuntimePermissionError):
        validate_provider_auth_actor(actor_type="agent", live=True)

    validate_provider_auth_actor(actor_type="agent", live=False)
    validate_provider_auth_actor(actor_type="control", live=True)


def test_auth_start_status_revoke_audit_without_secrets(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    monkeypatch.setenv("TSF_OPENAI_API_KEY", "sk-sensitive-openai-value")
    store = Store()

    session = provider_auth_status("openai-api-key", requested_by="system")
    save_auth_session(store, session)
    revoke_auth_metadata(store, "openai-api-key", requested_by="founder")
    dump = "\n".join(store.connection.iterdump())

    assert "sk-sensitive-openai-value" not in dump
    assert store.verify_audit()[0] is True
    store.close()


def test_cli_provider_auth_commands_safe(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    monkeypatch.setenv("TSF_OPENAI_API_KEY", "sk-sensitive-openai-value")

    assert main(["provider-routes"]) == 0
    assert main(["auth-status", "openai-api-key"]) == 0
    assert main(["auth-start", "kimi-code", "--dry-run", "--telegram-dry-run"]) == 0
    assert main(["auth-redact-test", "Bearer abc.secret"]) == 0

    output = capsys.readouterr().out
    assert "sk-sensitive-openai-value" not in output
    assert "abc.secret" not in output
    assert "kimi-for-coding" in output
