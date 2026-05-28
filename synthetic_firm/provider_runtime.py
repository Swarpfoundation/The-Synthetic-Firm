"""Provider-owned runtime adapters for TSF agents."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import Callable

from synthetic_firm.agent_registry import AgentRegistry
from synthetic_firm.budget import BudgetPolicy
from synthetic_firm.provider_auth import get_provider_route, normalize_provider
from synthetic_firm.provider_auth_adapters import provider_auth_status
from synthetic_firm.provider_auth_redaction import redact_auth_text
from synthetic_firm.store import Store


class ProviderRuntimeError(ValueError):
    """Raised when provider runtime execution is not safely available."""


@dataclass(frozen=True)
class RuntimeInvocation:
    provider: str
    agent_id: str
    model_route: str
    command: tuple[str, ...]
    dry_run: bool
    executable: bool
    safe_summary: str


@dataclass(frozen=True)
class RuntimeResult:
    provider: str
    agent_id: str
    dry_run: bool
    returncode: int | None
    output_redacted: str
    safe_summary: str


def provider_runtime_status(provider: str) -> dict[str, object]:
    normalized = normalize_provider(provider)
    session = provider_auth_status(normalized)
    if normalized == "kimi-code":
        cli_available = shutil.which("kimi") is not None
    elif normalized == "openai-codex":
        cli_available = shutil.which("codex") is not None
    else:
        cli_available = False
    runtime_ready = session.status in {"connected", "pending_user_login", "pending_device_authorization"} and cli_available
    summary = session.safe_summary
    if normalized == "kimi-code" and session.status == "connected" and not cli_available:
        summary = "Kimi Code auth metadata is connected; install the provider-owned Kimi CLI before live runtime use."
    return {
        "provider": normalized,
        "auth_status": session.status,
        "model_route": session.model_route,
        "cli_available": cli_available,
        "runtime_ready": runtime_ready,
        "credential_storage": session.credential_storage,
        "safe_summary": summary,
    }


def build_runtime_invocation(
    *,
    provider: str,
    agent_id: str,
    prompt: str,
    dry_run: bool = True,
) -> RuntimeInvocation:
    normalized = normalize_provider(provider)
    if normalized not in {"kimi-code", "openai-codex"}:
        raise ProviderRuntimeError(f"Provider runtime is not implemented for {normalized}")
    session = provider_auth_status(normalized)
    route = get_provider_route(normalized)
    if session.status not in {"connected", "pending_user_login", "pending_device_authorization"}:
        raise ProviderRuntimeError(session.safe_summary)
    if normalized == "kimi-code":
        command = _kimi_command(prompt)
    else:
        command = _codex_command(prompt)
    executable = _command_exists(command[0])
    if not dry_run and not executable:
        raise ProviderRuntimeError(f"Provider CLI is not available: {command[0]}")
    return RuntimeInvocation(
        provider=normalized,
        agent_id=agent_id,
        model_route=f"{route.provider}:{route.model}",
        command=tuple(command),
        dry_run=dry_run,
        executable=executable,
        safe_summary=f"{normalized} runtime invocation prepared for {agent_id}.",
    )


def invoke_provider_runtime(
    store: Store,
    *,
    provider: str,
    agent_id: str,
    prompt: str,
    task_id: str | None = None,
    dry_run: bool = True,
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> RuntimeResult:
    invocation = build_runtime_invocation(provider=provider, agent_id=agent_id, prompt=prompt, dry_run=dry_run)
    if not dry_run:
        if not task_id:
            raise ProviderRuntimeError("Live provider runtime invocation requires a persisted task id.")
        _check_live_budget(store, agent_id=agent_id, task_id=task_id)
    store.append_audit(
        actor_type="orchestrator",
        actor_id="provider_runtime",
        action="provider_runtime_invoke",
        target_type="provider_runtime",
        target_id=provider,
        risk_level="medium",
        summary=invocation.safe_summary,
        metadata={"provider": invocation.provider, "agent_id": agent_id, "task_id": task_id, "dry_run": dry_run},
    )
    if dry_run:
        return RuntimeResult(
            provider=invocation.provider,
            agent_id=agent_id,
            dry_run=True,
            returncode=None,
            output_redacted="Dry-run: provider runtime command was not executed.",
            safe_summary=invocation.safe_summary,
        )
    run = runner or subprocess.run
    env = _safe_child_env()
    completed = run(
        invocation.command,
        check=False,
        text=True,
        capture_output=True,
        env=env,
        timeout=120,
    )
    store.record_budget_usage(
        amount_usd=0.0,
        loop_steps=1,
        tool_calls=1,
        summary=f"Provider runtime invocation recorded for {agent_id}.",
        agent_id=agent_id,
        task_id=task_id,
    )
    output = redact_auth_text((completed.stdout or "") + (completed.stderr or ""))
    return RuntimeResult(
        provider=invocation.provider,
        agent_id=agent_id,
        dry_run=False,
        returncode=completed.returncode,
        output_redacted=output,
        safe_summary=f"{invocation.provider} runtime exited with code {completed.returncode}.",
    )


def invocation_to_dict(invocation: RuntimeInvocation) -> dict[str, object]:
    return {
        "provider": invocation.provider,
        "agent_id": invocation.agent_id,
        "model_route": invocation.model_route,
        "command": _safe_command_preview(invocation.command),
        "dry_run": invocation.dry_run,
        "executable": invocation.executable,
        "safe_summary": invocation.safe_summary,
    }


def result_to_dict(result: RuntimeResult) -> dict[str, object]:
    return result.__dict__.copy()


def _kimi_command(prompt: str) -> list[str]:
    if _command_exists("kimi"):
        return ["kimi", "--model", "kimi-for-coding", prompt]
    return ["kimi", "--model", "kimi-for-coding", prompt]


def _codex_command(prompt: str) -> list[str]:
    return ["codex", prompt]


def _command_exists(command: str) -> bool:
    return shutil.which(command) is not None


def _safe_child_env() -> dict[str, str]:
    env: dict[str, str] = {}
    for name in ("PATH", "HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "TERM", "TSF_HOME"):
        if os.environ.get(name):
            env[name] = os.environ[name]
    for name in (
        "TSF_KIMI_CODE_API_KEY",
        "TSF_KIMI_API_KEY",
        "KIMI_API_KEY",
        "TSF_KIMI_BASE_URL",
        "KIMI_BASE_URL",
    ):
        if os.environ.get(name):
            env[name] = os.environ[name]
    if env.get("TSF_KIMI_CODE_API_KEY") and not env.get("KIMI_API_KEY"):
        env["KIMI_API_KEY"] = env["TSF_KIMI_CODE_API_KEY"]
    if env.get("TSF_KIMI_API_KEY") and not env.get("KIMI_API_KEY"):
        env["KIMI_API_KEY"] = env["TSF_KIMI_API_KEY"]
    if env.get("TSF_KIMI_BASE_URL") and not env.get("KIMI_BASE_URL"):
        env["KIMI_BASE_URL"] = env["TSF_KIMI_BASE_URL"]
    return env


def _safe_command_preview(command: tuple[str, ...]) -> list[str]:
    preview = list(command)
    if preview:
        preview[-1] = "<prompt redacted>"
    return preview


def _check_live_budget(store: Store, *, agent_id: str, task_id: str) -> None:
    registry = AgentRegistry.from_file()
    profile = registry.get(agent_id)
    task = store.get_task(task_id)
    company_limit = sum(agent.budget.daily_usd for agent in registry.list())
    task_limit = task.budget_limit if task.budget_limit is not None else profile.budget.daily_usd
    max_steps = task.max_steps if task.max_steps is not None else profile.budget.max_turns
    policy = BudgetPolicy(
        agent_daily_limit_usd=profile.budget.daily_usd,
        task_limit_usd=task_limit,
        company_daily_limit_usd=company_limit,
        max_loop_steps=max_steps,
        max_tool_calls=max_steps,
        dry_run=False,
    )
    decision = store.evaluate_persisted_budget(agent_id=agent_id, task_id=task_id, policy=policy)
    if not decision.allowed:
        raise ProviderRuntimeError(decision.reason)
