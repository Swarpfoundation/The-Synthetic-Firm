"""Private founder messages routed to Atlas."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from synthetic_firm.provider_auth_redaction import redact_auth_text
from synthetic_firm.time_utils import utc_iso

FOUNDER_MESSAGE_PRIORITIES = frozenset({"normal", "urgent"})
FOUNDER_MESSAGE_TYPES = frozenset(
    {"note", "human_task_done", "clarification", "new_constraint", "urgent_override"}
)
FOUNDER_MESSAGE_STATUSES = frozenset({"received", "queued", "reviewed", "routed", "resolved"})


class FounderMessageError(ValueError):
    """Raised when a founder message is invalid."""


@dataclass(frozen=True)
class FounderMessage:
    message_id: str
    source: str
    received_at: str
    sender: str
    target_agent: str
    priority: str
    message_type: str
    content: str
    status: str
    reviewed_by_agent_id: str | None
    reviewed_at: str | None
    related_human_task_id: str | None
    related_task_id: str | None


def create_founder_message(
    *,
    content: str,
    source: str = "telegram",
    sender: str = "founder",
    target_agent: str = "atlas",
    priority: str = "normal",
    message_type: str = "note",
    status: str = "queued",
    reviewed_by_agent_id: str | None = None,
    reviewed_at: str | None = None,
    related_human_task_id: str | None = None,
    related_task_id: str | None = None,
    message_id: str | None = None,
    received_at: str | None = None,
) -> FounderMessage:
    normalized_priority = _choice(priority, FOUNDER_MESSAGE_PRIORITIES, "priority")
    normalized_type = _choice(message_type, FOUNDER_MESSAGE_TYPES, "message_type")
    normalized_status = _choice(status, FOUNDER_MESSAGE_STATUSES, "status")
    return FounderMessage(
        message_id=message_id or f"fm_{uuid4().hex[:12]}",
        source=_required(source, "source"),
        received_at=received_at or utc_iso(),
        sender=_required(sender, "sender"),
        target_agent=_required(target_agent, "target_agent"),
        priority=normalized_priority,
        message_type=normalized_type,
        content=_required(redact_auth_text(content), "content"),
        status=normalized_status,
        reviewed_by_agent_id=reviewed_by_agent_id,
        reviewed_at=reviewed_at,
        related_human_task_id=related_human_task_id,
        related_task_id=related_task_id,
    )


def founder_message_to_dict(message: FounderMessage, *, public: bool = False) -> dict[str, Any]:
    if public:
        return {
            "status": message.status,
            "priority": message.priority,
            "messageType": message.message_type,
            "targetAgent": message.target_agent,
        }
    return {
        "message_id": message.message_id,
        "source": message.source,
        "received_at": message.received_at,
        "sender": message.sender,
        "target_agent": message.target_agent,
        "priority": message.priority,
        "message_type": message.message_type,
        "content": message.content,
        "status": message.status,
        "reviewed_by_agent_id": message.reviewed_by_agent_id,
        "reviewed_at": message.reviewed_at,
        "related_human_task_id": message.related_human_task_id,
        "related_task_id": message.related_task_id,
    }


def _choice(value: str, choices: frozenset[str], name: str) -> str:
    text = str(value or "").strip().lower()
    if text not in choices:
        raise FounderMessageError(f"Invalid {name}: {value}")
    return text


def _required(value: str, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise FounderMessageError(f"{name} is required")
    return text
