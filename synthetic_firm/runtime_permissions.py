"""Runtime permission boundary for tool-like TSF actions."""

from __future__ import annotations

from dataclasses import dataclass

from synthetic_firm.approval_signing import SignedApprovalDecision, verify_signed_decision
from synthetic_firm.budget import BudgetDecision, BudgetPolicy, BudgetUsage, evaluate_budget
from synthetic_firm.runtime_status import validate_status_for_action
from synthetic_firm.store import Store, StoreError

FORBIDDEN_ACTIONS = frozenset(
    {
        "email_send",
        "social_post",
        "investor_outreach_send",
        "vercel_deploy",
        "github_write",
        "github_merge",
        "stripe_connect",
        "domain_purchase",
        "active_worker_create",
        "production_deploy",
        "policy_modify",
        "permission_escalate",
        "secret_read",
        "log_disable",
        "browser_cookie_read",
        "browser_profile_read",
        "chatgpt_web_scrape",
        "oauth_token_print",
        "oauth_token_store_sqlite",
        "telegram_send_token",
        "provider_secret_log",
        "provider_auth_bypass",
    }
)

SAFE_ACTIONS = frozenset(
    {
        "internal_note",
        "create_task",
        "create_message",
        "create_approval_request",
        "generate_daily_report",
        "propose_worker",
        "propose_self_improvement",
        "budget_check",
        "status_check",
        "provider_auth_start",
        "provider_auth_status",
        "provider_auth_list",
        "provider_auth_revoke",
        "provider_route_status",
        "provider_runtime_status",
        "provider_runtime_invoke",
        "deployment_status",
        "deployment_plan",
        "deployment_check",
        "deployment_preview_dry_run",
    }
)


class RuntimePermissionError(ValueError):
    """Raised when runtime policy blocks an action."""


@dataclass(frozen=True)
class RuntimeAction:
    agent_id: str
    task_id: str
    action: str
    external_effect: bool = False
    approval_decision: SignedApprovalDecision | None = None


def evaluate_runtime_action(
    store: Store,
    runtime_action: RuntimeAction,
    budget_policy: BudgetPolicy,
    budget_usage: BudgetUsage,
) -> BudgetDecision:
    try:
        validate_status_for_action(store.runtime_status(), runtime_action.action)
        store.get_task(runtime_action.task_id)
    except (StoreError, ValueError) as exc:
        _deny(store, runtime_action, str(exc))
        raise RuntimePermissionError(str(exc)) from exc

    action = runtime_action.action
    if action in FORBIDDEN_ACTIONS:
        _deny(store, runtime_action, f"Forbidden action blocked: {action}")
        raise RuntimePermissionError(f"Forbidden action blocked: {action}")
    if action not in SAFE_ACTIONS:
        _deny(store, runtime_action, f"Unknown action blocked: {action}")
        raise RuntimePermissionError(f"Unknown action blocked: {action}")

    budget = evaluate_budget(budget_policy, budget_usage)
    store.append_audit(
        actor_type="orchestrator",
        actor_id="runtime_permissions",
        action="budget_check",
        target_type="task",
        target_id=runtime_action.task_id,
        risk_level="low",
        external_effect=runtime_action.external_effect,
        summary=budget.reason,
    )
    if not budget.allowed:
        raise RuntimePermissionError(budget.reason)

    if runtime_action.external_effect:
        decision = runtime_action.approval_decision
        if decision is None or not verify_signed_decision(decision, requested_action=action):
            _deny(store, runtime_action, "External-effect action requires exact signed approval")
            raise RuntimePermissionError("External-effect action requires exact signed approval")
        raise RuntimePermissionError("External-effect execution adapters are disabled in Phase 3")

    return budget


def validate_provider_auth_actor(*, actor_type: str, live: bool) -> None:
    if live and actor_type != "control":
        raise RuntimePermissionError("Provider auth start requires a human/control actor")


def _deny(store: Store, runtime_action: RuntimeAction, reason: str) -> None:
    store.append_audit(
        actor_type="agent",
        actor_id=runtime_action.agent_id,
        action="permission_denial",
        target_type="task",
        target_id=runtime_action.task_id,
        risk_level="high",
        external_effect=runtime_action.external_effect,
        summary=reason,
    )
