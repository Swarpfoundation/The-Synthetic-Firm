"""Deployment safety policy for The Synthetic Firm."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

from synthetic_firm.deployment import DeploymentCheckResult, DeploymentPlan, DEPLOYMENT_TARGETS
from synthetic_firm.provider_auth_redaction import redact_auth_text
from synthetic_firm.store import Store
from synthetic_firm.workday import load_workday_config


class DeploymentPolicyError(ValueError):
    """Raised when deployment policy fails closed."""


@dataclass(frozen=True)
class DeploymentPolicy:
    dry_run: bool
    autonomous_preview: bool
    autonomous_production: bool
    max_per_day: int
    require_sentinel: bool


@dataclass(frozen=True)
class DeploymentPolicyDecision:
    allowed: bool
    reason: str
    state: str


FORBIDDEN_COMMAND_PARTS = (
    " env ",
    " domains ",
    " alias ",
    " delete",
    " remove",
    " rm ",
    " psql",
    " ssh",
    " services create",
    " services update",
    " billing",
    " secrets",
)


def load_deployment_policy(env: Mapping[str, str] | None = None) -> DeploymentPolicy:
    env_map = env if env is not None else os.environ
    return DeploymentPolicy(
        dry_run=_bool(env_map.get("TSF_DEPLOY_DRY_RUN"), default=True),
        autonomous_preview=_bool(env_map.get("TSF_DEPLOY_AUTONOMOUS_PREVIEW"), default=True),
        autonomous_production=_bool(env_map.get("TSF_DEPLOY_AUTONOMOUS_PRODUCTION"), default=False),
        max_per_day=_int(env_map.get("TSF_DEPLOY_MAX_PER_DAY"), default=3),
        require_sentinel=_bool(env_map.get("TSF_DEPLOY_REQUIRE_SENTINEL"), default=True),
    )


def evaluate_deployment_policy(
    store: Store,
    plan: DeploymentPlan,
    checks: tuple[DeploymentCheckResult, ...],
    *,
    policy: DeploymentPolicy | None = None,
) -> DeploymentPolicyDecision:
    policy = policy or load_deployment_policy()
    if plan.target not in DEPLOYMENT_TARGETS:
        return _decision(False, f"Unknown deployment target: {plan.target}", "failed")
    if plan.blocked_reason:
        return _decision(False, plan.blocked_reason, "production_blocked" if plan.environment == "production" else "validation_required")
    if not _budget_known(store):
        store.append_audit(
            actor_type="orchestrator",
            actor_id="deployment_policy",
            action="deployment_budget_block",
            target_type="deployment",
            target_id=plan.plan_id,
            risk_level="medium",
            summary="Deployment blocked because budget could not be determined.",
        )
        return _decision(False, "Budget could not be determined; deployment failed closed.", "production_blocked")
    if store.runtime_status() in {"paused", "killed"}:
        return _decision(False, f"Runtime is {store.runtime_status()}; deployment blocked.", "production_blocked")
    if _deployment_count_today(store) >= policy.max_per_day:
        return _decision(False, "Daily deployment limit reached.", "production_blocked")
    bad_command = _first_forbidden_command(plan.command_plan)
    if bad_command:
        return _decision(False, f"Forbidden deployment command blocked: {bad_command}", "failed")
    if _contains_secret_like_output(checks):
        return _decision(False, "Secret-like output detected in deployment checks.", "validation_failed")
    failed = [check for check in checks if not check.passed]
    if failed:
        return _decision(False, f"Deployment validation failed: {failed[0].name}.", "validation_failed")
    if policy.require_sentinel and "sentinel" not in plan.sentinel_review.lower():
        return _decision(False, "Sentinel review is required before deployment.", "validation_required")
    if plan.environment == "production":
        if not policy.autonomous_production:
            return _decision(False, "Production deployments are disabled by default.", "production_blocked")
        if not plan.rollback_plan.steps or not plan.health_check.checks:
            return _decision(False, "Production deployment requires rollback and health check plans.", "production_blocked")
        return _decision(True, "Production deployment policy gates passed.", "production_ready")
    if plan.environment == "preview":
        if not policy.autonomous_preview:
            return _decision(False, "Preview deployments are disabled by policy.", "production_blocked")
        return _decision(True, "Preview deployment policy gates passed.", "ready_for_preview")
    return _decision(True, "Deployment validation passed.", "validation_required")


def sentinel_review_deployment_plan(plan: DeploymentPlan, checks: tuple[DeploymentCheckResult, ...]) -> DeploymentPolicyDecision:
    if plan.environment == "production" and (not plan.rollback_plan.steps or not plan.health_check.checks):
        return _decision(False, "Sentinel blocks production deployment without rollback and health checks.", "production_blocked")
    failed = [check for check in checks if not check.passed]
    if failed:
        return _decision(False, f"Sentinel blocks deployment because {failed[0].name} failed.", "validation_failed")
    if _first_forbidden_command(plan.command_plan):
        return _decision(False, "Sentinel blocks forbidden deployment command.", "failed")
    if _contains_secret_like_output(checks):
        return _decision(False, "Sentinel blocks secret-like deployment output.", "validation_failed")
    return _decision(True, "Sentinel reviewed deployment plan and found no policy violations.", plan.state)


def _decision(allowed: bool, reason: str, state: str) -> DeploymentPolicyDecision:
    return DeploymentPolicyDecision(allowed=allowed, reason=redact_auth_text(reason), state=state)


def _budget_known(store: Store) -> bool:
    config = load_workday_config()
    if config.company_daily_budget_usd is None:
        return False
    totals = store.budget_totals()
    return totals["spend"] is not None


def _deployment_count_today(store: Store) -> int:
    row = store.connection.execute(
        """
        SELECT COUNT(*) AS count FROM deployment_records
        WHERE date(created_at) = date('now')
          AND state IN ('preview_deployed', 'production_deployed', 'ready_for_preview', 'production_ready')
        """
    ).fetchone()
    return int(row["count"])


def _first_forbidden_command(commands: tuple[str, ...]) -> str | None:
    for command in commands:
        padded = f" {command.lower()} "
        if any(part in padded for part in FORBIDDEN_COMMAND_PARTS):
            return redact_auth_text(command)
    return None


def _contains_secret_like_output(checks: tuple[DeploymentCheckResult, ...]) -> bool:
    for check in checks:
        text = f"{check.summary}\n{check.output_redacted}".lower()
        if any(marker in text for marker in ("token", "api_key", "secret", "password", "credential")):
            return True
    return False


def _bool(value: str | None, *, default: bool) -> bool:
    if value in {None, ""}:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _int(value: str | None, *, default: int) -> int:
    if value in {None, ""}:
        return default
    parsed = int(str(value))
    if parsed < 1:
        raise DeploymentPolicyError("TSF_DEPLOY_MAX_PER_DAY must be positive")
    return parsed
