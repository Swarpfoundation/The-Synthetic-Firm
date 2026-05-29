"""Read-only public progress snapshot export for The Synthetic Firm."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from synthetic_firm.agent_registry import AgentProfile, AgentRegistry
from synthetic_firm.cost_ledger import budget_private_report, budget_public_summary
from synthetic_firm.deployment import deployment_record_to_dict, latest_credential_status_records, list_deployment_records
from synthetic_firm.execution_queue import list_queue
from synthetic_firm.founder_messages import founder_message_to_dict
from synthetic_firm.human_tasks import human_task_to_dict
from synthetic_firm.provider_auth_redaction import redact_auth_text
from synthetic_firm.store import Store
from synthetic_firm.store_backend import db_status
from synthetic_firm.time_utils import utc_iso
from synthetic_firm.workday import evaluate_workday, load_workday_config

SCHEMA_VERSION = "control-room.v1"
AGENT_ROLES = {
    "atlas": "Supervisor / CEO",
    "scout": "Research & Opportunity",
    "forge": "Builder / Product",
    "pulse": "Growth / Sales",
    "sentinel": "Guardian / QA / Compliance",
}
AGENT_NAMES = {
    "atlas": "Atlas",
    "scout": "Scout",
    "forge": "Forge",
    "pulse": "Pulse",
    "sentinel": "Sentinel",
}
AGENT_ORDER = ("atlas", "scout", "forge", "pulse", "sentinel")
ACTIVE_TASK_STATUSES = {"assigned", "in_progress", "review_required", "approval_required", "blocked"}
STATUS_TO_EVENT = {
    "proposed": "task.created",
    "assigned": "task.assigned",
    "in_progress": "task.started",
    "blocked": "task.blocked",
    "review_required": "task.review_required",
    "approval_required": "approval.requested",
    "completed": "task.completed",
}
AUDIENCES = frozenset({"public", "founder"})
PRIVATE_TEXT_PATTERNS = (
    re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}"),
    re.compile(r"https?://\S+"),
)


def build_control_room_snapshot(store: Store | None = None, *, audience: str = "public") -> dict[str, Any]:
    """Build a frontend-safe, read-only public progress state snapshot."""

    if audience not in AUDIENCES:
        raise ValueError(f"Unsupported progress snapshot audience: {audience}")
    own_store = store is None
    store = store or Store()
    try:
        tasks = store.list_tasks()
        approvals = _list_approvals(store)
        queue = list_queue(store)
        messages = store.list_messages()
        founder_messages = store.list_founder_messages()
        reports = store.list_daily_reports()
        human_tasks = store.list_human_tasks()
        registry = AgentRegistry.from_file()
        audit_verified, audit_summary = store.verify_audit()
        last_sequence = _last_audit_sequence(store)
        runtime_status = store.runtime_status()
        workday = _workday_snapshot()
        budget = _budget_snapshot(store, registry)
        public_reports = _public_reports(reports)
        public_report = _public_daily_report(tasks, human_tasks, public_reports, runtime_status, workday)
        autonomous_workday = _autonomous_workday_snapshot(store)
        return {
            "schemaVersion": SCHEMA_VERSION,
            "audience": audience,
            "dataMode": "real_snapshot",
            "truthfulness": "real_runtime_data_only",
            "generatedAt": utc_iso(),
            "source": {
                "label": "TSF public progress snapshot" if audience == "public" else "TSF founder operations snapshot",
                "mode": "read_only",
            },
            "runtime": {
                "status": runtime_status,
                "summary": f"The Synthetic Firm runtime is {runtime_status}.",
            },
            "workday": workday,
            "autonomousWorkday": autonomous_workday,
            "scheduler": _scheduler_snapshot(store),
            "storage": _storage_snapshot(),
            "storeBackendPublicStatus": _storage_snapshot()["storeBackendPublicStatus"],
            "schedulerPublicStatus": _scheduler_public_status(store),
            "lastSchedulerCheckpoint": _last_scheduler_checkpoint(store),
            "lastAtlasReportAt": _last_atlas_report_at(reports),
            "publicEmptyStateReason": _public_empty_state_reason(tasks, human_tasks, public_reports),
            "deploymentSummary": _deployment_summary(store),
            "agents": _agents_snapshot(registry, tasks, approvals),
            "tasks": [_task_snapshot(task, audience=audience) for task in tasks],
            "messages": _messages_summary(messages, audience=audience),
            "approvals": [_approval_snapshot(row, audience=audience) for row in approvals],
            "executionQueue": [_queue_snapshot(item) for item in queue],
            "budget": budget,
            "infrastructureBudget": _infrastructure_budget_snapshot(store, audience=audience),
            "reports": [_report_snapshot(report) for report in (public_reports if audience == "public" else reports)[:10]],
            "publicDailyReport": public_report,
            "privateFounderReport": _private_founder_report(store, tasks, human_tasks, reports, runtime_status, workday)
            if audience == "founder"
            else None,
            "humanTasks": [_human_task_snapshot(task, audience=audience) for task in human_tasks],
            "humanTaskSummary": _human_task_summary(human_tasks, audience=audience),
            "founderMessageSummary": _founder_message_summary(founder_messages, audience=audience),
            "agentProgressSummary": _agent_progress_summary(tasks),
            "audit": {
                "verified": audit_verified,
                "lastSequence": last_sequence,
                "summary": _safe(audit_summary),
            },
            "events": _events_snapshot(tasks, approvals, messages, reports, queue, runtime_status, human_tasks),
        }
    finally:
        if own_store:
            store.close()


def export_control_room_state(
    *,
    output: str | Path | None = None,
    stdout: bool = False,
    audience: str = "public",
) -> str:
    snapshot = build_control_room_snapshot(audience=audience)
    payload = json.dumps(snapshot, indent=2, sort_keys=True) + "\n"
    if output:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload, encoding="utf-8")
    if stdout:
        return payload
    return payload


def _workday_snapshot() -> dict[str, Any]:
    config = load_workday_config()
    status = evaluate_workday(config)
    phase = _phase_from_time(status.now.strftime("%H:%M"), status.inside_work_hours)
    return {
        "timezone": status.timezone,
        "insideWorkday": status.inside_work_hours,
        "phase": phase,
        "summary": _safe(status.plain_english()),
    }


def _autonomous_workday_snapshot(store: Store) -> dict[str, Any]:
    row = store.connection.execute(
        """
        SELECT * FROM workdays
        WHERE workday_date = date('now') OR status IN ('active', 'paused', 'closing')
        ORDER BY started_at DESC LIMIT 1
        """
    ).fetchone()
    if not row:
        return {
            "status": "not_started",
            "summary": "No autonomous workday started today.",
            "cycleCount": 0,
            "workdayId": None,
            "atlasPlanId": None,
            "publicReportId": None,
            "privateReportId": None,
        }
    return {
        "status": row["status"],
        "summary": _safe(row["summary"], public=True),
        "cycleCount": int(row["cycle_count"]),
        "workdayId": row["workday_id"],
        "atlasPlanId": row["atlas_plan_id"],
        "publicReportId": row["public_report_id"],
        "privateReportId": row["private_report_id"],
        "lastCycleAt": row["last_cycle_at"],
    }


def _scheduler_snapshot(store: Store) -> dict[str, Any]:
    row = store.connection.execute(
        "SELECT * FROM scheduler_runs ORDER BY started_at DESC LIMIT 1"
    ).fetchone()
    next_checkpoint = None
    try:
        from synthetic_firm.scheduler import scheduler_dry_run_plan

        current = scheduler_dry_run_plan()["current_evaluation"]
        next_checkpoint = current.get("next_checkpoint")
    except Exception:
        next_checkpoint = None
    workday_window = _workday_window_label()
    if not row:
        return {
            "status": "not_started",
            "lastCheckpointAt": None,
            "lastCheckpointType": None,
            "nextCheckpoint": next_checkpoint,
            "workdayWindow": workday_window,
            "summary": "No autonomous scheduler checkpoint has run yet.",
        }
    return {
        "status": row["status"],
        "lastCheckpointAt": row["ended_at"] or row["started_at"],
        "lastCheckpointType": row["checkpoint_type"],
        "nextCheckpoint": next_checkpoint,
        "workdayWindow": workday_window,
        "summary": _safe(row["summary"], public=True),
    }


def _workday_window_label() -> str:
    try:
        config = load_workday_config()
        return f"{config.start.strftime('%H:%M')}-{config.end.strftime('%H:%M')} {config.timezone}"
    except Exception:
        return "09:00-16:00 Europe/Paris"


def _storage_snapshot() -> dict[str, Any]:
    try:
        status = db_status()
    except Exception as exc:  # noqa: BLE001
        return {
            "storeBackendPublicStatus": "postgres_unavailable",
            "summary": _safe(str(exc), public=True),
        }
    backend = status.get("backend")
    public_status = status.get("publicStatus") or ("sqlite_preview" if backend == "sqlite" else "postgres_unavailable")
    return {
        "storeBackendPublicStatus": public_status,
        "backend": backend,
        "repositoryMode": status.get("repositoryMode"),
        "connected": bool(status.get("connected")),
        "schemaVersion": status.get("schemaVersion"),
        "summary": _safe(str(status.get("safeSummary", "Store status loaded.")), public=True),
    }


def _scheduler_public_status(store: Store) -> str:
    row = store.connection.execute("SELECT status FROM scheduler_runs ORDER BY started_at DESC LIMIT 1").fetchone()
    if not row:
        return "not_started"
    return str(row["status"])


def _last_scheduler_checkpoint(store: Store) -> str | None:
    row = store.connection.execute("SELECT ended_at, started_at FROM scheduler_runs ORDER BY started_at DESC LIMIT 1").fetchone()
    if not row:
        return None
    return row["ended_at"] or row["started_at"]


def _last_atlas_report_at(reports: list[dict[str, str]]) -> str | None:
    if not reports:
        return None
    return max(str(report["created_at"]) for report in reports if report.get("created_at"))


def _public_empty_state_reason(tasks: list[Any], human_tasks: list[Any], public_reports: list[dict[str, str]]) -> str | None:
    if tasks or human_tasks or public_reports:
        return None
    return "No persisted public runtime work, reports, or HumanTasks exist yet."


def _deployment_summary(store: Store) -> dict[str, Any]:
    records = list_deployment_records(store, limit=5)
    latest = records[0] if records else None
    latest_preview = next((record.preview_url for record in records if record.preview_url and record.state == "preview_deployed"), None)
    blocked = None if latest and latest.state == "preview_deployed" else next(
        (deployment_record_to_dict(record, public=True)["blockedReason"] for record in records if record.blocked_reason),
        None,
    )
    latest_health = _deployment_health_status(latest)
    credential_status = latest_credential_status_records(store)
    return {
        "latestState": latest.state if latest else "not_started",
        "latestTarget": latest.target if latest else None,
        "latestEnvironment": latest.environment if latest else None,
        "latestPreviewUrl": latest_preview,
        "backendHealthPublicStatus": latest_health,
        "deploymentBlockedReason": _safe(blocked, public=True) if blocked else None,
        "lastCheckedAt": _latest_deployment_check_time(records, credential_status),
        "credentialStatus": credential_status,
        "summary": _safe(latest.public_summary, public=True) if latest else "No public deployment activity yet.",
        "history": [deployment_record_to_dict(record, public=True) for record in records],
    }


def _infrastructure_budget_snapshot(store: Store, *, audience: str) -> dict[str, Any]:
    try:
        public = budget_public_summary(store)
        if audience == "founder":
            public["privateReport"] = budget_private_report(store)
        return _sanitize_mapping(public, public=audience == "public")
    except Exception as exc:  # noqa: BLE001
        return {
            "monthlyInfrastructureBudgetEur": 100.0,
            "status": "tracking",
            "unknownCostCount": 1,
            "summary": _safe(f"Infrastructure budget tracking needs setup: {exc}", public=True),
        }


def _deployment_health_status(record: Any | None) -> str:
    if not record:
        return "not_checked"
    for check in record.checks:
        if check.name == "preview health check":
            return "healthy" if check.passed else "health_check_failed"
    if record.state == "health_check_failed":
        return "health_check_failed"
    return "not_checked"


def _latest_deployment_check_time(records: list[Any], credential_status: dict[str, Any]) -> str | None:
    candidates = [record.updated_at for record in records]
    candidates.extend(str(value.get("lastCheckedAt")) for value in credential_status.values() if value.get("lastCheckedAt"))
    return max(candidates) if candidates else None


def _phase_from_time(time_text: str, inside_workday: bool) -> str:
    if not inside_workday:
        return "closed"
    if time_text < "10:00":
        return "planning"
    if time_text < "15:00":
        return "execution"
    if time_text < "16:00":
        return "review"
    return "report"


def _agents_snapshot(registry: AgentRegistry, tasks: list[Any], approvals: list[Any]) -> list[dict[str, Any]]:
    pending_by_agent = {row["agent_id"] for row in approvals if row["status"] == "pending"}
    active_tasks = [task for task in tasks if task.status in ACTIVE_TASK_STATUSES and task.assigned_agent_id]
    agents = []
    profiles = {profile.agent_id: profile for profile in registry.list()}
    for agent_id in AGENT_ORDER:
        profile = profiles[agent_id]
        task = next((candidate for candidate in active_tasks if candidate.assigned_agent_id == profile.agent_id), None)
        attention = _attention_level(profile.agent_id, task, pending_by_agent)
        agents.append(
            {
                "id": profile.agent_id,
                "name": AGENT_NAMES.get(profile.agent_id, profile.display_name.split("/", 1)[0].strip()),
                "role": AGENT_ROLES.get(profile.agent_id, profile.display_name),
                "status": _agent_status(task, attention),
                "currentTaskId": task.task_id if task else None,
                "currentTaskTitle": _safe(task.title) if task else None,
                "attentionLevel": attention,
            }
        )
    return agents


def _attention_level(agent_id: str, task: Any | None, pending_by_agent: set[str]) -> str:
    if task and task.status == "blocked":
        return "blocked"
    if task and task.status == "approval_required":
        return "approval_required"
    if agent_id in pending_by_agent:
        return "approval_required"
    if task and task.risk_level in {"high", "critical"}:
        return "warning"
    return "normal"


def _agent_status(task: Any | None, attention: str) -> str:
    if attention == "blocked":
        return "blocked"
    if attention == "approval_required":
        return "approval_required"
    if not task:
        return "idle"
    if task.status == "review_required":
        return "reviewing"
    if task.assigned_agent_id == "scout":
        return "researching"
    if task.assigned_agent_id == "forge":
        return "building"
    if task.assigned_agent_id == "pulse":
        return "drafting"
    return "planning"


def _task_snapshot(task: Any, *, audience: str) -> dict[str, Any]:
    return {
        "id": task.task_id,
        "title": _safe(task.title, public=audience == "public"),
        "objective": _safe(task.objective, public=audience == "public"),
        "assignedAgentId": task.assigned_agent_id,
        "createdByAgentId": task.created_by_agent_id,
        "riskLevel": task.risk_level,
        "status": task.status,
        "externalEffect": task.external_effect,
        "budgetLimit": task.budget_limit,
        "maxSteps": task.max_steps,
        "createdAt": task.created_at.isoformat(),
        "updatedAt": task.updated_at.isoformat(),
        "plainEnglishSummary": _safe(task.plain_english_summary, public=audience == "public"),
    }


def _list_approvals(store: Store) -> list[Any]:
    return store.connection.execute(
        "SELECT * FROM approval_requests ORDER BY created_at, approval_id"
    ).fetchall()


def _approval_snapshot(row: Any, *, audience: str) -> dict[str, Any]:
    return {
        "id": row["approval_id"],
        "taskId": row["task_id"],
        "agentId": row["agent_id"],
        "requestedAction": _safe(row["requested_action"], public=audience == "public"),
        "riskLevel": row["risk_level"],
        "externalEffect": bool(row["external_effect"]),
        "plainEnglishRequest": _safe(row["plain_english_request"], public=audience == "public"),
        "sentinelReview": _safe(row["guardian_review"] or "", public=audience == "public"),
        "status": row["status"],
        "createdAt": row["created_at"],
        "decidedAt": row["decided_at"],
    }


def _messages_summary(messages: list[Any], *, audience: str) -> dict[str, Any]:
    recent = list(messages)[-10:]
    return {
        "count": len(messages),
        "recent": [
            {
                "id": message.message_id,
                "senderAgentId": message.sender_agent_id,
                "recipientAgentId": message.recipient_agent_id,
                "channel": message.channel,
                "taskId": message.task_id,
                "messageType": message.message_type,
                "summary": _safe(message.content, limit=180, public=audience == "public"),
                "createdAt": message.created_at.isoformat(),
            }
            for message in recent
        ],
    }


def _queue_snapshot(item: Any) -> dict[str, Any]:
    return {
        "id": item.queue_id,
        "taskId": item.task_id,
        "agentId": item.agent_id,
        "action": _safe(item.action),
        "externalEffect": item.external_effect,
        "approvalId": item.approval_id,
        "status": item.status,
        "resultSummary": _safe(item.result_summary or ""),
        "createdAt": item.created_at,
        "updatedAt": item.updated_at,
    }


def _budget_snapshot(store: Store, registry: AgentRegistry) -> dict[str, Any]:
    company = store.budget_totals()
    per_agent = []
    profiles_by_id = {profile.agent_id: profile for profile in registry.list()}
    profiles = [profiles_by_id[agent_id] for agent_id in AGENT_ORDER]
    daily_limit = _company_daily_limit(profiles)
    for profile in profiles:
        usage = store.budget_totals(agent_id=profile.agent_id)
        per_agent.append(
            {
                "agentId": profile.agent_id,
                "dailyLimit": profile.budget.daily_usd,
                "usage": float(usage["spend"]),
                "loopSteps": int(usage["loop_steps"]),
                "toolCalls": int(usage["tool_calls"]),
            }
        )
    return {
        "companyDailyLimit": daily_limit,
        "companyUsage": float(company["spend"]),
        "loopSteps": int(company["loop_steps"]),
        "toolCalls": int(company["tool_calls"]),
        "warningThresholds": [0.5, 0.8, 0.95, 1.0],
        "perAgent": per_agent,
    }


def _company_daily_limit(profiles: list[AgentProfile]) -> float:
    try:
        config = load_workday_config()
        if config.company_daily_budget_usd is not None:
            return config.company_daily_budget_usd
    except Exception:
        pass
    return sum(profile.budget.daily_usd for profile in profiles)


def _report_snapshot(report: dict[str, str]) -> dict[str, Any]:
    return {
        "id": report["report_id"],
        "date": report["report_date"],
        "summary": _safe(report["telegram_summary"] or report["content"], limit=800),
        "createdAt": report["created_at"],
    }


def _public_reports(reports: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        report
        for report in reports
        if "Private Founder Report" not in str(report["content"])
        and "Private Founder Report" not in str(report["telegram_summary"])
    ]


def _human_task_snapshot(task: Any, *, audience: str) -> dict[str, Any]:
    payload = human_task_to_dict(task, audience=audience)
    if audience == "public":
        payload = {
            "humanTaskId": task.human_task_id,
            "requestedByAgentId": task.requested_by_agent_id,
            "relatedTaskId": task.related_task_id,
            "priority": task.priority,
            "riskLevel": task.risk_level,
            "publicSummary": _safe(task.public_summary, public=True),
            "status": task.status,
            "createdAt": task.created_at,
            "updatedAt": task.updated_at,
            "completedAt": task.completed_at,
        }
    return _sanitize_mapping(payload, public=audience == "public")


def _human_task_summary(human_tasks: list[Any], *, audience: str) -> dict[str, Any]:
    pending = [task for task in human_tasks if task.status == "pending"]
    blocked = [task for task in human_tasks if task.status == "blocked"]
    done = [task for task in human_tasks if task.status == "done"]
    summaries = [
        {
            "humanTaskId": task.human_task_id,
            "status": task.status,
            "publicSummary": _safe(task.public_summary, public=True),
        }
        for task in human_tasks[:20]
    ]
    payload: dict[str, Any] = {
        "pendingCount": len(pending),
        "blockedCount": len(blocked),
        "doneCount": len(done),
        "publicSummaries": summaries,
        "summary": "No public human tasks pending." if not pending else f"{len(pending)} founder task(s) pending.",
    }
    if audience == "founder":
        payload["privateItems"] = [_human_task_snapshot(task, audience="founder") for task in human_tasks[:20]]
    return payload


def _founder_message_summary(messages: list[Any], *, audience: str) -> dict[str, Any]:
    queued = [message for message in messages if message.status in {"received", "queued"}]
    reviewed = [message for message in messages if message.status == "reviewed"]
    urgent = [message for message in messages if message.priority == "urgent"]
    payload: dict[str, Any] = {
        "queuedCount": len(queued),
        "reviewedCount": len(reviewed),
        "urgentCount": len(urgent),
        "summary": "No founder messages queued for Atlas." if not queued else f"{len(queued)} founder message(s) queued for Atlas.",
    }
    if audience == "founder":
        payload["privateItems"] = [founder_message_to_dict(message, public=False) for message in messages[:20]]
    return _sanitize_mapping(payload, public=audience == "public")


def _agent_progress_summary(tasks: list[Any]) -> list[dict[str, Any]]:
    result = []
    for agent_id in AGENT_ORDER:
        assigned = [task for task in tasks if task.assigned_agent_id == agent_id or task.created_by_agent_id == agent_id]
        result.append(
            {
                "agentId": agent_id,
                "name": AGENT_NAMES[agent_id],
                "completedCount": len([task for task in assigned if task.status == "completed"]),
                "inProgressCount": len([task for task in assigned if task.status in ACTIVE_TASK_STATUSES]),
                "blockedCount": len([task for task in assigned if task.status == "blocked"]),
                "summary": _agent_public_summary(agent_id, assigned),
            }
        )
    return result


def _agent_public_summary(agent_id: str, tasks: list[Any]) -> str:
    active = [task for task in tasks if task.status in ACTIVE_TASK_STATUSES]
    completed = [task for task in tasks if task.status == "completed"]
    if active:
        return _safe(f"{AGENT_NAMES[agent_id]} is working on {active[0].title}.", public=True)
    if completed:
        return _safe(f"{AGENT_NAMES[agent_id]} completed {completed[-1].title}.", public=True)
    return f"{AGENT_NAMES[agent_id]} has no public task activity yet."


def _public_daily_report(
    tasks: list[Any],
    human_tasks: list[Any],
    reports: list[dict[str, str]],
    runtime_status: str,
    workday: dict[str, Any],
) -> dict[str, Any]:
    completed = [_safe(task.title, public=True) for task in tasks if task.status == "completed"]
    in_progress = [_safe(task.title, public=True) for task in tasks if task.status in ACTIVE_TASK_STATUSES]
    blocked = [_safe(task.title, public=True) for task in tasks if task.status == "blocked"]
    pending_human = [task for task in human_tasks if task.status == "pending"]
    what_happened = [
        item["summary"]
        for item in _agent_progress_summary(tasks)
        if not str(item["summary"]).endswith("has no public task activity yet.")
    ]
    latest = reports[0]["content"] if reports else "No public report generated yet."
    return {
        "type": "public_daily_report",
        "title": "The Synthetic Firm - Daily Public Report",
        "date": str(workday.get("date") or utc_iso()[:10]),
        "runtime": runtime_status,
        "workdayPhase": workday["phase"],
        "whatHappenedToday": what_happened,
        "completed": completed,
        "inProgress": in_progress,
        "blocked": blocked,
        "humanTasks": [
            {
                "status": task.status,
                "publicSummary": _safe(task.public_summary, public=True),
            }
            for task in human_tasks[:20]
        ],
        "notes": [_safe(latest, limit=800, public=True)],
        "risksAndLessons": ["No public risks or lessons recorded yet."] if not blocked else blocked,
        "nextLikelyWork": ["No public next steps recorded yet."] if not in_progress else in_progress,
        "truthfulness": "Based on real TSF runtime data. No mock data. No fabricated progress.",
        "emptyState": {
            "completed": "No completed tasks today." if not completed else "",
            "humanTasks": "No public human tasks pending." if not pending_human else "",
        },
    }


def _private_founder_report(
    store: Store,
    tasks: list[Any],
    human_tasks: list[Any],
    reports: list[dict[str, str]],
    runtime_status: str,
    workday: dict[str, Any],
) -> dict[str, Any]:
    return {
        "type": "private_founder_report",
        "date": str(workday.get("date") or utc_iso()[:10]),
        "runtime": runtime_status,
        "exactHumanTasks": [_human_task_snapshot(task, audience="founder") for task in human_tasks[:50]],
        "privateBlockers": [_safe(task.plain_english_summary, public=False) for task in tasks if task.status == "blocked"],
        "operationalNotes": [_safe(report["content"], limit=1000, public=False) for report in reports[:5]],
        "infrastructureBudget": budget_private_report(store),
        "truthfulness": "Based on real TSF runtime data. No mock data. No fabricated progress.",
    }


def _last_audit_sequence(store: Store) -> int:
    row = store.connection.execute("SELECT COALESCE(MAX(sequence_number), 0) AS seq FROM audit_log").fetchone()
    return int(row["seq"])


def _events_snapshot(
    tasks: list[Any],
    approvals: list[Any],
    messages: list[Any],
    reports: list[dict[str, str]],
    queue: list[Any],
    runtime_status: str,
    human_tasks: list[Any],
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = [
        {
            "id": "runtime-current",
            "type": f"runtime.{runtime_status}",
            "agentId": None,
            "message": f"Runtime is {runtime_status}.",
            "timestamp": utc_iso(),
            "metadata": {"runtimeStatus": runtime_status},
        }
    ]
    for task in tasks:
        events.append(
            {
                "id": f"task-{task.task_id}",
                "type": STATUS_TO_EVENT.get(task.status, "task.created"),
                "agentId": task.assigned_agent_id or task.created_by_agent_id,
                "message": _safe(f"{task.title}: {task.plain_english_summary}", limit=220),
                "timestamp": task.updated_at.isoformat(),
                "metadata": {"taskId": task.task_id, "status": task.status},
            }
        )
    for row in approvals:
        events.append(
            {
                "id": f"approval-{row['approval_id']}",
                "type": _approval_event_type(row["status"]),
                "agentId": row["agent_id"],
                "message": _safe(f"Approval {row['approval_id']}: {row['requested_action']}", limit=220),
                "timestamp": row["decided_at"] or row["created_at"],
                "metadata": {"approvalId": row["approval_id"], "status": row["status"]},
            }
        )
    for message in messages[-10:]:
        events.append(
            {
                "id": f"message-{message.message_id}",
                "type": "message.sent",
                "agentId": message.sender_agent_id,
                "message": _safe(message.content, limit=160),
                "timestamp": message.created_at.isoformat(),
                "metadata": {"messageId": message.message_id, "channel": message.channel},
            }
        )
    for item in queue[-10:]:
        events.append(
            {
                "id": f"queue-{item.queue_id}",
                "type": "message.sent",
                "agentId": item.agent_id,
                "message": _safe(f"Execution queue item {item.status}: {item.action}", limit=180),
                "timestamp": item.updated_at,
                "metadata": {"queueId": item.queue_id, "status": item.status},
            }
        )
    for report in reports[:5]:
        events.append(
            {
                "id": f"report-{report['report_id']}",
                "type": "daily_report.generated",
                "agentId": "sentinel",
                "message": _safe(f"Daily report saved for {report['report_date']}.", limit=180),
                "timestamp": report["created_at"],
                "metadata": {"reportId": report["report_id"]},
            }
        )
    for task in human_tasks[:20]:
        events.append(
            {
                "id": f"human-task-{task.human_task_id}",
                "type": "human_task.updated",
                "agentId": task.requested_by_agent_id,
                "message": _safe(task.public_summary, limit=180, public=True),
                "timestamp": task.updated_at,
                "metadata": {"humanTaskId": task.human_task_id, "status": task.status},
            }
        )
    events.sort(key=lambda event: str(event["timestamp"]), reverse=True)
    return events[:50]


def _approval_event_type(status: str) -> str:
    if status == "approved":
        return "approval.approved"
    if status == "denied":
        return "approval.denied"
    return "approval.requested"


def _sanitize_mapping(value: dict[str, Any], *, public: bool) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, item in value.items():
        if isinstance(item, str):
            sanitized[key] = _safe(item, public=public)
        else:
            sanitized[key] = item
    return sanitized


def _safe(value: object, *, limit: int = 400, public: bool = False) -> str:
    text = redact_auth_text(value).replace("\x00", "")
    if public:
        for pattern in PRIVATE_TEXT_PATTERNS:
            replacement = "[redacted-email]" if "@" in pattern.pattern else "[redacted-url]"
            text = pattern.sub(replacement, text)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"
