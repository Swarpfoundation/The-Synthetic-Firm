"""Safe Render deployment adapter for TSF backend/runtime services."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping

from synthetic_firm.deployment import (
    DeploymentCredentialStatus,
    DeploymentHealthCheck,
    DeploymentPlan,
    DeploymentRollbackPlan,
    credential_status_to_dict,
    create_deployment_plan,
    save_credential_status_record,
    save_deployment_record,
)
from synthetic_firm.deployment_checks import run_deployment_checks
from synthetic_firm.deployment_policy import evaluate_deployment_policy, load_deployment_policy, sentinel_review_deployment_plan
from synthetic_firm.notification_queue import enqueue_notification
from synthetic_firm.provider_auth_redaction import redact_auth_text
from synthetic_firm.store import Store
from synthetic_firm.time_utils import utc_iso

CommandRunner = Callable[[list[str], Path | None, Mapping[str, str] | None], subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class RenderStatus:
    enabled: bool
    cli_available: bool
    api_key_present: bool
    api_service_id_present: bool
    scheduler_service_id_present: bool
    deploy_method: str
    blueprint_path: str
    safe_summary: str


def render_status(env: Mapping[str, str] | None = None) -> dict[str, object]:
    env_map = env if env is not None else os.environ
    credential = render_credential_status(env=env_map)
    enabled = _bool(env_map.get("TSF_RENDER_ENABLED"), default=False)
    status = RenderStatus(
        enabled=enabled,
        cli_available=credential.cli_available,
        api_key_present=credential.credential_present,
        api_service_id_present=bool(_render_service_id(env_map, "render_backend_api")),
        scheduler_service_id_present=bool(_render_service_id(env_map, "render_scheduler_worker")),
        deploy_method=_render_deploy_method(env_map),
        blueprint_path=env_map.get("TSF_RENDER_BLUEPRINT_PATH", "render.yaml"),
        safe_summary=credential.safe_summary,
    )
    payload = status.__dict__.copy()
    payload["credential_status"] = credential_status_to_dict(credential)
    return payload


def render_credential_status(
    *,
    env: Mapping[str, str] | None = None,
    store: Store | None = None,
    target: str = "render_backend_api",
) -> DeploymentCredentialStatus:
    env_map = env if env is not None else os.environ
    enabled = _bool(env_map.get("TSF_RENDER_ENABLED"), default=False)
    cli_path = shutil.which("render")
    api_key = _render_api_key(env_map)
    deploy_method = _render_deploy_method(env_map)
    blueprint_path = Path(env_map.get("TSF_RENDER_BLUEPRINT_PATH", "render.yaml"))
    service_id = _render_service_id(env_map, target)
    missing: list[str] = []
    if deploy_method == "cli" and not cli_path:
        missing.append("Install Render CLI in the TSF runtime environment.")
    if deploy_method not in {"api", "cli"}:
        missing.append("Set Render deploy method to api or cli.")
    if not api_key:
        missing.extend(
            (
                "Create Render API access in the Render dashboard.",
                "Set Render API access as a provider environment variable in the runtime environment.",
            )
        )
    if target == "render_backend_api" and not env_map.get("TSF_RENDER_API_SERVICE_ID", "").strip():
        missing.append("Provide the Render backend API service ID.")
    if target == "render_scheduler_worker" and not (
        env_map.get("TSF_RENDER_SCHEDULER_SERVICE_ID", "").strip()
        or env_map.get("TSF_RENDER_WORKER_SERVICE_ID", "").strip()
    ):
        missing.append("Provide the Render scheduler worker service ID.")
    if not blueprint_path.exists():
        missing.append("Add or confirm render.yaml for backend readiness validation.")
    deploy_enabled = _bool(env_map.get("TSF_RENDER_DEPLOY_ENABLED"), default=False)
    if enabled and not deploy_enabled:
        missing.append("Render live deploys remain disabled until explicit staging policy is enabled.")
    summary = "Render deployment readiness is available." if enabled and not missing else "Render deployment readiness setup is pending."
    status = DeploymentCredentialStatus(
        provider="render",
        enabled=enabled,
        cli_available=bool(cli_path),
        cli_version_redacted=_render_version_redacted() if cli_path else None,
        credential_present=bool(api_key),
        credential_source="env" if api_key else "missing",
        project_linked=bool(service_id),
        target_configured=blueprint_path.exists(),
        safe_summary=summary if enabled else "Render adapter is disabled by default.",
        missing_requirements=tuple(missing),
        human_task_required=bool(missing),
        last_checked_at=utc_iso(),
    )
    if store is not None and status.human_task_required:
        _create_render_setup_human_tasks(store, status, target=target)
    if store is not None:
        check_id = save_credential_status_record(store, status)
        store.append_audit(
            actor_type="orchestrator",
            actor_id="deployment_credentials",
            action="deployment_credential_status",
            target_type="deployment_provider",
            target_id="render",
            risk_level="low" if not status.human_task_required else "medium",
            summary=status.safe_summary,
            metadata={
                "check_id": check_id,
                "enabled": status.enabled,
                "cli_available": status.cli_available,
                "credential_present": status.credential_present,
            },
        )
    return status


def create_render_deployment_plan(
    *,
    target: str = "render_backend_api",
    environment: str = "preview",
    env: Mapping[str, str] | None = None,
) -> DeploymentPlan:
    env_map = env if env is not None else os.environ
    service_id_name = "TSF_RENDER_API_SERVICE_ID" if target == "render_backend_api" else "TSF_RENDER_SCHEDULER_SERVICE_ID"
    blocked = None
    if not _render_api_key(env_map):
        blocked = "Render API access is missing."
    elif target != "render_postgres_future" and not env_map.get(service_id_name, "").strip():
        blocked = f"Render service id is missing: {service_id_name}"
    elif environment == "production":
        blocked = "Render production deployment is blocked in this phase."
    state = "production_candidate" if environment == "production" else "validation_required"
    if blocked:
        state = "production_blocked" if environment == "production" else "validation_required"
    return create_deployment_plan(
        target=target,
        environment=environment,
        command_plan=_command_plan(target, environment),
        checks_required=(
            "backend compileall",
            "backend ruff",
            "backend tests",
            "brand guard",
            "audit verification",
            "Render blueprint validation",
            "Sentinel review",
        ),
        risk_level="high" if environment == "production" else "medium",
        rollback_plan=DeploymentRollbackPlan(
            steps=("Use Render dashboard or deploy history to restore a previous known-good deploy.",),
            summary="Rollback uses Render deploy history; no destructive datastore action is allowed.",
        ),
        health_check=DeploymentHealthCheck(
            checks=("GET /health", "GET /api/public/control-room/snapshot", "verify scheduler status"),
            summary="Backend health checks verify read-only API and scheduler visibility.",
        ),
        sentinel_review="Sentinel review required: backend deploy must be health-checkable, rollbackable, and secret-free.",
        public_summary="Backend/API deployment readiness for TSF public progress services.",
        state=state,
        blocked_reason=blocked,
    )


def deploy_render_service(
    store: Store,
    *,
    target: str = "render_backend_api",
    environment: str = "preview",
    dry_run: bool = True,
    env: Mapping[str, str] | None = None,
    runner: CommandRunner | None = None,
) -> dict[str, object]:
    env_map = env if env is not None else os.environ
    credential_status = render_credential_status(env=env_map, store=store, target=target)
    plan = create_render_deployment_plan(target=target, environment=environment, env=env_map)
    checks = run_deployment_checks(store, target=target, run_heavy=False)
    sentinel = sentinel_review_deployment_plan(plan, checks)
    decision = evaluate_deployment_policy(store, plan, checks)
    if plan.blocked_reason:
        _create_render_human_task(store, plan.blocked_reason, target=target)
    if credential_status.human_task_required:
        _enqueue_deployment_setup_notifications(store)
    if credential_status.human_task_required:
        state = "validation_required"
    else:
        state = decision.state if decision.allowed and sentinel.allowed else (plan.state if plan.blocked_reason else "validation_failed")
    live_gate = _render_live_gate(env_map, credential_status, environment=environment)
    if dry_run or not live_gate[0] or load_deployment_policy(env_map).dry_run or not decision.allowed or not sentinel.allowed or plan.blocked_reason:
        if not dry_run and not live_gate[0]:
            store.append_audit(
                actor_type="orchestrator",
                actor_id="render_adapter",
                action="deployment_render_live_block",
                target_type="deployment_provider",
                target_id="render",
                risk_level="medium",
                summary=live_gate[1],
            )
        record = save_deployment_record(store, plan=plan, checks=checks, state=state)
        return {
            "dry_run": True,
            "executed": False,
            "summary": "Render deployment planned in dry-run mode.",
            "deployment": record.deployment_id,
            "policy": decision.__dict__,
            "sentinel": sentinel.__dict__,
        }
    service_id = _render_service_id(env_map, target)
    if _render_deploy_method(env_map) == "cli":
        runner = runner or _run
        completed = runner(["render", "deploys", "create", service_id, "--wait", "--confirm"], None, _safe_env(env_map))
        executed = completed.returncode == 0
        render_deploy_id = None
    else:
        deploy_payload = _post_render_deploy(env_map, service_id)
        executed = True
        render_deploy_id = _render_deploy_id(deploy_payload)
    live_plan = create_render_deployment_plan(target=target, environment=environment, env=env_map)
    state = "production_deployed" if executed and environment == "production" else _deployed_state(environment)
    if not executed:
        state = "failed"
    record = save_deployment_record(store, plan=live_plan, checks=checks, state=state)
    store.append_audit(
        actor_type="orchestrator",
        actor_id="render_adapter",
        action="deployment_render_staging_triggered",
        target_type="deployment_provider",
        target_id="render",
        risk_level="medium",
        summary="Render staging deploy was triggered through the configured deploy adapter.",
        metadata={
            "method": _render_deploy_method(env_map),
            "target": target,
            "render_deploy_id_present": bool(render_deploy_id),
        },
    )
    return {
        "dry_run": False,
        "executed": executed,
        "deployment": record.deployment_id,
        "render_deploy_id_present": bool(render_deploy_id),
        "summary": "Render staging deploy triggered.",
    }


def validate_render_command(command: str) -> bool:
    lowered = f" {command.lower()} "
    if lowered.strip() == "render --version":
        return True
    if "render blueprints validate" in lowered:
        return True
    if "render deploys list" in lowered or "render logs" in lowered:
        return True
    if "render deploys create" in lowered:
        return "--confirm" in lowered and " production " not in lowered
    return False


def render_readiness(
    store: Store,
    *,
    target: str = "render_backend_api",
    env: Mapping[str, str] | None = None,
) -> dict[str, object]:
    env_map = env if env is not None else os.environ
    credential = render_credential_status(env=env_map, store=store, target=target)
    plan = create_render_deployment_plan(target=target, environment="staging", env=env_map)
    checks = run_deployment_checks(store, target=target, run_heavy=False)
    decision = evaluate_deployment_policy(store, plan, checks)
    if credential.human_task_required:
        _enqueue_deployment_setup_notifications(store)
    record = save_deployment_record(store, plan=plan, checks=checks, state=decision.state if decision.allowed else plan.state)
    return {
        "summary": "Render readiness evaluated without triggering a live deploy.",
        "credential_status": credential_status_to_dict(credential),
        "deployment": record.deployment_id,
        "policy": decision.__dict__,
        "executed": False,
    }


def _command_plan(target: str, environment: str) -> tuple[str, ...]:
    if target == "render_postgres_future":
        return ("render blueprints validate render.yaml",)
    if environment == "production":
        return ("render deploys create SERVICE_ID --wait --confirm",)
    return ("POST https://api.render.com/v1/services/SERVICE_ID/deploys",)


def _create_render_human_task(store: Store, reason: str, *, target: str) -> None:
    existing = [task for task in store.list_human_tasks(status="pending") if "Render" in task.title and target in (task.private_details_redacted or "")]
    if existing:
        return
    store.create_human_task(
        requested_by_agent_id="forge",
        title="Render deployment access",
        plain_english_request="Provide Render service access for safe backend deployment planning.",
        reason=reason,
        priority="medium",
        risk_level="medium",
        public_summary="Backend deployment access is pending.",
        private_details=f"Target: {target}. Expected unblock result: Forge can prepare audited Render deployment plans.",
    )


def _create_render_setup_human_tasks(store: Store, status: DeploymentCredentialStatus, *, target: str) -> None:
    existing_titles = {task.title for task in store.list_human_tasks(status="pending")}
    for requirement in status.missing_requirements:
        title = _requirement_title(requirement, provider="Render")
        if title in existing_titles:
            continue
        store.create_human_task(
            requested_by_agent_id="forge",
            title=title,
            plain_english_request=requirement,
            reason="Backend deployment readiness needs this setup before TSF can validate Render operations.",
            priority="medium",
            risk_level="medium",
            public_summary="Backend deployment setup is pending.",
            private_details=(
                f"Related deployment target: {target}. "
                "Expected unblock condition: Render readiness can be validated without exposing credentials."
            ),
        )


def _enqueue_deployment_setup_notifications(store: Store) -> None:
    existing_bodies = "\n".join(row["body"] for row in store.connection.execute("SELECT body FROM notification_queue").fetchall())
    for task in store.list_human_tasks(status="pending"):
        if "deployment" not in f"{task.title} {task.public_summary}".lower():
            continue
        if task.human_task_id in existing_bodies:
            continue
        enqueue_notification(
            store,
            notification_type="human_task",
            body=(
                f"HUMAN TASK - {task.human_task_id}\n\n"
                f"Requested by: Forge\nNeed: {task.plain_english_request}\nReason: {task.reason}\n"
                f"Priority: {task.priority}\nRisk: {task.risk_level}\nPublic note: {task.public_summary}\n\n"
                f"Reply:\n/done {task.human_task_id}\n/blocked {task.human_task_id}\n/note {task.human_task_id} <message>"
            ),
            dry_run=True,
        )


def _run(command: list[str], cwd: Path | None, env: Mapping[str, str] | None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=True, timeout=240, check=False)


def _safe_env(env: Mapping[str, str]) -> dict[str, str]:
    safe = {key: value for key, value in env.items() if key not in {"TSF_RENDER_API_KEY", "RENDER_API_KEY"}}
    api_key = _render_api_key(env)
    if api_key:
        safe["RENDER_API_KEY"] = api_key
    return safe


def _render_deploy_method(env: Mapping[str, str]) -> str:
    return (env.get("TSF_RENDER_DEPLOY_METHOD") or "api").strip().lower()


def _render_api_key(env: Mapping[str, str]) -> str:
    return (env.get("TSF_RENDER_API_KEY") or env.get("RENDER_API_KEY") or "").strip()


def _render_service_id(env: Mapping[str, str], target: str) -> str:
    if target == "render_scheduler_worker":
        return (env.get("TSF_RENDER_SCHEDULER_SERVICE_ID") or env.get("TSF_RENDER_WORKER_SERVICE_ID") or "").strip()
    if target == "render_postgres_future":
        return (env.get("TSF_RENDER_POSTGRES_ID") or "").strip()
    return (env.get("TSF_RENDER_API_SERVICE_ID") or "").strip()


def _render_version_redacted() -> str | None:
    try:
        completed = subprocess.run(["render", "--version"], text=True, capture_output=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return redact_auth_text((completed.stdout or completed.stderr).strip())[:120]


def _render_live_gate(env: Mapping[str, str], status: DeploymentCredentialStatus, *, environment: str) -> tuple[bool, str]:
    if environment == "production":
        return False, "Render production deployment is blocked in this phase."
    if _render_deploy_method(env) not in {"api", "cli"}:
        return False, "Render deploy method must be api or cli."
    if not _bool(env.get("TSF_RENDER_ENABLED"), default=False):
        return False, "Render live deploy is disabled."
    if not _bool(env.get("TSF_RENDER_DEPLOY_ENABLED"), default=False):
        return False, "Render deploy requires explicit staging enablement."
    if status.human_task_required:
        return False, "Render deployment setup is incomplete."
    return True, "Render staging live gate passed."


def _post_render_deploy(env: Mapping[str, str], service_id: str) -> dict[str, object]:
    body: dict[str, object] = {"clearCache": env.get("TSF_RENDER_CLEAR_CACHE", "do_not_clear")}
    commit_id = env.get("TSF_RENDER_DEPLOY_COMMIT_ID", "").strip()
    if commit_id:
        body["commitId"] = commit_id
    request = urllib.request.Request(
        f"https://api.render.com/v1/services/{service_id}/deploys",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {_render_api_key(env)}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(redact_auth_text(f"Render deploy API failed with HTTP {exc.code}: {detail}")) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(redact_auth_text(f"Render deploy API failed: {exc.reason}")) from exc
    return json.loads(payload) if payload else {}


def _render_deploy_id(payload: Mapping[str, object]) -> str | None:
    value = payload.get("id")
    if isinstance(value, str):
        return value
    deploy = payload.get("deploy")
    if isinstance(deploy, Mapping):
        nested = deploy.get("id")
        if isinstance(nested, str):
            return nested
    return None


def _deployed_state(environment: str) -> str:
    return "staging_deployed" if environment == "staging" else "preview_deployed"


def _requirement_title(requirement: str, *, provider: str) -> str:
    lowered = requirement.lower()
    if "cli" in lowered:
        return f"Install {provider} CLI"
    if "api key" in lowered or "access" in lowered:
        return f"Configure {provider} access"
    if "backend api service" in lowered:
        return "Provide Render backend API service ID"
    if "service id" in lowered:
        return f"Provide {provider} service ID"
    if "deploy mode" in lowered:
        return "Confirm Render deploy mode"
    if "production" in lowered:
        return "Confirm Render production remains blocked"
    if "render.yaml" in lowered:
        return "Confirm Render blueprint"
    return f"Complete {provider} deployment setup"


def _bool(value: str | None, *, default: bool) -> bool:
    if value in {None, ""}:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}
