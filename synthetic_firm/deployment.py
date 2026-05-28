"""Deployment operations domain model and persistence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from synthetic_firm.provider_auth_redaction import redact_auth_text
from synthetic_firm.store import Store
from synthetic_firm.time_utils import utc_iso

DEPLOYMENT_TARGETS = frozenset(
    {"vercel_frontend", "render_backend_api", "render_scheduler_worker", "render_postgres_future"}
)
DEPLOYMENT_ENVIRONMENTS = frozenset({"local", "preview", "staging", "production"})
DEPLOYMENT_STATES = frozenset(
    {
        "proposed",
        "validation_required",
        "validation_failed",
        "ready_for_preview",
        "preview_deployed",
        "production_candidate",
        "production_blocked",
        "production_ready",
        "production_deployed",
        "health_check_failed",
        "rollback_required",
        "rolled_back",
        "cancelled",
        "failed",
    }
)


class DeploymentError(ValueError):
    """Raised when deployment operations fail closed."""


@dataclass(frozen=True)
class DeploymentTarget:
    target_type: str
    name: str
    project_path: str | None
    public_summary: str


@dataclass(frozen=True)
class DeploymentCheckResult:
    name: str
    passed: bool
    summary: str
    output_redacted: str = ""


@dataclass(frozen=True)
class DeploymentHealthCheck:
    checks: tuple[str, ...]
    summary: str


@dataclass(frozen=True)
class DeploymentRollbackPlan:
    steps: tuple[str, ...]
    summary: str


@dataclass(frozen=True)
class DeploymentPlan:
    plan_id: str
    target: str
    environment: str
    state: str
    command_plan: tuple[str, ...]
    checks_required: tuple[str, ...]
    risk_level: str
    rollback_plan: DeploymentRollbackPlan
    health_check: DeploymentHealthCheck
    sentinel_review: str
    public_summary: str
    blocked_reason: str | None = None
    preview_url: str | None = None


@dataclass(frozen=True)
class DeploymentRequest:
    target: str
    environment: str
    requested_by_agent_id: str = "forge"
    dry_run: bool = True


@dataclass(frozen=True)
class DeploymentRecord:
    deployment_id: str
    target: str
    environment: str
    state: str
    plan: dict[str, Any]
    checks: tuple[DeploymentCheckResult, ...]
    health_check: dict[str, Any]
    rollback_plan: dict[str, Any]
    preview_url: str | None
    public_summary: str
    blocked_reason: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class DeploymentCredentialStatus:
    provider: str
    enabled: bool
    cli_available: bool
    cli_version_redacted: str | None
    credential_present: bool
    credential_source: str
    project_linked: bool
    target_configured: bool
    safe_summary: str
    missing_requirements: tuple[str, ...]
    human_task_required: bool
    last_checked_at: str


def deployment_target(target: str) -> DeploymentTarget:
    _validate_choice(target, DEPLOYMENT_TARGETS, "deployment target")
    if target == "vercel_frontend":
        return DeploymentTarget(
            target_type=target,
            name="Public Progress Window frontend",
            project_path="apps/control-room",
            public_summary="Frontend preview deployment readiness.",
        )
    if target == "render_backend_api":
        return DeploymentTarget(
            target_type=target,
            name="TSF backend public API",
            project_path=None,
            public_summary="Backend API deployment readiness.",
        )
    if target == "render_scheduler_worker":
        return DeploymentTarget(
            target_type=target,
            name="TSF autonomous scheduler worker",
            project_path=None,
            public_summary="Autonomous scheduler worker deployment readiness.",
        )
    return DeploymentTarget(
        target_type=target,
        name="Future managed database",
        project_path=None,
        public_summary="Future durable database migration planning.",
    )


def create_deployment_plan(
    *,
    target: str,
    environment: str,
    command_plan: tuple[str, ...],
    checks_required: tuple[str, ...],
    risk_level: str,
    rollback_plan: DeploymentRollbackPlan,
    health_check: DeploymentHealthCheck,
    sentinel_review: str,
    public_summary: str,
    state: str = "validation_required",
    blocked_reason: str | None = None,
    preview_url: str | None = None,
) -> DeploymentPlan:
    _validate_choice(target, DEPLOYMENT_TARGETS, "deployment target")
    _validate_choice(environment, DEPLOYMENT_ENVIRONMENTS, "deployment environment")
    _validate_choice(state, DEPLOYMENT_STATES, "deployment state")
    return DeploymentPlan(
        plan_id=f"deploy_plan_{uuid4().hex[:12]}",
        target=target,
        environment=environment,
        state=state,
        command_plan=tuple(redact_auth_text(item) for item in command_plan),
        checks_required=checks_required,
        risk_level=risk_level,
        rollback_plan=rollback_plan,
        health_check=health_check,
        sentinel_review=redact_auth_text(sentinel_review),
        public_summary=redact_auth_text(public_summary),
        blocked_reason=redact_auth_text(blocked_reason) if blocked_reason else None,
        preview_url=_safe_preview_url(preview_url),
    )


def deployment_plan_to_dict(plan: DeploymentPlan) -> dict[str, Any]:
    return {
        "planId": plan.plan_id,
        "target": plan.target,
        "environment": plan.environment,
        "state": plan.state,
        "commandPlan": list(plan.command_plan),
        "checksRequired": list(plan.checks_required),
        "riskLevel": plan.risk_level,
        "rollbackPlan": rollback_plan_to_dict(plan.rollback_plan),
        "healthCheck": health_check_to_dict(plan.health_check),
        "sentinelReview": plan.sentinel_review,
        "publicSummary": plan.public_summary,
        "blockedReason": plan.blocked_reason,
        "previewUrl": plan.preview_url,
    }


def check_to_dict(check: DeploymentCheckResult) -> dict[str, Any]:
    return {
        "name": check.name,
        "passed": check.passed,
        "summary": redact_auth_text(check.summary),
        "outputRedacted": redact_auth_text(check.output_redacted),
    }


def rollback_plan_to_dict(plan: DeploymentRollbackPlan) -> dict[str, Any]:
    return {"steps": list(plan.steps), "summary": redact_auth_text(plan.summary)}


def health_check_to_dict(check: DeploymentHealthCheck) -> dict[str, Any]:
    return {"checks": list(check.checks), "summary": redact_auth_text(check.summary)}


def save_deployment_record(
    store: Store,
    *,
    plan: DeploymentPlan,
    checks: tuple[DeploymentCheckResult, ...] = (),
    state: str | None = None,
) -> DeploymentRecord:
    record_id = f"deploy_{uuid4().hex[:12]}"
    created = utc_iso()
    record_state = state or plan.state
    _validate_choice(record_state, DEPLOYMENT_STATES, "deployment state")
    store.connection.execute(
        """
        INSERT INTO deployment_records VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record_id,
            plan.target,
            plan.environment,
            record_state,
            json.dumps(deployment_plan_to_dict(plan), sort_keys=True),
            json.dumps([check_to_dict(check) for check in checks], sort_keys=True),
            json.dumps(health_check_to_dict(plan.health_check), sort_keys=True),
            json.dumps(rollback_plan_to_dict(plan.rollback_plan), sort_keys=True),
            plan.preview_url,
            plan.public_summary,
            plan.blocked_reason,
            created,
            created,
        ),
    )
    store.connection.commit()
    store.append_audit(
        actor_type="orchestrator",
        actor_id="deployment",
        action="deployment_record",
        target_type="deployment",
        target_id=record_id,
        risk_level=plan.risk_level,
        summary=f"Deployment record saved for {plan.target} {plan.environment}.",
        metadata={"state": record_state, "target": plan.target, "environment": plan.environment},
    )
    return get_deployment_record(store, record_id)


def get_deployment_record(store: Store, deployment_id: str) -> DeploymentRecord:
    row = store.connection.execute(
        "SELECT * FROM deployment_records WHERE deployment_id = ?", (deployment_id,)
    ).fetchone()
    if not row:
        raise DeploymentError(f"Deployment record not found: {deployment_id}")
    return _record_from_row(row)


def list_deployment_records(store: Store, *, limit: int = 20) -> list[DeploymentRecord]:
    rows = store.connection.execute(
        "SELECT * FROM deployment_records ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    return [_record_from_row(row) for row in rows]


def deployment_record_to_dict(record: DeploymentRecord, *, public: bool = False) -> dict[str, Any]:
    payload = {
        "deploymentId": record.deployment_id,
        "target": record.target,
        "environment": record.environment,
        "state": record.state,
        "previewUrl": record.preview_url if (not public or record.state == "preview_deployed") else None,
        "publicSummary": record.public_summary,
        "blockedReason": _public_blocked_reason(record.blocked_reason) if public else record.blocked_reason,
        "createdAt": record.created_at,
        "updatedAt": record.updated_at,
    }
    if not public:
        payload.update(
            {
                "plan": record.plan,
                "checks": [check_to_dict(check) for check in record.checks],
                "healthCheck": record.health_check,
                "rollbackPlan": record.rollback_plan,
            }
        )
    return payload


def credential_status_to_dict(status: DeploymentCredentialStatus, *, public: bool = False) -> dict[str, Any]:
    payload = {
        "provider": status.provider,
        "enabled": status.enabled,
        "cliAvailable": status.cli_available,
        "cliVersionRedacted": status.cli_version_redacted,
        "credentialPresent": status.credential_present,
        "credentialSource": status.credential_source,
        "projectLinked": status.project_linked,
        "targetConfigured": status.target_configured,
        "safeSummary": redact_auth_text(status.safe_summary),
        "missingRequirements": tuple(redact_auth_text(item) for item in status.missing_requirements),
        "humanTaskRequired": status.human_task_required,
        "lastCheckedAt": status.last_checked_at,
    }
    if public:
        payload.pop("cliVersionRedacted", None)
        payload["missingRequirements"] = tuple(_public_blocked_reason(item) or "Deployment setup is pending." for item in status.missing_requirements)
    return payload


def save_credential_status_record(store: Store, status: DeploymentCredentialStatus) -> str:
    check_id = f"deploy_cred_{uuid4().hex[:12]}"
    store.connection.execute(
        """
        INSERT INTO deployment_credential_status VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            check_id,
            status.provider,
            int(status.enabled),
            int(status.cli_available),
            status.cli_version_redacted,
            int(status.credential_present),
            status.credential_source,
            int(status.project_linked),
            int(status.target_configured),
            redact_auth_text(status.safe_summary),
            json.dumps([redact_auth_text(item) for item in status.missing_requirements], sort_keys=True),
            int(status.human_task_required),
            status.last_checked_at,
        ),
    )
    store.connection.commit()
    return check_id


def latest_credential_status_records(store: Store) -> dict[str, dict[str, Any]]:
    rows = store.connection.execute(
        """
        SELECT * FROM deployment_credential_status
        WHERE checked_at IN (
            SELECT MAX(checked_at) FROM deployment_credential_status GROUP BY provider
        )
        ORDER BY provider
        """
    ).fetchall()
    return {
        row["provider"]: {
            "provider": row["provider"],
            "enabled": bool(row["enabled"]),
            "cliAvailable": bool(row["cli_available"]),
            "credentialPresent": bool(row["credential_present"]),
            "credentialSource": row["credential_source"],
            "projectLinked": bool(row["project_linked"]),
            "targetConfigured": bool(row["target_configured"]),
            "safeSummary": redact_auth_text(row["safe_summary"]),
            "missingRequirements": tuple(
                _public_blocked_reason(item) or "Deployment setup is pending."
                for item in json.loads(row["missing_requirements_json"])
            ),
            "humanTaskRequired": bool(row["human_task_required"]),
            "lastCheckedAt": row["checked_at"],
        }
        for row in rows
    }


def _record_from_row(row: Any) -> DeploymentRecord:
    return DeploymentRecord(
        deployment_id=row["deployment_id"],
        target=row["target"],
        environment=row["environment"],
        state=row["state"],
        plan=json.loads(row["plan_json"]),
        checks=tuple(_check_from_dict(item) for item in json.loads(row["checks_json"])),
        health_check=json.loads(row["health_check_json"]),
        rollback_plan=json.loads(row["rollback_plan_json"]),
        preview_url=_safe_preview_url(row["preview_url"]),
        public_summary=redact_auth_text(row["public_summary"]),
        blocked_reason=redact_auth_text(row["blocked_reason"]) if row["blocked_reason"] else None,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _check_from_dict(value: dict[str, Any]) -> DeploymentCheckResult:
    return DeploymentCheckResult(
        name=str(value["name"]),
        passed=bool(value["passed"]),
        summary=redact_auth_text(str(value["summary"])),
        output_redacted=redact_auth_text(str(value.get("outputRedacted") or "")),
    )


def _validate_choice(value: str, choices: frozenset[str], label: str) -> str:
    normalized = str(value or "").strip()
    if normalized not in choices:
        raise DeploymentError(f"Unknown {label}: {value}")
    return normalized


def _safe_preview_url(value: str | None) -> str | None:
    text = redact_auth_text(value).strip()
    if not text:
        return None
    if "token" in text.lower() or "secret" in text.lower() or "@" in text:
        return None
    if text.startswith("https://") and (text.endswith(".vercel.app") or ".vercel.app/" in text):
        return text
    return None


def _public_blocked_reason(value: str | None) -> str | None:
    if not value:
        return None
    lowered = value.lower()
    if any(marker in lowered for marker in ("token", "api key", "service id", "credential", "secret")):
        return "Deployment access is pending."
    return redact_auth_text(value)
