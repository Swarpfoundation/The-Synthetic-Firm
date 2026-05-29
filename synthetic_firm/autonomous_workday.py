"""Bounded autonomous workday engine for The Synthetic Firm."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import uuid4

from synthetic_firm.agent_registry import AgentRegistry
from synthetic_firm.agent_reasoning import (
    build_agent_reasoning_request,
    safe_reasoning_summary,
    validate_reasoning_output,
)
from synthetic_firm.budget import BudgetPolicy
from synthetic_firm.code_change import CodeChangeError, create_code_change_proposal
from synthetic_firm.llm_client import complete_agent_reasoning
from synthetic_firm.model_provider import resolve_model_provider
from synthetic_firm.provider_auth_adapters import provider_auth_status
from synthetic_firm.provider_auth_redaction import redact_auth_text
from synthetic_firm.store import Store
from synthetic_firm.time_utils import utc_iso
from synthetic_firm.truthfulness_guard import evaluate_public_claims
from synthetic_firm.workday import load_workday_config

WORKDAY_STATUSES = frozenset({"not_started", "active", "paused", "closing", "closed", "failed"})
PLAN_STATUSES = frozenset({"draft", "active", "review_required", "closed"})
AUTONOMOUS_LIMITS = {
    "max_cycles_per_workday": 6,
    "max_agent_turns_per_cycle": 5,
    "max_tasks_per_cycle": 5,
    "max_messages_per_cycle": 8,
    "max_human_tasks_per_cycle": 3,
}
AGENTS = ("atlas", "scout", "forge", "pulse", "sentinel")
WORKER_AGENTS = ("scout", "forge", "pulse", "sentinel")


class AutonomousWorkdayError(ValueError):
    """Raised when the autonomous workday engine fails closed."""


@dataclass(frozen=True)
class WorkdayState:
    workday_id: str
    date: str
    timezone: str
    status: str
    started_at: str | None
    closed_at: str | None
    atlas_plan_id: str | None
    public_report_id: str | None
    private_report_id: str | None
    cycle_count: int
    last_cycle_at: str | None
    summary: str


@dataclass(frozen=True)
class DailyPlan:
    plan_id: str
    workday_id: str
    created_by_agent_id: str
    objective: str
    priorities: tuple[str, ...]
    agent_assignments: dict[str, str]
    constraints: tuple[str, ...]
    real_data_sources_used: tuple[str, ...]
    assumptions: tuple[str, ...]
    open_questions: tuple[str, ...]
    status: str
    created_at: str


def autonomous_status(store: Store | None = None) -> dict[str, Any]:
    own = store is None
    store = store or Store()
    try:
        workday = get_current_workday(store)
        return {
            "runtime_status": store.runtime_status(),
            "workday": workday_to_dict(workday) if workday else None,
            "summary": "Autonomous workday state loaded." if workday else "No autonomous workday started today.",
        }
    finally:
        if own:
            store.close()


def start_workday(store: Store | None = None, *, dry_run: bool = False) -> WorkdayState:
    own = store is None
    store = store or Store()
    try:
        _ensure_runtime_allows_work(store)
        today = _today()
        existing = _workday_by_date(store, today)
        if existing and existing.status in {"active", "paused", "closing"}:
            current_timezone = load_workday_config().timezone
            if existing.timezone != current_timezone:
                _update_workday(
                    store,
                    existing.workday_id,
                    timezone=current_timezone,
                    summary="Atlas aligned the active workday with current TSF schedule configuration.",
                )
                return get_workday(store, existing.workday_id)
            return existing
        if dry_run:
            return WorkdayState(
                workday_id="dry_run_workday",
                date=today,
                timezone=load_workday_config().timezone,
                status="not_started",
                started_at=None,
                closed_at=None,
                atlas_plan_id=None,
                public_report_id=None,
                private_report_id=None,
                cycle_count=0,
                last_cycle_at=None,
                summary="Dry-run: would start autonomous workday.",
            )
        workday = WorkdayState(
            workday_id=f"wd_{uuid4().hex[:12]}",
            date=today,
            timezone=load_workday_config().timezone,
            status="active",
            started_at=utc_iso(),
            closed_at=None,
            atlas_plan_id=None,
            public_report_id=None,
            private_report_id=None,
            cycle_count=0,
            last_cycle_at=None,
            summary="Atlas started the autonomous workday from persisted TSF state.",
        )
        _insert_workday(store, workday)
        store.append_audit(
            actor_type="agent",
            actor_id="atlas",
            action="workday_start",
            target_type="workday",
            target_id=workday.workday_id,
            summary=workday.summary,
        )
        plan = create_daily_plan(store, workday.workday_id)
        _update_workday(store, workday.workday_id, atlas_plan_id=plan.plan_id)
        return get_workday(store, workday.workday_id)
    finally:
        if own:
            store.close()


def run_cycle(store: Store | None = None, *, dry_run: bool = False) -> dict[str, Any]:
    own = store is None
    store = store or Store()
    try:
        _ensure_runtime_allows_work(store)
        workday = get_current_workday(store) or start_workday(store)
        if workday.cycle_count >= AUTONOMOUS_LIMITS["max_cycles_per_workday"]:
            store.append_audit(
                actor_type="orchestrator",
                actor_id="autonomous_workday",
                action="budget_block",
                target_type="workday",
                target_id=workday.workday_id,
                risk_level="medium",
                summary="Autonomous cycle limit reached; no more cycles will run today.",
            )
            raise AutonomousWorkdayError("Autonomous cycle limit reached for today")
        _ensure_budget_known(store)
        if dry_run:
            return {"summary": "Dry-run: would run one bounded autonomous workday cycle.", "workday": workday_to_dict(workday)}
        results = []
        store.append_audit(
            actor_type="orchestrator",
            actor_id="autonomous_workday",
            action="workday_cycle",
            target_type="workday",
            target_id=workday.workday_id,
            summary="Started one bounded autonomous workday cycle.",
        )
        plan = get_latest_plan(store, workday.workday_id) or create_daily_plan(store, workday.workday_id)
        results.append(assign_agent_tasks(store, workday, plan))
        for agent_id in AGENTS[: AUTONOMOUS_LIMITS["max_agent_turns_per_cycle"]]:
            results.append(run_agent_turn(store, agent_id=agent_id, workday_id=workday.workday_id))
        process_blockers(store, workday.workday_id)
        public_report_id = generate_public_daily_report(store, workday.workday_id)
        private_report_id = generate_private_founder_report(store, workday.workday_id)
        _update_workday(
            store,
            workday.workday_id,
            cycle_count=workday.cycle_count + 1,
            last_cycle_at=utc_iso(),
            public_report_id=public_report_id,
            private_report_id=private_report_id,
            summary="Autonomous cycle completed with real persisted state and no fabricated progress.",
        )
        return {
            "summary": "Autonomous workday cycle completed.",
            "workday": workday_to_dict(get_workday(store, workday.workday_id)),
            "results": results,
        }
    finally:
        if own:
            store.close()


def run_agent_turn(store: Store | None = None, *, agent_id: str, workday_id: str | None = None, dry_run: bool = False):
    own = store is None
    store = store or Store()
    try:
        _ensure_runtime_allows_work(store)
        AgentRegistry.from_file().get(agent_id)
        workday = get_workday(store, workday_id) if workday_id else (get_current_workday(store) or start_workday(store))
        if dry_run:
            return {"agent_id": agent_id, "summary": "Dry-run: would run a bounded agent turn."}
        store.append_audit(
            actor_type="agent",
            actor_id=agent_id,
            action="agent_turn_start",
            target_type="workday",
            target_id=workday.workday_id,
            summary=f"{agent_id} started a bounded autonomous turn.",
        )
        if agent_id == "atlas":
            result = _atlas_turn(store, workday)
        elif agent_id == "scout":
            result = _provider_reasoning_turn(
                store, workday, agent_id="scout"
            ) or _capability_blocked_turn(
                store,
                workday,
                agent_id="scout",
                title="Research capability setup",
                objective="Identify research opportunities once a safe research source or provider is configured.",
                public_summary="Autonomous research capability setup is pending.",
                human_request="Provide or approve a safe research/provider source for Scout.",
                reason="Scout cannot perform external research without an approved provider or source adapter.",
            )
        elif agent_id == "forge":
            result = _forge_turn(store, workday)
        elif agent_id == "pulse":
            result = _provider_reasoning_turn(
                store, workday, agent_id="pulse"
            ) or _capability_blocked_turn(
                store,
                workday,
                agent_id="pulse",
                title="Growth planning without outreach sending",
                objective="Prepare growth planning from existing approved public status only.",
                public_summary="Growth planning is limited until approved offer/CRM data exists.",
                human_request="Confirm approved offer, CRM/source data, or future outreach capability for Pulse.",
                reason="Pulse cannot claim leads or send outreach without approved data and adapters.",
            )
        elif agent_id == "sentinel":
            result = _sentinel_turn(store, workday)
        else:
            raise AutonomousWorkdayError(f"Unsupported agent turn: {agent_id}")
        store.append_audit(
            actor_type="agent",
            actor_id=agent_id,
            action="agent_turn_end",
            target_type="workday",
            target_id=workday.workday_id,
            summary=str(result["summary"]),
        )
        return result
    finally:
        if own:
            store.close()


def create_daily_plan(store: Store, workday_id: str) -> DailyPlan:
    tasks = store.list_tasks()
    messages = store.list_messages()
    human_tasks = store.list_human_tasks()
    founder_messages = store.list_founder_messages()
    open_questions = []
    if not tasks:
        open_questions.append("No persisted company tasks existed at planning time.")
    if not human_tasks:
        open_questions.append("No founder human tasks were pending at planning time.")
    queued_founder_messages = [message for message in founder_messages if message.status in {"received", "queued"}]
    if queued_founder_messages:
        open_questions.append(f"{len(queued_founder_messages)} founder message(s) are queued for Atlas review.")
    plan = DailyPlan(
        plan_id=f"plan_{uuid4().hex[:12]}",
        workday_id=workday_id,
        created_by_agent_id="atlas",
        objective="Run one truthful autonomous workday using persisted TSF state only.",
        priorities=(
            "Keep public progress truthful and evidence-backed.",
            "Unblock provider/capability gaps through HumanTasks instead of pretending.",
            "Produce Atlas public and private reports from persisted state.",
        ),
        agent_assignments={
            "scout": "Find research work only from real configured sources; otherwise block.",
            "forge": "Identify internal build work from the existing repo/runtime state.",
            "pulse": "Plan growth only from approved offers and real data.",
            "sentinel": "Review truthfulness, privacy, budget, and unsupported claims.",
        },
        constraints=(
            "No external business automation.",
            "No fake progress.",
            "No public private details.",
            "No frontend mutations.",
        ),
        real_data_sources_used=(
            f"{len(tasks)} persisted task(s)",
            f"{len(messages)} persisted message(s)",
            f"{len(human_tasks)} persisted human task(s)",
            f"{len(founder_messages)} founder message(s)",
        ),
        assumptions=("Provider-backed autonomous reasoning may be unavailable until auth/runtime is configured.",),
        open_questions=tuple(open_questions),
        status="active",
        created_at=utc_iso(),
    )
    _insert_plan(store, plan)
    store.append_audit(
        actor_type="agent",
        actor_id="atlas",
        action="daily_plan_create",
        target_type="daily_plan",
        target_id=plan.plan_id,
        summary="Atlas created a daily plan from persisted TSF state.",
    )
    return plan


def assign_agent_tasks(store: Store, workday: WorkdayState, plan: DailyPlan) -> dict[str, Any]:
    created = []
    for agent_id, assignment in plan.agent_assignments.items():
        existing = [
            task for task in store.list_tasks() if task.assigned_agent_id == agent_id and task.status not in {"completed", "cancelled", "failed"}
        ]
        if existing:
            continue
        task = store.create_task(
            title=f"{agent_id.title()} autonomous workday task",
            objective=assignment,
            created_by_agent_id="atlas",
            assigned_agent_id=agent_id,
            risk_level="low",
            budget_limit=1.0,
            max_steps=4,
            plain_english_summary=f"Atlas assigned {agent_id} to: {assignment}",
        )
        store.assign_task(task.task_id, agent_id)
        created.append(task.task_id)
    store.append_audit(
        actor_type="agent",
        actor_id="atlas",
        action="task_assignment",
        target_type="workday",
        target_id=workday.workday_id,
        summary=f"Atlas assigned {len(created)} autonomous task(s).",
    )
    return {"summary": f"Atlas assigned {len(created)} task(s).", "created_task_ids": created}


def process_blockers(store: Store, workday_id: str) -> dict[str, Any]:
    blocked = [task for task in store.list_tasks() if task.status == "blocked"]
    store.append_audit(
        actor_type="orchestrator",
        actor_id="autonomous_workday",
        action="blocked_task",
        target_type="workday",
        target_id=workday_id,
        risk_level="medium" if blocked else "low",
        summary=f"Processed blocker review for {len(blocked)} blocked task(s).",
    )
    return {"summary": f"{len(blocked)} blocked task(s) reviewed.", "blocked_count": len(blocked)}


def generate_public_daily_report(store: Store, workday_id: str) -> str:
    tasks = store.list_tasks()
    human_tasks = store.list_human_tasks()
    founder_messages = store.list_founder_messages()
    evidence = _evidence(store)
    completed = [task.plain_english_summary for task in tasks if task.status == "completed"]
    in_progress = [task.plain_english_summary for task in tasks if task.status in {"assigned", "in_progress", "review_required", "approval_required"}]
    blocked = [task.plain_english_summary for task in tasks if task.status == "blocked"]
    human_public = [f"{task.status}: {task.public_summary}" for task in human_tasks]
    reviewed_founder_count = len([message for message in founder_messages if message.status == "reviewed"])
    lines = [
        "The Synthetic Firm - Daily Public Report",
        f"Date: {_today()}",
        "",
        "What happened today:",
        *(_bullets(_agent_progress_lines(tasks)) or ["- No public task activity yet."]),
        "",
        "Completed:",
        *(_bullets(completed) or ["- No completed tasks today."]),
        "",
        "In progress:",
        *(_bullets(in_progress) or ["- No public tasks in progress."]),
        "",
        "Blocked:",
        *(_bullets(blocked) or ["- No public blockers recorded."]),
        "",
        "Human tasks:",
        *(_bullets(human_public) or ["- No public human tasks pending."]),
        "",
        "Founder messages:",
        f"- Atlas reviewed {reviewed_founder_count} founder message(s)." if reviewed_founder_count else "- No founder messages reviewed today.",
        "",
        "Truthfulness:",
        "- Based on real TSF runtime data.",
        "- No mock data.",
        "- No fabricated progress.",
    ]
    report = "\n".join(lines) + "\n"
    truth = evaluate_public_claims(report, evidence)
    if not truth.allowed:
        store.append_audit(
            actor_type="agent",
            actor_id="sentinel",
            action="truthfulness_guard_rejection",
            target_type="workday",
            target_id=workday_id,
            risk_level="high",
            summary=truth.summary,
            metadata={"unsupported_claims": list(truth.unsupported_claims)},
        )
        report = truth.safe_text + "\n"
    store.append_audit(
        actor_type="agent",
        actor_id="sentinel",
        action="sentinel_review",
        target_type="public_daily_report",
        target_id=workday_id,
        summary="Sentinel reviewed the public report for unsupported claims.",
    )
    report_id = store.save_daily_report(report_date=_today(), content=report, telegram_summary=_telegram_summary(report))
    store.append_audit(
        actor_type="agent",
        actor_id="atlas",
        action="public_report_generation",
        target_type="daily_report",
        target_id=report_id,
        summary="Atlas generated a public daily report from persisted TSF state.",
    )
    return report_id


def generate_private_founder_report(store: Store, workday_id: str) -> str:
    human_tasks = store.list_human_tasks()
    blocked = [task for task in store.list_tasks() if task.status == "blocked"]
    founder_messages = store.list_founder_messages()
    lines = [
        "The Synthetic Firm - Private Founder Report",
        f"Date: {_today()}",
        "",
        "Exact human tasks:",
        *(_bullets([f"{task.human_task_id}: {task.plain_english_request}" for task in human_tasks]) or ["- None."]),
        "",
        "Private blockers:",
        *(_bullets([task.plain_english_summary for task in blocked]) or ["- None."]),
        "",
        "Founder messages reviewed by Atlas:",
        *(
            _bullets(
                [
                    f"{message.message_id}: {message.priority} {message.message_type} - {message.content}"
                    for message in founder_messages
                    if message.status == "reviewed"
                ]
            )
            or ["- None."]
        ),
        "",
        "Next founder actions:",
        *(_bullets([task.public_summary for task in human_tasks if task.status == "pending"]) or ["- No founder action pending."]),
    ]
    report = redact_auth_text("\n".join(lines) + "\n")
    report_id = store.save_daily_report(report_date=_today(), content=report, telegram_summary=_telegram_summary(report))
    store.append_audit(
        actor_type="agent",
        actor_id="atlas",
        action="private_report_generation",
        target_type="daily_report",
        target_id=report_id,
        summary="Atlas generated a private founder report without secrets.",
    )
    return report_id


def close_workday(store: Store | None = None, *, dry_run: bool = False) -> WorkdayState:
    own = store is None
    store = store or Store()
    try:
        workday = get_current_workday(store)
        if not workday:
            raise AutonomousWorkdayError("No active workday to close")
        if workday.status not in {"active", "closing", "paused"}:
            raise AutonomousWorkdayError(f"Cannot close workday in status {workday.status}")
        if dry_run:
            return workday
        _update_workday(store, workday.workday_id, status="closed", closed_at=utc_iso(), summary="Workday closed by Atlas.")
        store.append_audit(
            actor_type="agent",
            actor_id="atlas",
            action="workday_close",
            target_type="workday",
            target_id=workday.workday_id,
            summary="Atlas closed the autonomous workday.",
        )
        return get_workday(store, workday.workday_id)
    finally:
        if own:
            store.close()


def list_agent_work(store: Store, agent_id: str | None = None) -> dict[str, Any]:
    tasks = store.list_tasks()
    if agent_id:
        tasks = [task for task in tasks if task.assigned_agent_id == agent_id or task.created_by_agent_id == agent_id]
    return {
        "tasks": [
            {"task_id": task.task_id, "title": task.title, "status": task.status, "assigned_agent_id": task.assigned_agent_id}
            for task in tasks
        ]
    }


def get_current_workday(store: Store) -> WorkdayState | None:
    row = store.connection.execute(
        """
        SELECT * FROM workdays
        WHERE workday_date = ? AND status IN ('active', 'paused', 'closing')
        ORDER BY started_at DESC LIMIT 1
        """,
        (_today(),),
    ).fetchone()
    return _workday_from_row(row) if row else None


def get_workday(store: Store, workday_id: str | None) -> WorkdayState:
    if not workday_id:
        raise AutonomousWorkdayError("workday_id is required")
    row = store.connection.execute("SELECT * FROM workdays WHERE workday_id = ?", (workday_id,)).fetchone()
    if not row:
        raise AutonomousWorkdayError(f"Workday not found: {workday_id}")
    return _workday_from_row(row)


def get_latest_plan(store: Store, workday_id: str) -> DailyPlan | None:
    row = store.connection.execute(
        "SELECT * FROM daily_plans WHERE workday_id = ? ORDER BY created_at DESC LIMIT 1",
        (workday_id,),
    ).fetchone()
    return _plan_from_row(row) if row else None


def workday_to_dict(workday: WorkdayState) -> dict[str, Any]:
    return workday.__dict__.copy()


def plan_to_dict(plan: DailyPlan) -> dict[str, Any]:
    return {
        "plan_id": plan.plan_id,
        "workday_id": plan.workday_id,
        "created_by_agent_id": plan.created_by_agent_id,
        "objective": plan.objective,
        "priorities": list(plan.priorities),
        "agent_assignments": plan.agent_assignments,
        "constraints": list(plan.constraints),
        "real_data_sources_used": list(plan.real_data_sources_used),
        "assumptions": list(plan.assumptions),
        "open_questions": list(plan.open_questions),
        "status": plan.status,
        "created_at": plan.created_at,
    }


def _atlas_turn(store: Store, workday: WorkdayState) -> dict[str, Any]:
    reviewed = store.review_founder_messages(reviewed_by_agent_id="atlas")
    reasoned = _provider_reasoning_turn(store, workday, agent_id="atlas")
    if reasoned:
        return {
            "summary": (
                f"Atlas reviewed {len(reviewed)} founder message(s) and completed bounded "
                f"model reasoning with status {reasoned['status']}."
            )
        }
    store.create_message(
        sender_agent_id="atlas",
        channel="company",
        message_type="manager_update",
        content=(
            "Atlas reviewed persisted TSF state, "
            f"including {len(reviewed)} queued founder message(s), and coordinated bounded autonomous work."
        ),
    )
    return {
        "summary": f"Atlas coordinated the autonomous workday and reviewed {len(reviewed)} founder message(s)."
    }


def _forge_turn(store: Store, workday: WorkdayState) -> dict[str, Any]:
    reasoned = _provider_reasoning_turn(store, workday, agent_id="forge")
    if reasoned:
        return reasoned
    provider = _provider_ready()
    if not provider:
        return _capability_blocked_turn(
            store,
            workday,
            agent_id="forge",
            title="Provider runtime setup for build work",
            objective="Run build reasoning only after a safe provider runtime is available.",
            public_summary="Autonomous provider setup is pending.",
            human_request="Connect Kimi Code or OpenAI Codex provider runtime for Forge.",
            reason="Forge cannot perform provider-backed build reasoning without a connected safe provider runtime.",
        )
    store.create_message(
        sender_agent_id="forge",
        channel="forge",
        message_type="status",
        content=f"Forge has provider route {provider} available for future bounded build work.",
    )
    return {"summary": f"Forge detected provider route {provider}."}


def _sentinel_turn(store: Store, workday: WorkdayState) -> dict[str, Any]:
    reasoned = _provider_reasoning_turn(store, workday, agent_id="sentinel")
    if reasoned:
        return reasoned
    store.create_message(
        sender_agent_id="sentinel",
        channel="company",
        message_type="review",
        content="Sentinel reviewed public-report truthfulness and confirmed unsupported claims must remain blocked.",
    )
    store.append_audit(
        actor_type="agent",
        actor_id="sentinel",
        action="sentinel_review",
        target_type="workday",
        target_id=workday.workday_id,
        summary="Sentinel reviewed workday safety, truthfulness, and privacy boundaries.",
    )
    return {"summary": "Sentinel reviewed safety and truthfulness boundaries."}


def _provider_reasoning_turn(store: Store, workday: WorkdayState, *, agent_id: str) -> dict[str, Any] | None:
    try:
        route = resolve_model_provider()
    except Exception as exc:
        store.append_audit(
            actor_type="agent",
            actor_id=agent_id,
            action="model_unavailable",
            target_type="workday",
            target_id=workday.workday_id,
            risk_level="medium",
            summary=redact_auth_text(str(exc)),
        )
        return None
    if route.provider == "dry-run" or not route.connected:
        return None
    if not _model_budget_allows(store, agent_id=agent_id, workday_id=workday.workday_id):
        return None
    request = build_agent_reasoning_request(store, agent_id=agent_id, workday_id=workday.workday_id)
    response = complete_agent_reasoning(request, store=store)
    if response.status != "success" or not response.structured_output:
        store.append_audit(
            actor_type="agent",
            actor_id=agent_id,
            action="model_reasoning_failure",
            target_type="workday",
            target_id=workday.workday_id,
            risk_level="medium",
            summary=response.error_redacted or response.redacted_debug_summary,
        )
        return None
    validation = validate_reasoning_output(response.structured_output, evidence=_evidence(store))
    if not validation.allowed:
        store.append_audit(
            actor_type="agent",
            actor_id="sentinel",
            action="truthfulness_guard_rejection",
            target_type="workday",
            target_id=workday.workday_id,
            risk_level="high",
            summary=validation.summary,
            metadata={"blocked_reasons": list(validation.blocked_reasons)},
        )
        return None
    _persist_reasoning_output(store, agent_id=agent_id, workday=workday, output=response.structured_output)
    store.append_audit(
        actor_type="agent",
        actor_id=agent_id,
        action="structured_output_accepted",
        target_type="workday",
        target_id=workday.workday_id,
        summary=f"{agent_id} structured model reasoning was accepted.",
        metadata={"provider": response.provider, "model": response.model, "dry_run": response.dry_run},
    )
    return {
        "summary": safe_reasoning_summary(response.structured_output),
        "status": response.status,
        "provider": response.provider,
        "dry_run": response.dry_run,
    }


def _model_budget_allows(store: Store, *, agent_id: str, workday_id: str) -> bool:
    registry = AgentRegistry.from_file()
    profile = registry.get(agent_id)
    company_limit = sum(agent.budget.daily_usd for agent in registry.list())
    agent = store.budget_totals(agent_id=agent_id)
    company = store.budget_totals()
    allowed = float(agent["spend"]) < profile.budget.daily_usd and float(company["spend"]) < company_limit
    store.append_audit(
        actor_type="orchestrator",
        actor_id="model_budget",
        action="budget_check" if allowed else "model_budget_block",
        target_type="workday",
        target_id=workday_id,
        risk_level="low" if allowed else "medium",
        summary="Model reasoning budget check passed." if allowed else "Model reasoning budget check failed closed.",
        metadata={"agent_id": agent_id},
    )
    return allowed


def _persist_reasoning_output(store: Store, *, agent_id: str, workday: WorkdayState, output: dict[str, Any]) -> None:
    store.create_message(
        sender_agent_id=agent_id,
        channel="company",
        message_type="model_reasoning_summary",
        content=safe_reasoning_summary(output),
    )
    for item in output.get("messages_to_agents", [])[:2]:
        if not isinstance(item, dict):
            continue
        recipient = str(item.get("recipient_agent_id") or "").strip().lower()
        content = str(item.get("content") or "").strip()
        if recipient in AGENTS and content:
            store.create_message(
                sender_agent_id=agent_id,
                recipient_agent_id=recipient,
                message_type="model_reasoning_note",
                content=redact_auth_text(content),
            )
    for item in output.get("human_tasks", [])[: AUTONOMOUS_LIMITS["max_human_tasks_per_cycle"]]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "Founder action requested").strip()
        request = str(item.get("plain_english_request") or item.get("request") or "").strip()
        reason = str(item.get("reason") or "A real-world founder action is required.").strip()
        public_summary = str(item.get("public_summary") or "Founder action is pending.").strip()
        if request:
            human_task = store.create_human_task(
                requested_by_agent_id=agent_id,
                title=title,
                plain_english_request=redact_auth_text(request),
                reason=redact_auth_text(reason),
                priority=str(item.get("priority") or "medium"),
                risk_level=str(item.get("risk_level") or "medium"),
                public_summary=redact_auth_text(public_summary),
                private_details=redact_auth_text(str(item.get("private_details") or "")),
            )
            store.append_audit(
                actor_type="agent",
                actor_id=agent_id,
                action="human_task_from_model_reasoning",
                target_type="human_task",
                target_id=human_task.human_task_id,
                risk_level=human_task.risk_level,
                summary=human_task.public_summary,
            )
    if agent_id == "forge":
        _persist_forge_code_proposals(store, workday=workday, output=output)


def _persist_forge_code_proposals(store: Store, *, workday: WorkdayState, output: dict[str, Any]) -> None:
    for item in output.get("proposed_tasks", [])[:2]:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("type") or item.get("kind") or "").strip().lower()
        if kind not in {"code_change", "patch", "repo_patch"}:
            continue
        patch_text = str(item.get("patch_text") or item.get("patch") or "").strip()
        if not patch_text:
            continue
        try:
            proposal = create_code_change_proposal(
                store,
                title=str(item.get("title") or "Forge code-change proposal"),
                summary=str(item.get("summary") or "Forge proposed a bounded code change."),
                rationale=str(item.get("rationale") or "Forge identified repo work from persisted runtime state."),
                patch_text=patch_text,
                created_by_agent_id="forge",
                tests_command=str(item.get("tests_command") or ""),
                public_summary=str(item.get("public_summary") or "Forge proposed a code change for review."),
                private_notes=f"Workday: {workday.workday_id}",
            )
            store.append_audit(
                actor_type="agent",
                actor_id="forge",
                action="code_change_from_model_reasoning",
                target_type="code_change_proposal",
                target_id=proposal.proposal_id,
                risk_level="medium",
                summary=proposal.public_summary,
            )
        except CodeChangeError as exc:
            store.append_audit(
                actor_type="agent",
                actor_id="forge",
                action="code_change_proposal_blocked",
                target_type="workday",
                target_id=workday.workday_id,
                risk_level="medium",
                summary=redact_auth_text(str(exc)),
            )


def _capability_blocked_turn(
    store: Store,
    workday: WorkdayState,
    *,
    agent_id: str,
    title: str,
    objective: str,
    public_summary: str,
    human_request: str,
    reason: str,
) -> dict[str, Any]:
    task = store.create_task(
        title=title,
        objective=objective,
        created_by_agent_id=agent_id,
        assigned_agent_id=agent_id,
        risk_level="medium",
        budget_limit=1.0,
        max_steps=3,
        plain_english_summary=f"{title}: {objective}",
    )
    store.assign_task(task.task_id, agent_id)
    store.mark_blocked(task.task_id, summary=f"{title}: blocked until founder/capability setup is complete.")
    human_task = store.create_human_task(
        requested_by_agent_id=agent_id,
        related_task_id=task.task_id,
        title=title,
        plain_english_request=human_request,
        reason=reason,
        priority="medium",
        risk_level="medium",
        public_summary=public_summary,
        private_details=f"Expected unblock result: {agent_id} can continue bounded autonomous work without fabricating progress.",
    )
    store.append_audit(
        actor_type="agent",
        actor_id=agent_id,
        action="provider_unavailable" if "provider" in title.lower() else "blocked_task",
        target_type="task",
        target_id=task.task_id,
        risk_level="medium",
        summary=public_summary,
    )
    return {
        "summary": f"{agent_id} created blocked task {task.task_id} and HumanTask {human_task.human_task_id}.",
        "task_id": task.task_id,
        "human_task_id": human_task.human_task_id,
    }


def _provider_ready() -> str | None:
    for provider in ("kimi-code", "openai-codex"):
        try:
            status = provider_auth_status(provider)
        except Exception:
            continue
        if status.status == "connected":
            return provider
    return None


def _ensure_runtime_allows_work(store: Store) -> None:
    runtime = store.runtime_status()
    if runtime in {"paused", "killed"}:
        raise AutonomousWorkdayError(f"Runtime is {runtime}; autonomous work is blocked")


def _ensure_budget_known(store: Store) -> None:
    registry = AgentRegistry.from_file()
    company_limit = sum(agent.budget.daily_usd for agent in registry.list())
    totals = store.budget_totals()
    policy = BudgetPolicy(
        agent_daily_limit_usd=registry.get("atlas").budget.daily_usd,
        task_limit_usd=1.0,
        company_daily_limit_usd=company_limit,
        max_loop_steps=AUTONOMOUS_LIMITS["max_cycles_per_workday"],
        max_tool_calls=AUTONOMOUS_LIMITS["max_agent_turns_per_cycle"] * AUTONOMOUS_LIMITS["max_cycles_per_workday"],
        dry_run=False,
    )
    decision = store.evaluate_persisted_budget(agent_id="atlas", task_id="autonomous_workday", policy=policy)
    if not decision.allowed:
        raise AutonomousWorkdayError(decision.reason)
    if totals["spend"] is None:
        raise AutonomousWorkdayError("Budget usage is unavailable")


def _evidence(store: Store) -> list[str]:
    items: list[str] = []
    items.extend(task.plain_english_summary for task in store.list_tasks())
    items.extend(message.content for message in store.list_messages())
    items.extend(task.public_summary for task in store.list_human_tasks())
    rows = store.connection.execute("SELECT summary FROM audit_log ORDER BY sequence_number").fetchall()
    items.extend(row["summary"] for row in rows)
    return items


def _agent_progress_lines(tasks: list[Any]) -> list[str]:
    lines = []
    for agent_id in WORKER_AGENTS:
        active = [task for task in tasks if task.assigned_agent_id == agent_id and task.status not in {"completed", "cancelled", "failed"}]
        if active:
            lines.append(f"{agent_id.title()} worked on {active[0].title}.")
    return lines


def _workday_by_date(store: Store, day: str) -> WorkdayState | None:
    row = store.connection.execute(
        "SELECT * FROM workdays WHERE workday_date = ? ORDER BY started_at DESC LIMIT 1",
        (day,),
    ).fetchone()
    return _workday_from_row(row) if row else None


def _insert_workday(store: Store, workday: WorkdayState) -> None:
    store.connection.execute(
        "INSERT INTO workdays VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            workday.workday_id,
            workday.date,
            workday.timezone,
            workday.status,
            workday.started_at,
            workday.closed_at,
            workday.atlas_plan_id,
            workday.public_report_id,
            workday.private_report_id,
            workday.cycle_count,
            workday.last_cycle_at,
            workday.summary,
        ),
    )
    store.connection.commit()


def _update_workday(store: Store, workday_id: str, **updates: Any) -> None:
    if not updates:
        return
    allowed = {
        "status",
        "closed_at",
        "atlas_plan_id",
        "public_report_id",
        "private_report_id",
        "cycle_count",
        "last_cycle_at",
        "summary",
        "timezone",
    }
    invalid = set(updates) - allowed
    if invalid:
        raise AutonomousWorkdayError(f"Unsupported workday update: {sorted(invalid)}")
    assignments = ", ".join(f"{key} = ?" for key in updates)
    store.connection.execute(
        f"UPDATE workdays SET {assignments} WHERE workday_id = ?",
        (*updates.values(), workday_id),
    )
    store.connection.commit()


def _insert_plan(store: Store, plan: DailyPlan) -> None:
    store.connection.execute(
        "INSERT INTO daily_plans VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            plan.plan_id,
            plan.workday_id,
            plan.created_by_agent_id,
            plan.objective,
            json.dumps(list(plan.priorities), sort_keys=True),
            json.dumps(plan.agent_assignments, sort_keys=True),
            json.dumps(list(plan.constraints), sort_keys=True),
            json.dumps(list(plan.real_data_sources_used), sort_keys=True),
            json.dumps(list(plan.assumptions), sort_keys=True),
            json.dumps(list(plan.open_questions), sort_keys=True),
            plan.status,
            plan.created_at,
        ),
    )
    store.connection.commit()


def _workday_from_row(row: Any) -> WorkdayState:
    return WorkdayState(
        workday_id=row["workday_id"],
        date=row["workday_date"],
        timezone=row["timezone"],
        status=row["status"],
        started_at=row["started_at"],
        closed_at=row["closed_at"],
        atlas_plan_id=row["atlas_plan_id"],
        public_report_id=row["public_report_id"],
        private_report_id=row["private_report_id"],
        cycle_count=int(row["cycle_count"]),
        last_cycle_at=row["last_cycle_at"],
        summary=row["summary"],
    )


def _plan_from_row(row: Any) -> DailyPlan:
    return DailyPlan(
        plan_id=row["plan_id"],
        workday_id=row["workday_id"],
        created_by_agent_id=row["created_by_agent_id"],
        objective=row["objective"],
        priorities=tuple(json.loads(row["priorities_json"])),
        agent_assignments=dict(json.loads(row["agent_assignments_json"])),
        constraints=tuple(json.loads(row["constraints_json"])),
        real_data_sources_used=tuple(json.loads(row["real_data_sources_used_json"])),
        assumptions=tuple(json.loads(row["assumptions_json"])),
        open_questions=tuple(json.loads(row["open_questions_json"])),
        status=row["status"],
        created_at=row["created_at"],
    )


def _today() -> str:
    return date.today().isoformat()


def _bullets(items: list[str]) -> list[str]:
    return [f"- {redact_auth_text(item)}" for item in items if str(item or "").strip()]


def _telegram_summary(report: str) -> str:
    return "\n".join(line.strip() for line in report.splitlines() if line.strip())[:1500]
