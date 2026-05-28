"""Workday schedule evaluation for The Synthetic Firm."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml


DEFAULT_WORKDAY_PATH = Path("agents/workday.yaml")
WEEKDAY_NAMES = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


@dataclass(frozen=True)
class WorkdayConfig:
    timezone: str
    workdays: frozenset[int]
    start: time
    end: time
    company_daily_budget_usd: float | None = None
    max_task_steps: int | None = None
    max_tool_calls_per_task: int | None = None


@dataclass(frozen=True)
class WorkdayStatus:
    now: datetime
    timezone: str
    inside_work_hours: bool
    reason: str

    def plain_english(self) -> str:
        state = "inside" if self.inside_work_hours else "outside"
        return f"The firm is {state} work hours for {self.timezone}: {self.reason}."


class WorkdayConfigError(ValueError):
    """Raised when workday configuration is invalid."""


def load_workday_config(path: str | Path = DEFAULT_WORKDAY_PATH) -> WorkdayConfig:
    config_path = Path(path)
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise WorkdayConfigError(f"Workday config not found: {config_path}") from exc
    if not isinstance(raw, dict):
        raise WorkdayConfigError("Workday config must be a mapping")

    hours = raw.get("hours") or {}
    if not isinstance(hours, dict):
        raise WorkdayConfigError("hours must be a mapping")

    workdays = raw.get("workdays") or []
    if not isinstance(workdays, list):
        raise WorkdayConfigError("workdays must be a list")

    budget = raw.get("company_budget") or {}
    limits = raw.get("limits") or {}
    if not isinstance(budget, dict):
        raise WorkdayConfigError("company_budget must be a mapping")
    if not isinstance(limits, dict):
        raise WorkdayConfigError("limits must be a mapping")

    return WorkdayConfig(
        timezone=str(raw.get("timezone") or "Europe/Paris"),
        workdays=frozenset(_parse_workday(day) for day in workdays),
        start=_parse_time(hours.get("start") or "10:00"),
        end=_parse_time(hours.get("end") or "16:00"),
        company_daily_budget_usd=_optional_float(budget.get("daily_usd")),
        max_task_steps=_optional_int(limits.get("max_task_steps")),
        max_tool_calls_per_task=_optional_int(limits.get("max_tool_calls_per_task")),
    )


def evaluate_workday(config: WorkdayConfig, now: datetime | None = None) -> WorkdayStatus:
    tz = ZoneInfo(config.timezone)
    local_now = now.astimezone(tz) if now else datetime.now(tz)
    weekday = local_now.weekday()
    if weekday not in config.workdays:
        return WorkdayStatus(local_now, config.timezone, False, f"{WEEKDAY_NAMES[weekday]} is not a workday")
    current = local_now.time().replace(tzinfo=None)
    if not (config.start <= current < config.end):
        return WorkdayStatus(
            local_now,
            config.timezone,
            False,
            f"local time {current.strftime('%H:%M')} is outside {config.start.strftime('%H:%M')}-{config.end.strftime('%H:%M')}",
        )
    return WorkdayStatus(
        local_now,
        config.timezone,
        True,
        f"local time {current.strftime('%H:%M')} is within {config.start.strftime('%H:%M')}-{config.end.strftime('%H:%M')}",
    )


def _parse_workday(value: Any) -> int:
    name = str(value).strip().lower()
    if name not in WEEKDAY_NAMES:
        raise WorkdayConfigError(f"Unknown workday: {value!r}")
    return WEEKDAY_NAMES.index(name)


def _parse_time(value: Any) -> time:
    text = str(value).strip()
    try:
        hour, minute = text.split(":", 1)
        return time(hour=int(hour), minute=int(minute))
    except Exception as exc:
        raise WorkdayConfigError(f"Invalid time: {value!r}") from exc


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)
