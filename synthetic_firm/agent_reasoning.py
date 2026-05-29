"""Evidence-bounded reasoning contexts and structured outputs for TSF agents."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from synthetic_firm.budget_gate import safe_budget_context
from synthetic_firm.llm_client import AgentReasoningRequest
from synthetic_firm.provider_auth_redaction import redact_auth_text
from synthetic_firm.store import Store
from synthetic_firm.truthfulness_guard import evaluate_public_claims

AGENT_REASONING_FIELDS = frozenset(
    {
        "summary",
        "proposed_tasks",
        "messages_to_agents",
        "human_tasks",
        "assumptions",
        "evidence_refs",
        "blocked_reasons",
        "public_report_notes",
        "private_founder_notes",
    }
)
AGENT_PURPOSES = {
    "atlas": "Create or update daily management priorities from persisted state.",
    "scout": "Identify research work only from real configured sources or blockers.",
    "forge": "Identify repo/product work from real runtime state, create coding-agent implementation tasks, and track blockers.",
    "pulse": "Identify growth planning only from approved real data or blockers.",
    "sentinel": "Review truthfulness, privacy, security, budget, and unsupported claims.",
}
FORBIDDEN_OUTPUTS = (
    "Do not claim revenue, customers, leads, investors, meetings, PRs, deployments, outreach, payments, accounts, or domains unless evidence_refs include persisted evidence.",
    "Do not request or expose secrets.",
    "Do not propose live external business actions as completed work.",
    "Do not change permissions, budgets, policies, logging, or authority without founder-visible review.",
)
ALLOWED_OUTPUTS = (
    "JSON only using the required schema.",
    "Evidence-backed summaries.",
    "Assumptions clearly listed as assumptions.",
    "Blocked reasons and HumanTask requests for real-world blockers.",
    "Public-safe report notes.",
)


class AgentReasoningError(ValueError):
    """Raised when an agent reasoning context or output is unsafe."""


@dataclass(frozen=True)
class ReasoningValidationResult:
    allowed: bool
    summary: str
    blocked_reasons: tuple[str, ...]


def build_agent_reasoning_request(
    store: Store,
    *,
    agent_id: str,
    workday_id: str | None = None,
    task_id: str | None = None,
) -> AgentReasoningRequest:
    if agent_id not in AGENT_PURPOSES:
        raise AgentReasoningError(f"Unsupported reasoning agent: {agent_id}")
    context = build_agent_context(store, agent_id=agent_id, workday_id=workday_id, task_id=task_id)
    return AgentReasoningRequest(
        agent_id=agent_id,
        task_id=task_id,
        workday_id=workday_id,
        purpose=AGENT_PURPOSES[agent_id],
        system_instructions=_system_instructions(agent_id),
        context_summary=context,
        allowed_outputs=ALLOWED_OUTPUTS,
        forbidden_outputs=FORBIDDEN_OUTPUTS,
        max_output_chars=4000,
        require_json=True,
        risk_level="medium" if agent_id == "sentinel" else "low",
        budget_context=_budget_context(store, agent_id=agent_id, task_id=task_id),
    )


def build_agent_context(
    store: Store,
    *,
    agent_id: str,
    workday_id: str | None = None,
    task_id: str | None = None,
) -> str:
    tasks = store.list_tasks()
    human_tasks = store.list_human_tasks()
    founder_messages = store.list_founder_messages()
    messages = store.list_messages()
    reports = store.list_daily_reports()
    task_lines = [
        f"{task.task_id}: {task.status} assigned={task.assigned_agent_id or 'none'} summary={task.plain_english_summary}"
        for task in tasks[-20:]
    ]
    human_lines = [
        f"{task.human_task_id}: {task.status} public_summary={task.public_summary}"
        for task in human_tasks[-20:]
    ]
    founder_summary = _founder_message_summary(founder_messages)
    message_summary = [
        f"{message.sender_agent_id}->{message.channel or message.recipient_agent_id}: {message.message_type}"
        for message in messages[-10:]
    ]
    report_summary = [f"{report['report_date']}: {report['telegram_summary']}" for report in reports[:3]]
    capability_note = _capability_note(agent_id)
    context = {
        "agent_id": agent_id,
        "workday_id": workday_id,
        "task_id": task_id,
        "task_summaries": task_lines or ["No persisted tasks."],
        "human_task_public_summaries": human_lines or ["No persisted HumanTasks."],
        "founder_message_summary": founder_summary,
        "message_summary": message_summary or ["No internal messages."],
        "report_summary": report_summary or ["No reports."],
        "capability_note": capability_note,
        "infrastructure_budget": safe_budget_context(store),
        "missing_data_rule": "If evidence is missing, say missing and create blockers or HumanTasks instead of pretending.",
    }
    return redact_auth_text(json.dumps(context, sort_keys=True))


def validate_reasoning_output(output: dict[str, Any], *, evidence: list[str]) -> ReasoningValidationResult:
    missing = AGENT_REASONING_FIELDS - set(output)
    if missing:
        return ReasoningValidationResult(False, "Structured output is missing required fields.", tuple(sorted(missing)))
    text = "\n".join(
        str(item)
        for item in (
            output.get("summary", ""),
            *output.get("public_report_notes", []),
            *[task.get("summary", "") if isinstance(task, dict) else str(task) for task in output.get("proposed_tasks", [])],
        )
    )
    evidence_refs = output.get("evidence_refs") or []
    assumptions = output.get("assumptions") or []
    truth = evaluate_public_claims(text, [*evidence, *[str(ref) for ref in evidence_refs], *[str(item) for item in assumptions]])
    if not truth.allowed:
        return ReasoningValidationResult(False, truth.summary, tuple(truth.unsupported_claims))
    return ReasoningValidationResult(True, "Structured output accepted.", ())


def safe_reasoning_summary(output: dict[str, Any]) -> str:
    return redact_auth_text(str(output.get("summary") or "Agent reasoning completed."))


def _system_instructions(agent_id: str) -> str:
    return (
        f"You are {agent_id}, an internal TSF agent. Return compact JSON only. "
        "Use persisted evidence, label assumptions, create HumanTasks only for real-world blockers, "
        "and never claim external actions happened without audit evidence."
    )


def _founder_message_summary(messages: list[Any]) -> dict[str, int]:
    return {
        "queued": len([message for message in messages if message.status in {"received", "queued"}]),
        "reviewed": len([message for message in messages if message.status == "reviewed"]),
        "urgent": len([message for message in messages if message.priority == "urgent"]),
    }


def _capability_note(agent_id: str) -> str:
    if agent_id == "scout":
        return "No external research adapter exists yet; do not invent leads or market findings."
    if agent_id == "forge":
        return (
            "Forge may propose repo edits, tests, commits, Vercel preview work, and Render runtime changes for the coding agent. "
            "Do not claim code changes, pushes, previews, or deployments are complete unless persisted evidence exists."
        )
    if agent_id == "pulse":
        return "No email/social/CRM sending adapter exists; do not claim outreach was sent."
    if agent_id == "sentinel":
        return "Block unsupported claims and privacy/security risks."
    return "Atlas coordinates work asynchronously and reviews founder messages at checkpoints."


def _budget_context(store: Store, *, agent_id: str, task_id: str | None) -> dict[str, Any]:
    agent = store.budget_totals(agent_id=agent_id)
    task = store.budget_totals(task_id=task_id) if task_id else {"spend": 0.0, "loop_steps": 0, "tool_calls": 0}
    company = store.budget_totals()
    return {
        "agent_daily_spend_usd": agent["spend"],
        "task_spend_usd": task["spend"],
        "company_daily_spend_usd": company["spend"],
        "task_loop_steps": task["loop_steps"],
        "task_tool_calls": task["tool_calls"],
        "infrastructure_budget": safe_budget_context(store),
    }
