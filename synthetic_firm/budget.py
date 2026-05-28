"""Budget and loop-limit enforcement for Synthetic Firm tasks."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BudgetPolicy:
    agent_daily_limit_usd: float | None
    task_limit_usd: float | None
    company_daily_limit_usd: float | None
    max_loop_steps: int | None
    max_tool_calls: int | None
    dry_run: bool = False


@dataclass(frozen=True)
class BudgetUsage:
    agent_daily_spend_usd: float | None
    task_spend_usd: float | None
    company_daily_spend_usd: float | None
    loop_steps: int | None
    tool_calls: int | None


@dataclass(frozen=True)
class BudgetDecision:
    allowed: bool
    dry_run: bool
    reason: str


def evaluate_budget(policy: BudgetPolicy, usage: BudgetUsage) -> BudgetDecision:
    checks = (
        ("agent daily budget", policy.agent_daily_limit_usd, usage.agent_daily_spend_usd),
        ("task budget", policy.task_limit_usd, usage.task_spend_usd),
        ("company daily budget", policy.company_daily_limit_usd, usage.company_daily_spend_usd),
        ("loop steps", policy.max_loop_steps, usage.loop_steps),
        ("tool calls", policy.max_tool_calls, usage.tool_calls),
    )
    for label, limit, current in checks:
        if limit is None or current is None:
            return BudgetDecision(False, policy.dry_run, f"Cannot determine {label}; failing closed")
        if current > limit:
            return BudgetDecision(False, policy.dry_run, f"{label} exceeded: {current} > {limit}")
    return BudgetDecision(True, policy.dry_run, "Budget and loop limits are within configured caps")


def budget_status_text(policy: BudgetPolicy, usage: BudgetUsage) -> str:
    decision = evaluate_budget(policy, usage)
    mode = "dry-run" if decision.dry_run else "enforced"
    state = "allowed" if decision.allowed else "blocked"
    return f"Budget status ({mode}): {state}. {decision.reason}."
