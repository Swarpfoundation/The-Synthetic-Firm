"""Bounded autonomous scheduler checkpoints for The Synthetic Firm."""

from __future__ import annotations

import signal
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from synthetic_firm.autonomous_workday import (
    close_workday,
    generate_private_founder_report,
    generate_public_daily_report,
    get_current_workday,
    run_cycle,
    start_workday,
)
from synthetic_firm.human_tasks import HumanTask, format_human_task_for_telegram
from synthetic_firm.model_provider import provider_status
from synthetic_firm.notification_queue import enqueue_notification
from synthetic_firm.provider_auth_redaction import redact_auth_text
from synthetic_firm.store import Store
from synthetic_firm.time_utils import parse_utc_iso, utc_iso, utc_now
from synthetic_firm.workday import WorkdayConfig, evaluate_workday, load_workday_config

CHECKPOINT_SCHEDULE = (
    ("10:00", "start_workday", "Atlas starts the autonomous workday."),
    ("11:00", "cycle_1100", "Run one bounded autonomous workday cycle."),
    ("12:30", "cycle_1230", "Run one bounded autonomous workday cycle."),
    ("14:00", "cycle_1400", "Run one bounded autonomous workday cycle."),
    ("15:30", "report_1530", "Generate Atlas manager reports from real persisted state."),
    ("16:00", "close_workday", "Close the autonomous workday."),
)
RUN_STATUSES = frozenset({"running", "completed", "failed", "cancelled", "skipped"})
LOCK_TTL_SECONDS = 10 * 60
MAX_CHECKPOINTS_PER_DAY = 8
MAX_NOTIFICATIONS_PER_CHECKPOINT = 8
DEFAULT_LOOP_SLEEP_SECONDS = 60


class SchedulerError(ValueError):
    """Raised when the scheduler fails closed."""


@dataclass(frozen=True)
class SchedulerEvaluation:
    checkpoint_type: str
    due: bool
    reason: str
    local_now: str
    next_checkpoint: str | None
    workday_inside: bool


@dataclass(frozen=True)
class SchedulerLock:
    lock_id: str
    acquired_at: str
    expires_at: str
    owner: str
    status: str


def evaluate_checkpoint_now(now: datetime | None = None, *, store: Store | None = None) -> SchedulerEvaluation:
    """Evaluate which checkpoint is due for the current Paris workday."""

    config = load_workday_config()
    local_now = _local_now(config, now)
    workday = evaluate_workday(config, local_now)
    checkpoint_type, next_checkpoint = _checkpoint_for_time(local_now)
    due = checkpoint_type != "none"
    reason = "Checkpoint is due." if due else "No checkpoint is due now."
    if local_now.weekday() not in config.workdays:
        due = False
        checkpoint_type = "none"
        reason = "Today is not a configured workday."
    elif checkpoint_type.startswith("cycle") and not workday.inside_work_hours:
        due = False
        reason = "Cycle checkpoint is outside configured work hours."
    elif store and _checkpoint_already_completed(store, checkpoint_type, local_now):
        due = False
        reason = f"{checkpoint_type} already completed for this local workday."
    return SchedulerEvaluation(
        checkpoint_type=checkpoint_type,
        due=due,
        reason=reason,
        local_now=local_now.isoformat(),
        next_checkpoint=next_checkpoint,
        workday_inside=workday.inside_work_hours,
    )


def should_start_workday(now: datetime | None = None, *, store: Store | None = None) -> bool:
    evaluation = evaluate_checkpoint_now(now, store=store)
    return evaluation.due and evaluation.checkpoint_type == "start_workday"


def should_run_cycle(now: datetime | None = None, *, store: Store | None = None) -> bool:
    evaluation = evaluate_checkpoint_now(now, store=store)
    return evaluation.due and evaluation.checkpoint_type.startswith("cycle")


def should_close_workday(now: datetime | None = None, *, store: Store | None = None) -> bool:
    evaluation = evaluate_checkpoint_now(now, store=store)
    return evaluation.due and evaluation.checkpoint_type == "close_workday"


def should_send_report(now: datetime | None = None, *, store: Store | None = None) -> bool:
    evaluation = evaluate_checkpoint_now(now, store=store)
    return evaluation.due and evaluation.checkpoint_type in {"report_1530", "close_workday"}


def should_notify_founder(store: Store) -> bool:
    return bool(_pending_unnotified_human_tasks(store))


def run_checkpoint_once(
    store: Store | None = None,
    *,
    now: datetime | None = None,
    owner: str = "scheduler",
) -> dict[str, Any]:
    """Execute exactly one due checkpoint and exit."""

    own_store = store is None
    store = store or Store()
    lock: SchedulerLock | None = None
    run_id: str | None = None
    try:
        evaluation = evaluate_checkpoint_now(now, store=store)
        lock = acquire_scheduler_lock(store, owner=owner)
        if lock is None:
            return {"status": "skipped", "summary": "Scheduler lock is already held.", "evaluation": evaluation.__dict__}
        run_id = _insert_scheduler_run(
            store,
            mode="checkpoint_once",
            checkpoint_type=evaluation.checkpoint_type,
            lock_id=lock.lock_id,
            summary="Scheduler checkpoint started.",
            started_at=utc_iso(datetime.fromisoformat(evaluation.local_now)),
        )
        if not evaluation.due:
            _finish_scheduler_run(store, run_id, status="skipped", summary=evaluation.reason)
            return {"status": "skipped", "summary": evaluation.reason, "evaluation": evaluation.__dict__}
        _preflight_or_fail(store, evaluation)
        before_human_task_ids = {task.human_task_id for task in store.list_human_tasks()}
        result = _execute_checkpoint(store, evaluation)
        notifications = enqueue_new_human_task_notifications(store, before_ids=before_human_task_ids)
        summary = f"{evaluation.checkpoint_type} completed. {len(notifications)} founder notification(s) queued."
        _finish_scheduler_run(
            store,
            run_id,
            status="completed",
            summary=summary,
            workday_id=result.get("workday_id"),
            cycle_id=result.get("cycle_id"),
        )
        return {
            "status": "completed",
            "summary": summary,
            "evaluation": evaluation.__dict__,
            "result": result,
            "notifications_queued": len(notifications),
        }
    except Exception as exc:
        message = redact_auth_text(str(exc))
        if run_id:
            _finish_scheduler_run(store, run_id, status="failed", summary="Scheduler checkpoint failed closed.", error=message)
        store.append_audit(
            actor_type="orchestrator",
            actor_id="scheduler",
            action="scheduler_checkpoint_failed",
            target_type="scheduler_run",
            target_id=run_id or "unstarted",
            risk_level="medium",
            summary=message,
        )
        return {"status": "failed", "summary": message}
    finally:
        if lock:
            release_scheduler_lock(store, lock.lock_id)
        if own_store:
            store.close()


def run_scheduler_loop(
    *,
    max_runtime_seconds: int,
    max_checkpoints: int,
    sleep_seconds: int = DEFAULT_LOOP_SLEEP_SECONDS,
    store: Store | None = None,
) -> dict[str, Any]:
    """Run a bounded local/dev scheduler loop with hard stop limits."""

    if max_runtime_seconds <= 0 or max_checkpoints <= 0:
        raise SchedulerError("Scheduler loop requires positive runtime and checkpoint limits")
    own_store = store is None
    store = store or Store()
    cancelled = False

    def _cancel(_signum: int, _frame: Any) -> None:
        nonlocal cancelled
        cancelled = True

    previous_int = signal.getsignal(signal.SIGINT)
    previous_term = signal.getsignal(signal.SIGTERM)
    signal.signal(signal.SIGINT, _cancel)
    signal.signal(signal.SIGTERM, _cancel)
    started = time.monotonic()
    completed = 0
    results: list[dict[str, Any]] = []
    run_id = _insert_scheduler_run(
        store,
        mode="local_loop",
        checkpoint_type="loop",
        lock_id=None,
        summary="Bounded local scheduler loop started.",
    )
    store.append_audit(
        actor_type="orchestrator",
        actor_id="scheduler",
        action="scheduler_loop_start",
        target_type="scheduler_run",
        target_id=run_id,
        summary="Bounded local/dev scheduler loop started.",
    )
    try:
        while not cancelled and completed < max_checkpoints and (time.monotonic() - started) < max_runtime_seconds:
            result = run_checkpoint_once(store, owner="scheduler_loop")
            results.append(result)
            if result["status"] in {"completed", "failed"}:
                completed += 1
            if completed >= max_checkpoints:
                break
            remaining = max_runtime_seconds - int(time.monotonic() - started)
            if remaining <= 0:
                break
            time.sleep(min(max(sleep_seconds, 1), remaining))
        final_status = "cancelled" if cancelled else "completed"
        _finish_scheduler_run(store, run_id, status=final_status, summary=f"Scheduler loop ended after {completed} checkpoint(s).")
        return {"status": final_status, "checkpoints": completed, "results": results}
    finally:
        signal.signal(signal.SIGINT, previous_int)
        signal.signal(signal.SIGTERM, previous_term)
        if own_store:
            store.close()


def acquire_scheduler_lock(
    store: Store,
    *,
    owner: str = "scheduler",
    ttl_seconds: int = LOCK_TTL_SECONDS,
) -> SchedulerLock | None:
    now = utc_now()
    expires_at = now + timedelta(seconds=ttl_seconds)
    _expire_stale_locks(store, now)
    active = store.connection.execute(
        "SELECT * FROM scheduler_locks WHERE status = 'active' ORDER BY acquired_at DESC LIMIT 1"
    ).fetchone()
    if active:
        store.append_audit(
            actor_type="orchestrator",
            actor_id="scheduler",
            action="scheduler_lock_blocked",
            target_type="scheduler_lock",
            target_id=active["lock_id"],
            risk_level="low",
            summary="Scheduler lock is already active; overlapping run blocked.",
        )
        return None
    lock = SchedulerLock(
        lock_id=f"slock_{uuid4().hex[:12]}",
        acquired_at=utc_iso(now),
        expires_at=utc_iso(expires_at),
        owner=owner,
        status="active",
    )
    store.connection.execute(
        "INSERT INTO scheduler_locks VALUES (?, ?, ?, ?, ?)",
        (lock.lock_id, lock.acquired_at, lock.expires_at, lock.owner, lock.status),
    )
    store.connection.commit()
    store.append_audit(
        actor_type="orchestrator",
        actor_id="scheduler",
        action="scheduler_lock_acquire",
        target_type="scheduler_lock",
        target_id=lock.lock_id,
        summary="Scheduler lock acquired.",
    )
    return lock


def release_scheduler_lock(store: Store, lock_id: str, *, status: str = "released") -> None:
    store.connection.execute("UPDATE scheduler_locks SET status = ? WHERE lock_id = ?", (status, lock_id))
    store.connection.commit()
    store.append_audit(
        actor_type="orchestrator",
        actor_id="scheduler",
        action="scheduler_lock_release",
        target_type="scheduler_lock",
        target_id=lock_id,
        summary=f"Scheduler lock marked {status}.",
    )


def scheduler_lock_status(store: Store | None = None) -> dict[str, Any]:
    own_store = store is None
    store = store or Store()
    try:
        _expire_stale_locks(store, utc_now())
        row = store.connection.execute(
            "SELECT * FROM scheduler_locks ORDER BY acquired_at DESC LIMIT 1"
        ).fetchone()
        return {
            "summary": "Scheduler lock status loaded.",
            "lock": dict(row) if row else None,
        }
    finally:
        if own_store:
            store.close()


def scheduler_status(store: Store | None = None, *, now: datetime | None = None) -> dict[str, Any]:
    own_store = store is None
    store = store or Store()
    try:
        row = store.connection.execute(
            "SELECT * FROM scheduler_runs ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        evaluation = evaluate_checkpoint_now(now, store=store)
        return {
            "summary": "Autonomous scheduler status loaded.",
            "runtime_status": store.runtime_status(),
            "last_run": dict(row) if row else None,
            "lock": scheduler_lock_status(store)["lock"],
            "current_evaluation": evaluation.__dict__,
            "schedule": scheduler_dry_run_plan(now=now)["checkpoints"],
        }
    finally:
        if own_store:
            store.close()


def scheduler_dry_run_plan(now: datetime | None = None) -> dict[str, Any]:
    config = load_workday_config()
    local_now = _local_now(config, now)
    evaluation = evaluate_checkpoint_now(local_now)
    return {
        "summary": "Internal/dev scheduler checkpoint plan.",
        "timezone": config.timezone,
        "workdays": "Monday-Friday",
        "hours": f"{config.start.strftime('%H:%M')}-{config.end.strftime('%H:%M')}",
        "local_now": local_now.isoformat(),
        "current_evaluation": evaluation.__dict__,
        "checkpoints": [
            {"time": time_text, "checkpoint_type": checkpoint_type, "summary": summary}
            for time_text, checkpoint_type, summary in CHECKPOINT_SCHEDULE
        ],
    }


def enqueue_new_human_task_notifications(
    store: Store,
    *,
    before_ids: set[str] | None = None,
    limit: int = MAX_NOTIFICATIONS_PER_CHECKPOINT,
) -> list[str]:
    before_ids = before_ids or set()
    queued: list[str] = []
    for task in _pending_unnotified_human_tasks(store):
        if before_ids and task.human_task_id not in before_ids | {task.human_task_id}:
            continue
        if len(queued) >= limit:
            store.append_audit(
                actor_type="orchestrator",
                actor_id="scheduler",
                action="notification_limit",
                target_type="human_task",
                target_id="batch",
                risk_level="medium",
                summary="HumanTask notification limit reached for this checkpoint.",
            )
            break
        body = format_human_task_for_telegram(task)
        note_type = "provider_blocker" if "provider" in f"{task.title} {task.public_summary}".lower() else "human_task"
        notification = enqueue_notification(store, notification_type=note_type, body=body, dry_run=True)
        queued.append(notification.notification_id)
    return queued


def _execute_checkpoint(store: Store, evaluation: SchedulerEvaluation) -> dict[str, Any]:
    checkpoint = evaluation.checkpoint_type
    if checkpoint == "start_workday":
        workday = start_workday(store)
        return {"workday_id": workday.workday_id, "summary": workday.summary}
    if checkpoint.startswith("cycle"):
        _audit_provider_status(store)
        result = run_cycle(store)
        workday = result.get("workday") or {}
        return {"workday_id": workday.get("workday_id"), "cycle_id": checkpoint, "summary": result["summary"]}
    if checkpoint == "report_1530":
        workday = get_current_workday(store) or start_workday(store)
        public_report_id = generate_public_daily_report(store, workday.workday_id)
        private_report_id = generate_private_founder_report(store, workday.workday_id)
        return {
            "workday_id": workday.workday_id,
            "public_report_id": public_report_id,
            "private_report_id": private_report_id,
            "summary": "Atlas manager reports generated.",
        }
    if checkpoint == "close_workday":
        workday = get_current_workday(store)
        if workday:
            generate_public_daily_report(store, workday.workday_id)
            generate_private_founder_report(store, workday.workday_id)
            closed = close_workday(store)
            return {"workday_id": closed.workday_id, "summary": closed.summary}
        return {"workday_id": None, "summary": "No active workday was available to close."}
    raise SchedulerError(f"Unsupported checkpoint: {checkpoint}")


def _preflight_or_fail(store: Store, evaluation: SchedulerEvaluation) -> None:
    runtime = store.runtime_status()
    if runtime == "killed":
        store.append_audit(
            actor_type="orchestrator",
            actor_id="scheduler",
            action="scheduler_runtime_block",
            target_type="runtime_status",
            target_id="company",
            risk_level="high",
            summary="Killed runtime blocked scheduler work.",
        )
        raise SchedulerError("Runtime is killed; scheduler work is blocked")
    if runtime == "paused":
        store.append_audit(
            actor_type="orchestrator",
            actor_id="scheduler",
            action="scheduler_runtime_block",
            target_type="runtime_status",
            target_id="company",
            risk_level="medium",
            summary="Paused runtime blocked scheduler work.",
        )
        raise SchedulerError("Runtime is paused; scheduler work is blocked")
    ok, audit_summary = store.verify_audit()
    if not ok:
        store.append_audit(
            actor_type="orchestrator",
            actor_id="scheduler",
            action="scheduler_audit_block",
            target_type="audit_log",
            target_id="chain",
            risk_level="high",
            summary=redact_auth_text(audit_summary),
        )
        raise SchedulerError("Audit verification failed; scheduler work is blocked")
    if evaluation.checkpoint_type.startswith("cycle") and not evaluation.workday_inside:
        raise SchedulerError("Cycle checkpoint is outside work hours")
    _budget_or_fail(store)
    if _checkpoint_count_today(store) >= MAX_CHECKPOINTS_PER_DAY:
        store.append_audit(
            actor_type="orchestrator",
            actor_id="scheduler",
            action="scheduler_budget_block",
            target_type="scheduler_run",
            target_id="daily",
            risk_level="medium",
            summary="Daily scheduler checkpoint limit reached.",
        )
        raise SchedulerError("Daily scheduler checkpoint limit reached")


def _budget_or_fail(store: Store) -> None:
    config = load_workday_config()
    if config.company_daily_budget_usd is None:
        store.append_audit(
            actor_type="orchestrator",
            actor_id="scheduler",
            action="scheduler_budget_unknown",
            target_type="budget",
            target_id="company",
            risk_level="medium",
            summary="Company daily budget is unknown; scheduler failed closed.",
        )
        raise SchedulerError("Company daily budget is unavailable")
    totals = store.budget_totals()
    if float(totals["spend"]) > config.company_daily_budget_usd:
        store.append_audit(
            actor_type="orchestrator",
            actor_id="scheduler",
            action="scheduler_budget_block",
            target_type="budget",
            target_id="company",
            risk_level="medium",
            summary="Company daily budget exceeded; scheduler failed closed.",
        )
        raise SchedulerError("Company daily budget exceeded")


def _audit_provider_status(store: Store) -> None:
    try:
        status = provider_status()
    except Exception as exc:
        status = {"connected": False, "safe_summary": redact_auth_text(str(exc))}
    store.append_audit(
        actor_type="orchestrator",
        actor_id="scheduler",
        action="provider_status_check",
        target_type="model_provider",
        target_id=str(status.get("provider", "unknown")),
        risk_level="low" if status.get("connected") else "medium",
        summary=str(status.get("safe_summary") or "Model provider status checked."),
        metadata={"connected": bool(status.get("connected")), "dry_run": bool(status.get("dry_run"))},
    )


def _pending_unnotified_human_tasks(store: Store) -> list[HumanTask]:
    tasks = store.list_human_tasks(status="pending")
    existing = store.connection.execute(
        "SELECT body FROM notification_queue WHERE notification_type IN ('human_task', 'provider_blocker')"
    ).fetchall()
    bodies = "\n".join(str(row["body"]) for row in existing)
    return [task for task in tasks if task.human_task_id not in bodies]


def _insert_scheduler_run(
    store: Store,
    *,
    mode: str,
    checkpoint_type: str,
    lock_id: str | None,
    summary: str,
    workday_id: str | None = None,
    started_at: str | None = None,
) -> str:
    run_id = f"srun_{uuid4().hex[:12]}"
    store.connection.execute(
        "INSERT INTO scheduler_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (run_id, started_at or utc_iso(), None, mode, "running", checkpoint_type, workday_id, None, lock_id, summary, None),
    )
    store.connection.commit()
    store.append_audit(
        actor_type="orchestrator",
        actor_id="scheduler",
        action="scheduler_run_start",
        target_type="scheduler_run",
        target_id=run_id,
        summary=summary,
    )
    return run_id


def _finish_scheduler_run(
    store: Store,
    scheduler_run_id: str,
    *,
    status: str,
    summary: str,
    error: str | None = None,
    workday_id: str | None = None,
    cycle_id: str | None = None,
) -> None:
    if status not in RUN_STATUSES:
        raise SchedulerError(f"Unsupported scheduler run status: {status}")
    store.connection.execute(
        """
        UPDATE scheduler_runs
        SET ended_at = ?, status = ?, summary = ?, error_redacted = COALESCE(?, error_redacted),
            workday_id = COALESCE(?, workday_id), cycle_id = COALESCE(?, cycle_id)
        WHERE scheduler_run_id = ?
        """,
        (utc_iso(), status, redact_auth_text(summary), redact_auth_text(error) if error else None, workday_id, cycle_id, scheduler_run_id),
    )
    store.connection.commit()
    store.append_audit(
        actor_type="orchestrator",
        actor_id="scheduler",
        action="scheduler_run_end",
        target_type="scheduler_run",
        target_id=scheduler_run_id,
        risk_level="medium" if status == "failed" else "low",
        summary=f"Scheduler run ended with status {status}.",
    )


def _checkpoint_already_completed(store: Store, checkpoint_type: str, local_now: datetime) -> bool:
    if checkpoint_type == "none":
        return False
    tz = local_now.tzinfo or ZoneInfo(load_workday_config().timezone)
    start_local = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_local = start_local + timedelta(days=1)
    start_utc = utc_iso(start_local.astimezone(ZoneInfo("UTC")))
    end_utc = utc_iso(end_local.astimezone(ZoneInfo("UTC")))
    row = store.connection.execute(
        """
        SELECT 1 FROM scheduler_runs
        WHERE checkpoint_type = ?
          AND status IN ('running', 'completed')
          AND started_at >= ?
          AND started_at < ?
        LIMIT 1
        """,
        (checkpoint_type, start_utc, end_utc),
    ).fetchone()
    return bool(row and tz)


def _checkpoint_count_today(store: Store) -> int:
    row = store.connection.execute(
        """
        SELECT COUNT(*) AS count FROM scheduler_runs
        WHERE date(started_at) = date('now') AND status IN ('running', 'completed')
        """
    ).fetchone()
    return int(row["count"])


def _expire_stale_locks(store: Store, now: datetime) -> None:
    rows = store.connection.execute("SELECT * FROM scheduler_locks WHERE status = 'active'").fetchall()
    for row in rows:
        if parse_utc_iso(row["expires_at"]) <= now:
            store.connection.execute("UPDATE scheduler_locks SET status = 'expired' WHERE lock_id = ?", (row["lock_id"],))
            store.connection.commit()
            store.append_audit(
                actor_type="orchestrator",
                actor_id="scheduler",
                action="scheduler_lock_expire",
                target_type="scheduler_lock",
                target_id=row["lock_id"],
                summary="Stale scheduler lock expired.",
            )


def _checkpoint_for_time(local_now: datetime) -> tuple[str, str | None]:
    minute = local_now.hour * 60 + local_now.minute
    schedule = [(_minutes(time_text), checkpoint, time_text) for time_text, checkpoint, _summary in CHECKPOINT_SCHEDULE]
    due_checkpoint = "none"
    for scheduled_minute, checkpoint, _time_text in schedule:
        if minute >= scheduled_minute:
            due_checkpoint = checkpoint
    next_checkpoint = next((time_text for scheduled_minute, _checkpoint, time_text in schedule if minute < scheduled_minute), None)
    if minute < _minutes("10:00"):
        return "none", next_checkpoint
    return due_checkpoint, next_checkpoint


def _minutes(value: str) -> int:
    hour, minute = value.split(":", 1)
    return int(hour) * 60 + int(minute)


def _local_now(config: WorkdayConfig, now: datetime | None) -> datetime:
    tz = ZoneInfo(config.timezone)
    if now is None:
        return datetime.now(tz)
    if now.tzinfo is None:
        return now.replace(tzinfo=tz)
    return now.astimezone(tz)
