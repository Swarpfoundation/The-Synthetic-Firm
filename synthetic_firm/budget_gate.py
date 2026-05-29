"""Infrastructure budget gates for deployments and scheduler decisions."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from uuid import uuid4

from synthetic_firm.cost_budget import load_infrastructure_budget_config
from synthetic_firm.cost_ledger import create_budget_confirmation_tasks, monthly_budget_state
from synthetic_firm.provider_auth_redaction import redact_auth_text
from synthetic_firm.store import Store
from synthetic_firm.time_utils import utc_iso

PAID_ACTIONS = {
    "vercel_preview_deploy": "Vercel preview deployment may consume frontend hosting/build resources.",
    "render_readiness": "Render backend readiness depends on paid or usage-based infrastructure.",
    "render_deploy": "Render deploy may consume backend/worker hosting resources.",
    "scheduler_cron_enablement": "Scheduler cron introduces recurring runtime infrastructure.",
    "postgres_storage_enablement": "Durable Postgres storage introduces recurring database infrastructure.",
    "production_deploy": "Production deployment may increase infrastructure cost and remains separately blocked.",
}


@dataclass(frozen=True)
class BudgetGateDecision:
    allowed: bool
    status: str
    reason: str
    action_name: str
    known_monthly_burn_eur: float
    projected_monthly_burn_eur: float | None
    unknown_cost_count: int
    human_task_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def check_budget_gate(
    store: Store,
    action_name: str,
    *,
    new_recurring_cost: bool = False,
    unknown_cost_possible: bool = False,
    create_tasks: bool = True,
) -> BudgetGateDecision:
    config = load_infrastructure_budget_config()
    state = monthly_budget_state(store, config=config)
    created: tuple[str, ...] = ()
    reason = state.summary
    allowed = True
    if state.known_monthly_burn_eur >= config.hard_stop_eur:
        allowed = False
        reason = "Infrastructure hard stop reached; new paid actions are blocked."
    elif unknown_cost_possible and config.unknown_cost_policy == "block":
        allowed = False
        reason = f"Unknown infrastructure cost blocks {action_name} until founder confirms actual monthly cost."
    elif new_recurring_cost and config.new_paid_resource_policy == "human_task_required":
        allowed = False
        reason = f"New recurring infrastructure cost for {action_name} requires founder HumanTask approval."
    if (not allowed or state.unknown_cost_count) and create_tasks:
        created = tuple(create_budget_confirmation_tasks(store))
    decision = BudgetGateDecision(
        allowed=allowed,
        status=state.status,
        reason=redact_auth_text(reason),
        action_name=action_name,
        known_monthly_burn_eur=state.known_monthly_burn_eur,
        projected_monthly_burn_eur=state.projected_monthly_burn_eur,
        unknown_cost_count=state.unknown_cost_count,
        human_task_ids=created,
    )
    store.append_audit(
        actor_type="orchestrator",
        actor_id="budget_gate",
        action="infrastructure_budget_gate",
        target_type="budget_action",
        target_id=action_name,
        risk_level="medium" if not allowed or state.status in {"high", "critical", "blocked"} else "low",
        summary=decision.reason,
        metadata={
            "allowed": decision.allowed,
            "status": decision.status,
            "known_monthly_burn_eur": decision.known_monthly_burn_eur,
            "unknown_cost_count": decision.unknown_cost_count,
        },
    )
    store.connection.execute(
        "INSERT INTO cost_decisions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            f"cdec_{uuid4().hex[:12]}",
            action_name,
            int(decision.allowed),
            decision.status,
            decision.reason,
            decision.known_monthly_burn_eur,
            decision.projected_monthly_burn_eur,
            decision.unknown_cost_count,
            utc_iso(),
        ),
    )
    store.connection.commit()
    return decision


def safe_budget_context(store: Store) -> dict[str, object]:
    state = monthly_budget_state(store)
    return {
        "monthly_infrastructure_budget_eur": state.monthly_budget_eur,
        "target_monthly_infrastructure_eur": state.target_monthly_eur,
        "known_monthly_burn_eur": state.known_monthly_burn_eur,
        "projected_monthly_burn_eur": state.projected_monthly_burn_eur,
        "unknown_cost_count": state.unknown_cost_count,
        "unknown_recurring_count": state.unknown_recurring_count,
        "status": state.status,
        "model_api_budget_included": state.model_api_budget_included,
        "policy": "Unknown infrastructure cost blocks paid actions; new recurring paid services require HumanTask approval.",
    }
