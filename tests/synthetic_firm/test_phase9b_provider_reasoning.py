from __future__ import annotations

import json

import pytest

from synthetic_firm.agent_reasoning import build_agent_context, build_agent_reasoning_request, validate_reasoning_output
from synthetic_firm.autonomous_workday import run_agent_turn, start_workday
from synthetic_firm.llm_client import complete_agent_reasoning, dry_run_agent_reasoning
from synthetic_firm.model_provider import ModelProviderError, provider_status, resolve_model_provider
from synthetic_firm.store import Store
from synthetic_firm.truthfulness_guard import validate_provider_reasoning_text


class _FakeMessage:
    content = json.dumps(
        {
            "summary": "Atlas reviewed persisted evidence and found no completed external work.",
            "proposed_tasks": [],
            "messages_to_agents": [{"recipient_agent_id": "sentinel", "content": "Review public claims only."}],
            "human_tasks": [],
            "assumptions": [],
            "evidence_refs": ["persisted task"],
            "blocked_reasons": [],
            "public_report_notes": ["No public report generated yet."],
            "private_founder_notes": [],
        }
    )


class _FakeChoice:
    message = _FakeMessage()


class _FakeCompletions:
    def create(self, **kwargs):
        return type("Completion", (), {"choices": [_FakeChoice()]})()


class _FakeChat:
    completions = _FakeCompletions()


class _FakeClient:
    chat = _FakeChat()


def test_default_provider_is_dry_run(monkeypatch):
    monkeypatch.delenv("TSF_MODEL_PROVIDER", raising=False)

    route = resolve_model_provider()

    assert route.provider == "dry-run"
    assert route.dry_run is True
    assert provider_status()["provider"] == "dry-run"


def test_missing_provider_key_fails_closed(monkeypatch):
    monkeypatch.setenv("TSF_MODEL_PROVIDER", "kimi-code")
    monkeypatch.setenv("TSF_MODEL_DRY_RUN", "false")
    monkeypatch.delenv("TSF_KIMI_CODE_API_KEY", raising=False)
    monkeypatch.delenv("TSF_KIMI_API_KEY", raising=False)

    route = resolve_model_provider()

    assert route.connected is False
    assert "unavailable" in route.safe_summary.lower()


def test_provider_routes_are_distinct_and_no_browser_cookie_route(monkeypatch):
    monkeypatch.setenv("TSF_MODEL_PROVIDER", "kimi-code")
    monkeypatch.setenv("TSF_KIMI_CODE_API_KEY", "sk-kimi-code-secret")
    kimi_code = resolve_model_provider()
    monkeypatch.setenv("TSF_MODEL_PROVIDER", "kimi-platform")
    monkeypatch.setenv("TSF_KIMI_PLATFORM_API_KEY", "sk-kimi-platform-secret")
    kimi_platform = resolve_model_provider()
    monkeypatch.setenv("TSF_MODEL_PROVIDER", "openai-api")
    monkeypatch.setenv("TSF_OPENAI_API_KEY", "sk-openai-secret")
    openai = resolve_model_provider()

    assert kimi_code.model == "kimi-for-coding"
    assert kimi_code.base_url != kimi_platform.base_url
    assert kimi_platform.provider == "kimi-platform"
    assert openai.provider == "openai-api"
    with pytest.raises(ModelProviderError):
        resolve_model_provider({"TSF_MODEL_PROVIDER": "chatgpt-browser-cookie"})


def test_provider_status_redacts_secrets(monkeypatch):
    secret = "sk-kimi-code-secret-value"
    monkeypatch.setenv("TSF_MODEL_PROVIDER", "kimi-code")
    monkeypatch.setenv("TSF_KIMI_CODE_API_KEY", secret)

    dumped = json.dumps(provider_status())

    assert secret not in dumped
    assert "kimi-for-coding" in dumped


def test_dry_run_reasoning_response(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    store = Store()
    request = build_agent_reasoning_request(store, agent_id="atlas")

    response = dry_run_agent_reasoning(request)

    assert response.status == "success"
    assert response.dry_run is True
    assert response.structured_output is not None
    store.close()


def test_mocked_live_response_and_audit_without_secrets(monkeypatch, tmp_path):
    secret = "sk-openai-test-secret-value"
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    monkeypatch.setenv("TSF_MODEL_PROVIDER", "openai-api")
    monkeypatch.setenv("TSF_MODEL_DRY_RUN", "false")
    monkeypatch.setenv("TSF_OPENAI_API_KEY", secret)
    store = Store()
    request = build_agent_reasoning_request(store, agent_id="atlas")

    response = complete_agent_reasoning(request, store=store, client_factory=lambda **kwargs: _FakeClient())
    audit_dump = json.dumps([dict(row) for row in store.connection.execute("SELECT * FROM audit_log").fetchall()])

    assert response.status == "success"
    assert response.structured_output is not None
    assert secret not in audit_dump
    assert "model_reasoning_success" in audit_dump
    store.close()


def test_malformed_output_fails_closed(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    monkeypatch.setenv("TSF_MODEL_PROVIDER", "openai-api")
    monkeypatch.setenv("TSF_MODEL_DRY_RUN", "false")
    monkeypatch.setenv("TSF_OPENAI_API_KEY", "sk-openai-test-secret-value")
    store = Store()
    request = build_agent_reasoning_request(store, agent_id="sentinel")

    class BadMessage:
        content = "not json"

    class BadChoice:
        message = BadMessage()

    class BadCompletions:
        def create(self, **kwargs):
            return type("Completion", (), {"choices": [BadChoice()]})()

    class BadClient:
        chat = type("Chat", (), {"completions": BadCompletions()})()

    response = complete_agent_reasoning(request, store=store, client_factory=lambda **kwargs: BadClient())

    assert response.status == "failed"
    assert "malformed" in response.error_redacted.lower()
    store.close()


def test_provider_error_is_redacted(monkeypatch, tmp_path):
    secret = "sk-provider-error-secret-value"
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    monkeypatch.setenv("TSF_MODEL_PROVIDER", "openai-api")
    monkeypatch.setenv("TSF_MODEL_DRY_RUN", "false")
    monkeypatch.setenv("TSF_OPENAI_API_KEY", secret)
    store = Store()
    request = build_agent_reasoning_request(store, agent_id="atlas")

    response = complete_agent_reasoning(
        request,
        store=store,
        client_factory=lambda **kwargs: (_ for _ in ()).throw(RuntimeError(f"provider failed {secret}")),
    )
    audit_dump = json.dumps([dict(row) for row in store.connection.execute("SELECT * FROM audit_log").fetchall()])

    assert response.status == "failed"
    assert secret not in response.error_redacted
    assert secret not in audit_dump
    store.close()


def test_agent_context_excludes_private_founder_message_content(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    store = Store()
    store.create_founder_message(content="Private founder note private@example.com with token sk-private-value")

    context = build_agent_context(store, agent_id="atlas")

    assert "Private founder note" not in context
    assert "private@example.com" not in context
    assert "sk-private-value" not in context
    assert "founder_message_summary" in context
    store.close()


def test_agent_contexts_do_not_claim_unavailable_external_work(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    store = Store()

    scout = build_agent_context(store, agent_id="scout")
    forge = build_agent_context(store, agent_id="forge")
    pulse = build_agent_context(store, agent_id="pulse")

    assert "do not invent leads" in scout.lower()
    assert "do not claim code changes" in forge.lower()
    assert "do not claim outreach was sent" in pulse.lower()
    store.close()


def test_structured_output_validation_blocks_unsupported_claims():
    output = {
        "summary": "Pulse sent outreach to 25 leads.",
        "proposed_tasks": [],
        "messages_to_agents": [],
        "human_tasks": [],
        "assumptions": [],
        "evidence_refs": [],
        "blocked_reasons": [],
        "public_report_notes": [],
        "private_founder_notes": [],
    }

    result = validate_reasoning_output(output, evidence=[])

    assert result.allowed is False
    assert result.blocked_reasons


def test_structured_output_allows_assumptions():
    output = {
        "summary": "Atlas proposes exploring pricing as an assumption.",
        "proposed_tasks": [],
        "messages_to_agents": [],
        "human_tasks": [],
        "assumptions": ["pricing is an assumption"],
        "evidence_refs": [],
        "blocked_reasons": [],
        "public_report_notes": [],
        "private_founder_notes": [],
    }

    result = validate_reasoning_output(output, evidence=[])

    assert result.allowed is True


@pytest.mark.parametrize(
    "claim",
    [
        "We made $1000 revenue.",
        "Scout found 5 leads.",
        "Investor interest is confirmed.",
        "Forge deployed the app.",
        "Forge opened 2 PRs.",
        "Pulse sent outreach.",
    ],
)
def test_truthfulness_blocks_fake_business_claims(claim):
    result = validate_provider_reasoning_text(claim, evidence=[])

    assert result.allowed is False


def test_workday_uses_configured_provider_reasoning_dry_run(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    monkeypatch.setenv("TSF_MODEL_PROVIDER", "kimi-code")
    monkeypatch.setenv("TSF_KIMI_CODE_API_KEY", "sk-kimi-code-secret")
    monkeypatch.setenv("TSF_MODEL_DRY_RUN", "true")
    store = Store()
    start_workday(store)

    result = run_agent_turn(store, agent_id="forge")
    messages = store.list_messages()

    assert result["provider"] == "dry-run"
    assert any(message.message_type == "model_reasoning_summary" for message in messages)
    assert store.verify_audit()[0] is True
    store.close()


def test_public_export_excludes_raw_model_output_and_private_messages(monkeypatch, tmp_path):
    from synthetic_firm.control_room_export import build_control_room_snapshot

    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    monkeypatch.setenv("TSF_MODEL_PROVIDER", "kimi-code")
    monkeypatch.setenv("TSF_KIMI_CODE_API_KEY", "sk-kimi-code-secret")
    monkeypatch.setenv("TSF_MODEL_DRY_RUN", "true")
    store = Store()
    store.create_founder_message(content="Private founder message with private@example.com")
    start_workday(store)
    run_agent_turn(store, agent_id="atlas")

    dumped = json.dumps(build_control_room_snapshot(store, audience="public"))

    assert "Private founder message" not in dumped
    assert "private@example.com" not in dumped
    assert "system_instructions" not in dumped
    assert "sk-kimi-code-secret" not in dumped
    store.close()
