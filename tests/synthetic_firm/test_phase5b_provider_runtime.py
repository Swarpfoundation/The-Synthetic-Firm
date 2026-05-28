from __future__ import annotations

import subprocess

import pytest

from synthetic_firm.agent_registry import AgentRegistry
from synthetic_firm.cli import main
from synthetic_firm.provider_runtime import (
    ProviderRuntimeError,
    build_runtime_invocation,
    invoke_provider_runtime,
    provider_runtime_status,
)
from synthetic_firm.store import Store


def test_all_agents_route_to_kimi_code_model():
    registry = AgentRegistry.from_file()

    for profile in registry.list():
        assert profile.model_policy.provider == "kimi-coding"
        assert profile.model_policy.model == "kimi-for-coding"
        assert profile.model_policy.api_key_alias == "TSF_KIMI_API_KEY"


def test_kimi_code_runtime_plan_uses_kimi_for_coding(monkeypatch):
    monkeypatch.setenv("TSF_KIMI_CODE_API_KEY", "sk-kimi-sensitive-test-value")
    monkeypatch.setattr("shutil.which", lambda command: "/usr/bin/kimi" if command == "kimi" else None)

    invocation = build_runtime_invocation(
        provider="kimi-code",
        agent_id="atlas",
        prompt="Say hello.",
        dry_run=True,
    )

    assert invocation.provider == "kimi-code"
    assert invocation.model_route == "kimi-code:kimi-for-coding"
    assert "kimi-for-coding" in invocation.command
    assert "sk-kimi-sensitive-test-value" not in str(invocation)


def test_openai_codex_runtime_plan_is_codex_managed(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda command: "/usr/bin/codex" if command == "codex" else None)

    invocation = build_runtime_invocation(
        provider="openai-codex",
        agent_id="forge",
        prompt="Plan work.",
        dry_run=True,
    )

    assert invocation.model_route == "openai-codex:codex-managed"
    assert invocation.command[0] == "codex"


def test_runtime_status_is_safe(monkeypatch):
    monkeypatch.setenv("TSF_KIMI_CODE_API_KEY", "sk-kimi-sensitive-test-value")

    status = provider_runtime_status("kimi-code")

    assert status["auth_status"] == "connected"
    assert "sk-kimi-sensitive-test-value" not in str(status)


def test_dry_run_invoke_writes_audit_without_execution(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    monkeypatch.setenv("TSF_KIMI_CODE_API_KEY", "sk-kimi-sensitive-test-value")
    store = Store()

    result = invoke_provider_runtime(
        store,
        provider="kimi-code",
        agent_id="atlas",
        prompt="Dry run only.",
        dry_run=True,
    )

    assert result.dry_run is True
    assert result.returncode is None
    assert store.verify_audit()[0] is True
    dump = "\n".join(store.connection.iterdump())
    assert "sk-kimi-sensitive-test-value" not in dump
    store.close()


def test_mocked_live_invoke_redacts_output(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    monkeypatch.setenv("TSF_KIMI_CODE_API_KEY", "sk-kimi-sensitive-test-value")
    monkeypatch.setattr("shutil.which", lambda command: "/usr/bin/kimi" if command == "kimi" else None)
    store = Store()
    task = store.create_task(
        title="Mock provider runtime task",
        objective="Check mocked provider runtime execution.",
        created_by_agent_id="atlas",
        assigned_agent_id="atlas",
        budget_limit=1.0,
        max_steps=5,
        plain_english_summary="Atlas checks mocked provider runtime execution.",
    )

    def runner(*_args, **_kwargs):
        return subprocess.CompletedProcess(
            args=["kimi"],
            returncode=0,
            stdout="Bearer secret-token\n",
            stderr="api_key=sk-sensitive123456789\n",
        )

    result = invoke_provider_runtime(
        store,
        provider="kimi-code",
        agent_id="atlas",
        task_id=task.task_id,
        prompt="Mock live.",
        dry_run=False,
        runner=runner,
    )

    assert result.returncode == 0
    assert "secret-token" not in result.output_redacted
    assert "sk-sensitive" not in result.output_redacted
    store.close()


def test_missing_provider_cli_blocks_live_execution(monkeypatch):
    monkeypatch.delenv("TSF_KIMI_CODE_API_KEY", raising=False)
    monkeypatch.delenv("TSF_KIMI_API_KEY", raising=False)
    monkeypatch.setattr("shutil.which", lambda _command: None)

    with pytest.raises(ProviderRuntimeError):
        build_runtime_invocation(provider="kimi-code", agent_id="atlas", prompt="Run.", dry_run=False)


def test_cli_runtime_commands_safe(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    monkeypatch.setenv("TSF_KIMI_CODE_API_KEY", "sk-kimi-sensitive-test-value")
    monkeypatch.setattr("shutil.which", lambda command: "/usr/bin/kimi" if command == "kimi" else None)

    assert main(["provider-runtime-status", "kimi-code"]) == 0
    assert main(["provider-runtime-plan", "kimi-code", "--agent-id", "atlas", "--prompt", "Hello"]) == 0
    assert main(["provider-runtime-invoke", "kimi-code", "--agent-id", "atlas", "--prompt", "Hello", "--dry-run"]) == 0

    output = capsys.readouterr().out
    assert "kimi-for-coding" in output
    assert "Hello" not in output
    assert "<prompt redacted>" in output
    assert "sk-kimi-sensitive-test-value" not in output
