"""Company runtime pause/resume/kill switch."""

from __future__ import annotations

VALID_STATUS = frozenset({"active", "paused", "killed"})
READ_ONLY_ACTIONS = frozenset({"status_check", "generate_daily_report", "audit_export"})


class RuntimeStatusError(ValueError):
    """Raised when runtime status blocks work."""


def validate_status_for_action(status: str, action: str) -> None:
    normalized = str(status or "").lower()
    if normalized == "active":
        return
    if normalized == "paused" and action in READ_ONLY_ACTIONS:
        return
    if normalized == "killed" and action in {"status_check", "audit_export"}:
        return
    raise RuntimeStatusError(f"Runtime status {normalized} blocks action {action}")
