"""Internal task model and state machine."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


TASK_STATUSES = frozenset(
    {
        "proposed",
        "accepted",
        "assigned",
        "in_progress",
        "blocked",
        "review_required",
        "approval_required",
        "completed",
        "cancelled",
        "failed",
    }
)

TERMINAL_STATUSES = frozenset({"completed", "cancelled", "failed"})

ALLOWED_TRANSITIONS = {
    "proposed": {"accepted", "cancelled"},
    "accepted": {"assigned", "cancelled"},
    "assigned": {"in_progress", "blocked", "cancelled"},
    "in_progress": {"blocked", "review_required", "approval_required", "completed", "failed"},
    "blocked": {"in_progress", "cancelled", "failed"},
    "review_required": {"in_progress", "approval_required", "completed", "failed"},
    "approval_required": {"in_progress", "completed", "cancelled", "failed"},
    "completed": set(),
    "cancelled": set(),
    "failed": set(),
}


@dataclass(frozen=True)
class Task:
    task_id: str
    title: str
    objective: str
    assigned_agent_id: str | None
    created_by_agent_id: str
    risk_level: str
    status: str
    external_effect: bool
    budget_limit: float | None
    max_steps: int | None
    created_at: datetime
    updated_at: datetime
    plain_english_summary: str


class TaskStateError(ValueError):
    """Raised for invalid task state or transition."""


def create_task(
    *,
    title: str,
    objective: str,
    created_by_agent_id: str,
    assigned_agent_id: str | None = None,
    risk_level: str = "low",
    external_effect: bool = False,
    budget_limit: float | None = None,
    max_steps: int | None = None,
    task_id: str | None = None,
    now: datetime | None = None,
) -> Task:
    timestamp = now or datetime.now(timezone.utc)
    return Task(
        task_id=task_id or f"task_{uuid4().hex[:12]}",
        title=_required(title, "title"),
        objective=_required(objective, "objective"),
        assigned_agent_id=_optional_str(assigned_agent_id),
        created_by_agent_id=_required(created_by_agent_id, "created_by_agent_id"),
        risk_level=_risk(risk_level),
        status="proposed",
        external_effect=bool(external_effect),
        budget_limit=budget_limit,
        max_steps=max_steps,
        created_at=timestamp,
        updated_at=timestamp,
        plain_english_summary=f"{_required(title, 'title')}: {_required(objective, 'objective')}",
    )


def transition_task(task: Task, new_status: str, *, now: datetime | None = None, summary: str | None = None) -> Task:
    target = str(new_status).strip()
    if target not in TASK_STATUSES:
        raise TaskStateError(f"Unknown task status: {new_status!r}")
    if target not in ALLOWED_TRANSITIONS[task.status]:
        raise TaskStateError(f"Invalid task transition: {task.status} -> {target}")
    return replace(
        task,
        status=target,
        updated_at=now or datetime.now(timezone.utc),
        plain_english_summary=summary or task.plain_english_summary,
    )


def task_to_dict(task: Task) -> dict[str, Any]:
    result = task.__dict__.copy()
    result["created_at"] = task.created_at.isoformat()
    result["updated_at"] = task.updated_at.isoformat()
    return result


def _required(value: Any, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise TaskStateError(f"{name} is required")
    return text


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _risk(value: Any) -> str:
    risk = str(value or "low").strip().lower()
    if risk not in {"low", "medium", "high", "critical"}:
        raise TaskStateError(f"Invalid risk level: {value!r}")
    return risk
