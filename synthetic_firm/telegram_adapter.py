"""Dry-run Telegram command adapter."""

from __future__ import annotations

from dataclasses import dataclass

from synthetic_firm.approval import ApprovalRequest, format_telegram_approval


class TelegramAdapterError(ValueError):
    """Raised for malformed Telegram command text."""


@dataclass(frozen=True)
class TelegramCommand:
    command: str
    approval_id: str | None = None
    human_task_id: str | None = None
    message: str | None = None
    priority: str = "normal"
    message_type: str | None = None


SUPPORTED_COMMANDS = frozenset(
    {
        "approve",
        "deny",
        "approval",
        "status",
        "pause",
        "resume",
        "kill",
        "budget",
        "report",
        "approvals",
        "tasks",
        "human_tasks",
        "human_task",
        "done",
        "blocked",
        "note",
        "urgent",
        "clarify",
        "constraint",
        "help",
    }
)


def format_outgoing_approval(request: ApprovalRequest) -> str:
    return format_telegram_approval(request).replace("/pause\n/budget", "/pause\n/resume\n/budget\n/report")


def parse_telegram_command(text: str) -> TelegramCommand:
    parts = str(text or "").strip().split()
    if not parts or not parts[0].startswith("/"):
        raise TelegramAdapterError("Telegram command must start with /")
    command = parts[0][1:].lower()
    if command not in SUPPORTED_COMMANDS:
        raise TelegramAdapterError(f"Unsupported Telegram command: /{command}")
    if command in {"approve", "deny", "approval"}:
        if len(parts) != 2 or not parts[1].strip():
            raise TelegramAdapterError(f"/{command} requires an approval id")
        return TelegramCommand(command=command, approval_id=parts[1].strip())
    if command in {"human_task", "done", "blocked"}:
        if len(parts) != 2 or not parts[1].strip():
            raise TelegramAdapterError(f"/{command} requires a human task id")
        return TelegramCommand(command=command, human_task_id=parts[1].strip())
    if command == "note":
        if len(parts) < 3 or not parts[1].strip():
            raise TelegramAdapterError("/note requires a human task id and message")
        return TelegramCommand(command=command, human_task_id=parts[1].strip(), message=" ".join(parts[2:]).strip())
    if command == "urgent":
        if len(parts) < 2:
            raise TelegramAdapterError("/urgent requires a message")
        return TelegramCommand(
            command="founder_message",
            message=" ".join(parts[1:]).strip(),
            priority="urgent",
            message_type="urgent_override",
        )
    if command == "clarify":
        if len(parts) < 2:
            raise TelegramAdapterError("/clarify requires a message")
        return TelegramCommand(
            command="founder_message",
            message=" ".join(parts[1:]).strip(),
            message_type="clarification",
        )
    if command == "constraint":
        if len(parts) < 2:
            raise TelegramAdapterError("/constraint requires a message")
        return TelegramCommand(
            command="founder_message",
            message=" ".join(parts[1:]).strip(),
            message_type="new_constraint",
        )
    if command == "kill" and len(parts) == 2:
        return TelegramCommand(command=command, approval_id=parts[1].strip())
    if len(parts) != 1:
        raise TelegramAdapterError(f"/{command} does not accept arguments")
    return TelegramCommand(command=command)


def handle_telegram_command_dry_run(text: str) -> str:
    command = parse_telegram_command(text)
    if command.command == "founder_message":
        return "Dry-run: would queue founder message for Atlas review."
    if command.approval_id:
        return f"Dry-run: would route /{command.command} for approval {command.approval_id}."
    if command.human_task_id:
        return f"Dry-run: would route /{command.command} for human task {command.human_task_id}."
    return f"Dry-run: would route /{command.command} to the TSF orchestrator."
