"""Safe Vercel deployment adapter for the public progress frontend."""

from __future__ import annotations

import os
import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping

from synthetic_firm.deployment import (
    DeploymentCredentialStatus,
    DeploymentCheckResult,
    DeploymentHealthCheck,
    DeploymentPlan,
    DeploymentRollbackPlan,
    credential_status_to_dict,
    create_deployment_plan,
    save_credential_status_record,
    save_deployment_record,
)
from synthetic_firm.deployment_checks import run_deployment_checks
from synthetic_firm.deployment_health import run_vercel_preview_health_check
from synthetic_firm.deployment_policy import evaluate_deployment_policy, load_deployment_policy, sentinel_review_deployment_plan
from synthetic_firm.notification_queue import enqueue_notification
from synthetic_firm.provider_auth_redaction import redact_auth_text
from synthetic_firm.store import Store
from synthetic_firm.time_utils import utc_iso

CommandRunner = Callable[[list[str], Path | None, Mapping[str, str] | None], subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class VercelStatus:
    enabled: bool
    cli_available: bool
    token_present: bool
    project_path: str
    safe_summary: str


def vercel_status(env: Mapping[str, str] | None = None) -> dict[str, object]:
    env_map = env if env is not None else os.environ
    credential = vercel_credential_status(env=env_map)
    enabled = _bool(env_map.get("TSF_VERCEL_ENABLED"), default=False)
    project_path = env_map.get("TSF_VERCEL_PROJECT_PATH", "apps/control-room")
    status = VercelStatus(
        enabled=enabled,
        cli_available=credential.cli_available,
        token_present=credential.credential_present,
        project_path=project_path,
        safe_summary=credential.safe_summary,
    )
    payload = status.__dict__.copy()
    payload["credential_status"] = credential_status_to_dict(credential)
    return payload


def vercel_credential_status(
    *,
    env: Mapping[str, str] | None = None,
    store: Store | None = None,
) -> DeploymentCredentialStatus:
    env_map = env if env is not None else os.environ
    project_path = Path(env_map.get("TSF_VERCEL_PROJECT_PATH", "apps/control-room"))
    enabled = _bool(env_map.get("TSF_VERCEL_ENABLED"), default=False)
    cli_path = _vercel_cli_path(project_path)
    credential = _vercel_token(env_map)
    linked = _project_linked(project_path, env_map)
    target_configured = project_path.exists()
    missing: list[str] = []
    if not cli_path:
        missing.append("Install Vercel CLI in the TSF runtime environment.")
    missing.extend(_project_validation_missing(project_path))
    if not credential:
        missing.extend(
            (
                "Create or rotate Vercel deployment access in the provider dashboard.",
                "Set Vercel deployment access as a provider environment variable in the runtime environment.",
            )
        )
    if not target_configured:
        missing.append("Restore or configure the frontend project path.")
    elif not linked:
        missing.append("Link the Vercel project for apps/control-room.")
    preview_enabled = _bool(env_map.get("TSF_VERCEL_PREVIEW_DEPLOY_ENABLED"), default=False)
    if enabled and not preview_enabled:
        missing.append("Confirm Vercel preview deployments are allowed for the public Progress Window.")
    summary = "Vercel preview deployment access is ready." if enabled and not missing else "Vercel preview deployment setup is pending."
    status = DeploymentCredentialStatus(
        provider="vercel",
        enabled=enabled,
        cli_available=bool(cli_path),
        cli_version_redacted=_vercel_version_redacted() if cli_path else None,
        credential_present=bool(credential),
        credential_source="env" if credential else "missing",
        project_linked=linked,
        target_configured=target_configured,
        safe_summary=summary if enabled else "Vercel adapter is disabled by default.",
        missing_requirements=tuple(missing),
        human_task_required=bool(missing),
        last_checked_at=utc_iso(),
    )
    if store is not None and status.human_task_required:
        _create_vercel_setup_human_tasks(store, status)
    if store is not None:
        check_id = save_credential_status_record(store, status)
        store.append_audit(
            actor_type="orchestrator",
            actor_id="deployment_credentials",
            action="deployment_credential_status",
            target_type="deployment_provider",
            target_id="vercel",
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


def create_vercel_deployment_plan(
    *,
    environment: str = "preview",
    env: Mapping[str, str] | None = None,
) -> DeploymentPlan:
    env_map = env if env is not None else os.environ
    project_path = Path(env_map.get("TSF_VERCEL_PROJECT_PATH", "apps/control-room"))
    if environment == "production":
        command = ("cd apps/control-room && vercel deploy --prod",)
        state = "production_candidate"
        risk = "high"
    else:
        command = ("cd apps/control-room && vercel deploy --yes --target preview",)
        state = "validation_required"
        risk = "medium"
    blocked = None
    if not _vercel_token(env_map):
        blocked = "Vercel project access is missing."
        state = "production_blocked" if environment == "production" else "validation_required"
    if not project_path.exists():
        blocked = f"Vercel project path is missing: {project_path}"
        state = "validation_failed"
    elif _project_validation_missing(project_path):
        blocked = "Vercel frontend project validation is incomplete."
        state = "validation_failed"
    return create_deployment_plan(
        target="vercel_frontend",
        environment=environment,
        command_plan=command,
        checks_required=(
            "frontend typecheck",
            "frontend build",
            "root frontend build",
            "brand guard",
            "audit verification",
            "Sentinel review",
        ),
        risk_level=risk,
        rollback_plan=DeploymentRollbackPlan(
            steps=("Use Vercel dashboard or CLI to promote a previous known-good deployment.",),
            summary="Rollback uses a previous Vercel deployment; no domain changes are made in this phase.",
        ),
        health_check=DeploymentHealthCheck(
            checks=("Fetch public site", "Verify read-only public snapshot renders", "Verify no mutation controls"),
            summary="Frontend health checks verify read-only public progress visibility.",
        ),
        sentinel_review="Sentinel review required: frontend must remain read-only and secret-free.",
        public_summary="Frontend deployment readiness for the public Progress Window.",
        state=state,
        blocked_reason=blocked,
    )


def deploy_vercel_preview(
    store: Store,
    *,
    dry_run: bool = True,
    env: Mapping[str, str] | None = None,
    runner: CommandRunner | None = None,
) -> dict[str, object]:
    env_map = env if env is not None else os.environ
    credential_status = vercel_credential_status(env=env_map, store=store)
    plan = create_vercel_deployment_plan(environment="preview", env=env_map)
    checks = run_deployment_checks(store, target="vercel_frontend", run_heavy=False)
    sentinel = sentinel_review_deployment_plan(plan, checks)
    decision = evaluate_deployment_policy(store, plan, checks)
    if plan.blocked_reason:
        _create_vercel_human_task(store, plan.blocked_reason)
    if credential_status.human_task_required:
        _enqueue_deployment_setup_notifications(store)
    if credential_status.human_task_required:
        state = "validation_required"
    else:
        state = decision.state if decision.allowed and sentinel.allowed else (plan.state if plan.blocked_reason else "validation_failed")
    live_gate = _preview_live_gate(env_map, credential_status)
    if dry_run or not live_gate[0] or load_deployment_policy(env_map).dry_run or not decision.allowed or not sentinel.allowed or plan.blocked_reason:
        if not dry_run and not live_gate[0]:
            store.append_audit(
                actor_type="orchestrator",
                actor_id="vercel_adapter",
                action="deployment_preview_live_block",
                target_type="deployment_provider",
                target_id="vercel",
                risk_level="medium",
                summary=live_gate[1],
            )
        record = save_deployment_record(store, plan=plan, checks=checks, state=state)
        return {
            "dry_run": True,
            "executed": False,
            "summary": "Vercel preview deployment planned in dry-run mode.",
            "deployment": record.deployment_id,
            "policy": decision.__dict__,
            "sentinel": sentinel.__dict__,
        }
    runner = runner or _run
    command = ["vercel", "deploy", "--yes", "--target", "preview"]
    store.append_audit(
        actor_type="orchestrator",
        actor_id="vercel_adapter",
        action="deployment_preview_started",
        target_type="deployment_provider",
        target_id="vercel",
        risk_level="medium",
        summary="Vercel preview deployment started.",
    )
    enqueue_notification(
        store,
        notification_type="task_summary",
        body="Frontend preview deployment started. TSF will report the safe preview result after validation.",
        dry_run=True,
    )
    completed = runner(command, Path(env_map.get("TSF_VERCEL_PROJECT_PATH", "apps/control-room")), _safe_env(env_map))
    output = _redact_vercel_output(completed.stdout + completed.stderr, env_map)
    preview_url = _extract_vercel_url(output)
    production_target = _looks_like_production_target(output)
    if production_target:
        health = DeploymentCheckResult("preview health check", False, "Vercel returned a production target for a preview command.")
    else:
        health = (
            run_vercel_preview_health_check(preview_url, env=env_map)
            if completed.returncode == 0 and preview_url
            else DeploymentCheckResult("preview health check", False, "Preview URL was not available.")
        )
    store.append_audit(
        actor_type="orchestrator",
        actor_id="deployment_health",
        action="deployment_health_check",
        target_type="deployment_preview",
        target_id=preview_url if health.passed else "missing",
        risk_level="low" if health.passed else "medium",
        summary=health.summary,
        metadata={"passed": health.passed, "output": health.output_redacted},
    )
    checks = checks + (health,)
    live_plan = create_deployment_plan(
        target="vercel_frontend",
        environment="preview",
        command_plan=("cd apps/control-room && vercel deploy",),
        checks_required=plan.checks_required,
        risk_level="medium",
        rollback_plan=plan.rollback_plan,
        health_check=plan.health_check,
        sentinel_review=plan.sentinel_review,
        public_summary="Frontend preview deployment completed.",
        state="preview_deployed" if completed.returncode == 0 and health.passed else ("health_check_failed" if completed.returncode == 0 else "failed"),
        blocked_reason=None if completed.returncode == 0 and health.passed else ("Vercel preview health check failed." if completed.returncode == 0 else "Vercel preview deployment failed."),
        preview_url=preview_url if health.passed else None,
    )
    record = save_deployment_record(store, plan=live_plan, checks=checks, state=live_plan.state)
    enqueue_notification(
        store,
        notification_type="task_summary",
        body=(
            f"Frontend preview deployed: {preview_url}"
            if live_plan.state == "preview_deployed"
            else "Frontend preview deployment did not pass health checks."
        ),
        dry_run=True,
    )
    result: dict[str, object] = {
        "dry_run": False,
        "executed": completed.returncode == 0 and health.passed,
        "deployment": record.deployment_id,
        "preview_url": preview_url,
        "health": health.__dict__,
    }
    if not result["executed"]:
        result["return_code"] = completed.returncode
        result["output_redacted"] = output[:2000]
    return result


def validate_vercel_command(command: str) -> bool:
    lowered = f" {command.lower()} "
    if "vercel deploy --prod" in lowered:
        return True
    if "project delete" in lowered or " teams " in lowered or " account " in lowered:
        return False
    if "vercel deploy" in lowered and not any(blocked in lowered for blocked in (" env ", " domains ", " alias ", " delete", " remove", " rm ")):
        return True
    return lowered.strip() == "vercel --version"


def _create_vercel_human_task(store: Store, reason: str) -> None:
    existing = [task for task in store.list_human_tasks(status="pending") if "Vercel" in task.title]
    if existing:
        return
    store.create_human_task(
        requested_by_agent_id="forge",
        title="Vercel deployment access",
        plain_english_request="Provide Vercel project access for safe frontend preview deployments.",
        reason=reason,
        priority="medium",
        risk_level="medium",
        public_summary="Frontend deployment access is pending.",
        private_details="Expected unblock result: Forge can prepare audited preview deployment plans.",
    )


def _create_vercel_setup_human_tasks(store: Store, status: DeploymentCredentialStatus) -> None:
    existing_titles = {task.title for task in store.list_human_tasks(status="pending")}
    for requirement in status.missing_requirements:
        title = _requirement_title(requirement, provider="Vercel")
        if title in existing_titles:
            continue
        store.create_human_task(
            requested_by_agent_id="forge",
            title=title,
            plain_english_request=requirement,
            reason="Frontend preview deployment needs this setup before TSF can safely deploy.",
            priority="medium",
            risk_level="medium",
            public_summary="Frontend deployment setup is pending.",
            private_details=(
                "Related deployment target: vercel_frontend. "
                "Expected unblock condition: Vercel preview deployment readiness can be validated without exposing credentials."
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
    return subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=True, timeout=300, check=False)


def _safe_env(env: Mapping[str, str]) -> dict[str, str]:
    safe = {key: value for key, value in env.items() if key not in {"TSF_VERCEL_TOKEN", "VERCEL_TOKEN"}}
    token = _vercel_token(env)
    if token:
        safe["VERCEL_TOKEN"] = token
    project_path = Path(env.get("TSF_VERCEL_PROJECT_PATH", "apps/control-room"))
    if not project_path.is_absolute():
        project_path = Path.cwd() / project_path
    local_bin = project_path / "node_modules" / ".bin"
    if local_bin.exists():
        safe["PATH"] = str(local_bin) + os.pathsep + safe.get("PATH", os.environ.get("PATH", ""))
    return safe


def _extract_vercel_url(output: str) -> str | None:
    for match in re.finditer(r"https://[^\s\"'<>\\]+", output):
        candidate = match.group(0).strip().rstrip(".,)")
        if ".vercel.app" in candidate and "token" not in candidate.lower():
            return candidate
    return None


def _redact_vercel_output(output: str, env: Mapping[str, str]) -> str:
    redacted = redact_auth_text(output)
    token = _vercel_token(env)
    if token:
        redacted = redacted.replace(token, "[REDACTED]")
    return redacted


def _looks_like_production_target(output: str) -> bool:
    lowered = output.lower()
    return bool(re.search(r'"target"\s*:\s*"production"', lowered)) or "▲ production" in lowered or "production  https://" in lowered


def _vercel_token(env: Mapping[str, str]) -> str:
    return (env.get("TSF_VERCEL_TOKEN") or env.get("VERCEL_TOKEN") or "").strip()


def _vercel_cli_path(project_path: Path | None = None) -> str | None:
    candidates: list[Path] = []
    if project_path is not None:
        candidates.append(project_path / "node_modules" / ".bin" / "vercel")
    candidates.append(Path("apps/control-room/node_modules/.bin/vercel"))
    for candidate in candidates:
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)
    return shutil.which("vercel")


def _vercel_version_redacted(project_path: Path | None = None) -> str | None:
    cli_path = _vercel_cli_path(project_path)
    if not cli_path:
        return None
    try:
        completed = subprocess.run([cli_path, "--version"], text=True, capture_output=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return redact_auth_text((completed.stdout or completed.stderr).strip())[:120]


def _project_linked(project_path: Path, env: Mapping[str, str]) -> bool:
    if (project_path / ".vercel" / "project.json").exists():
        return True
    return bool(env.get("TSF_VERCEL_PROJECT_ID", "").strip() and env.get("TSF_VERCEL_ORG_ID", "").strip())


def _project_validation_missing(project_path: Path) -> list[str]:
    missing: list[str] = []
    if not project_path.exists():
        return ["Restore or configure the frontend project path."]
    package_path = project_path / "package.json"
    if not package_path.exists():
        return ["Restore the frontend package.json file."]
    try:
        package = json.loads(package_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ["Repair the frontend package.json file."]
    scripts = package.get("scripts") or {}
    if "build" not in scripts:
        missing.append("Restore the frontend build script.")
    if "typecheck" not in scripts:
        missing.append("Restore the frontend typecheck script.")
    return missing


def _preview_live_gate(env: Mapping[str, str], status: DeploymentCredentialStatus) -> tuple[bool, str]:
    if not _bool(env.get("TSF_VERCEL_ENABLED"), default=False):
        return False, "Vercel live preview deployment is disabled."
    if not _bool(env.get("TSF_VERCEL_PREVIEW_DEPLOY_ENABLED"), default=False):
        return False, "Vercel preview deployment requires explicit enablement."
    if _bool(env.get("TSF_VERCEL_PRODUCTION_DEPLOY_ENABLED"), default=False):
        return False, "Production deployment enablement is ignored in this preview-only phase."
    if not status.cli_available:
        return False, "Vercel CLI is unavailable."
    if not status.credential_present:
        return False, "Vercel access is missing."
    if status.human_task_required:
        return False, "Vercel project setup is incomplete."
    return True, "Vercel preview live gate passed."


def _requirement_title(requirement: str, *, provider: str) -> str:
    lowered = requirement.lower()
    if "cli" in lowered:
        return f"Install {provider} CLI"
    if "token" in lowered or "access" in lowered:
        return f"Configure {provider} access"
    if "production" in lowered:
        return f"Confirm {provider} production remains blocked"
    if "preview" in lowered:
        return f"Confirm {provider} preview policy"
    if "link" in lowered:
        return f"Link {provider} project"
    return f"Complete {provider} deployment setup"


def _bool(value: str | None, *, default: bool) -> bool:
    if value in {None, ""}:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}
