"""Private founder human-task inbox for The Synthetic Firm."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from synthetic_firm.provider_auth_redaction import redact_auth_text
from synthetic_firm.time_utils import utc_iso, utc_now

HUMAN_TASK_STATUSES = frozenset({"pending", "done", "blocked", "cancelled"})
HUMAN_TASK_PRIORITIES = frozenset({"low", "medium", "high", "critical"})


class HumanTaskError(ValueError):
    """Raised when a human task is invalid or unsafe."""


@dataclass(frozen=True)
class HumanTask:
    human_task_id: str
    requested_by_agent_id: str
    related_task_id: str | None
    title: str
    plain_english_request: str
    reason: str
    priority: str
    deadline: str | None
    cost_estimate: str | None
    risk_level: str
    public_summary: str
    private_details_redacted: str | None
    status: str
    created_at: str
    updated_at: str
    completed_at: str | None
    founder_note: str | None


def create_human_task(
    *,
    requested_by_agent_id: str,
    title: str,
    plain_english_request: str,
    reason: str,
    public_summary: str,
    related_task_id: str | None = None,
    priority: str = "medium",
    deadline: str | None = None,
    cost_estimate: str | None = None,
    risk_level: str = "medium",
    private_details: str | None = None,
    status: str = "pending",
    now: str | None = None,
) -> HumanTask:
    normalized_priority = _choice(priority, HUMAN_TASK_PRIORITIES, "priority")
    normalized_status = _choice(status, HUMAN_TASK_STATUSES, "status")
    created = now or utc_iso()
    return HumanTask(
        human_task_id=f"HT-{utc_now().year}-{uuid4().hex[:8].upper()}",
        requested_by_agent_id=_required(requested_by_agent_id, "requested_by_agent_id"),
        related_task_id=related_task_id,
        title=_safe_required(title, "title"),
        plain_english_request=_safe_required(plain_english_request, "plain_english_request"),
        reason=_safe_required(reason, "reason"),
        priority=normalized_priority,
        deadline=_safe_optional(deadline),
        cost_estimate=_safe_optional(cost_estimate),
        risk_level=_safe_required(risk_level, "risk_level"),
        public_summary=_safe_required(public_summary, "public_summary"),
        private_details_redacted=_safe_optional(private_details),
        status=normalized_status,
        created_at=created,
        updated_at=created,
        completed_at=created if normalized_status == "done" else None,
        founder_note=None,
    )


def human_task_to_dict(task: HumanTask, *, audience: str = "founder") -> dict[str, Any]:
    base: dict[str, Any] = {
        "humanTaskId": task.human_task_id,
        "requestedByAgentId": task.requested_by_agent_id,
        "relatedTaskId": task.related_task_id,
        "title": task.title,
        "priority": task.priority,
        "deadline": task.deadline,
        "costEstimate": task.cost_estimate,
        "riskLevel": task.risk_level,
        "publicSummary": task.public_summary,
        "status": task.status,
        "createdAt": task.created_at,
        "updatedAt": task.updated_at,
        "completedAt": task.completed_at,
    }
    if audience == "founder":
        base.update(
            {
                "plainEnglishRequest": task.plain_english_request,
                "reason": task.reason,
                "privateDetailsRedacted": task.private_details_redacted,
                "founderNote": _safe_optional(task.founder_note),
            }
        )
    return base


def format_human_task_for_telegram(task: HumanTask) -> str:
    lines = [
        f"HUMAN TASK - {task.human_task_id}",
        "",
        f"Requested by: {task.requested_by_agent_id}",
        f"Need: {task.plain_english_request}",
        f"Reason: {task.reason}",
        f"Priority: {task.priority}",
        f"Cost: {task.cost_estimate or 'Unknown'}",
        f"Deadline: {task.deadline or 'Not set'}",
        f"Public report note: {task.public_summary}",
        "",
        "You can reply in normal language.",
        "Examples:",
        "- Confirmed: this costs 0 euros/month.",
        "- Approved: use the configured research provider.",
        "- Blocked: do not do outreach yet.",
        "",
        "Optional exact commands:",
        f"- /done {task.human_task_id}",
        f"- /blocked {task.human_task_id}",
        f"- /note {task.human_task_id} <message>",
    ]
    return "\n".join(lines)


def _choice(value: str, choices: frozenset[str], name: str) -> str:
    text = str(value or "").strip().lower()
    if text not in choices:
        raise HumanTaskError(f"Invalid {name}: {value}")
    return text


def _required(value: str, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise HumanTaskError(f"{name} is required")
    return text


def _safe_required(value: str, name: str) -> str:
    return _required(redact_auth_text(value), name)


def _safe_optional(value: str | None) -> str | None:
    text = redact_auth_text(value).strip()
    return text or None
