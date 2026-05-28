"""Local orchestrator-mediated message bus for internal agents."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


CHANNELS = frozenset({"company", "atlas", "scout", "forge", "pulse", "sentinel"})


@dataclass(frozen=True)
class AgentMessage:
    message_id: str
    sender_agent_id: str
    recipient_agent_id: str | None
    channel: str | None
    task_id: str | None
    message_type: str
    content: str
    created_at: datetime


class MessageRoutingError(ValueError):
    """Raised when a message cannot be safely routed."""


def create_message(
    *,
    sender_agent_id: str,
    content: str,
    recipient_agent_id: str | None = None,
    channel: str | None = None,
    task_id: str | None = None,
    message_type: str = "note",
    now: datetime | None = None,
) -> AgentMessage:
    if bool(recipient_agent_id) == bool(channel):
        raise MessageRoutingError("Set exactly one of recipient_agent_id or channel")
    normalized_channel = str(channel).strip().lower() if channel else None
    if normalized_channel and normalized_channel not in CHANNELS:
        raise MessageRoutingError(f"Unsupported channel: {channel!r}")
    sender = str(sender_agent_id or "").strip().lower()
    if not sender:
        raise MessageRoutingError("sender_agent_id is required")
    body = str(content or "").strip()
    if not body:
        raise MessageRoutingError("content is required")
    return AgentMessage(
        message_id=f"msg_{uuid4().hex[:12]}",
        sender_agent_id=sender,
        recipient_agent_id=_optional_agent(recipient_agent_id),
        channel=normalized_channel,
        task_id=_optional_str(task_id),
        message_type=str(message_type or "note").strip().lower(),
        content=body,
        created_at=now or datetime.now(timezone.utc),
    )


def append_message_log(message: AgentMessage, path: str | Path) -> Path:
    log_path = Path(path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(message_to_dict(message), sort_keys=True) + "\n")
    return log_path


def message_to_dict(message: AgentMessage) -> dict[str, Any]:
    result = message.__dict__.copy()
    result["created_at"] = message.created_at.isoformat()
    return result


def _optional_agent(value: str | None) -> str | None:
    text = _optional_str(value)
    return text.lower() if text else None


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
