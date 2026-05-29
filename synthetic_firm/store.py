"""Persistent SQLite store for The Synthetic Firm."""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import replace
from pathlib import Path
from typing import Any
from uuid import uuid4

from synthetic_firm.agent_registry import AgentRegistry
from synthetic_firm.approval import ApprovalRequest, create_approval_request
from synthetic_firm.approval_signing import SignedApprovalDecision, decision_from_json, decision_to_json
from synthetic_firm.audit_log import append_audit_entry, verify_audit_chain
from synthetic_firm.budget import BudgetDecision, BudgetPolicy, BudgetUsage, evaluate_budget
from synthetic_firm.founder_messages import (
    FOUNDER_MESSAGE_STATUSES,
    FounderMessage,
    create_founder_message,
)
from synthetic_firm.human_tasks import HUMAN_TASK_STATUSES, HumanTask, create_human_task
from synthetic_firm.message_bus import CHANNELS, AgentMessage, create_message
from synthetic_firm.migrations import SCHEMA_VERSION, initialize_schema
from synthetic_firm.proposals import (
    SelfImprovementProposal,
    WorkerProposal,
    proposal_to_dict,
)
from synthetic_firm.provider_auth_redaction import redact_auth_text
from synthetic_firm.task import Task, create_task as build_task, transition_task
from synthetic_firm.time_utils import parse_utc_iso, utc_iso


class StoreError(ValueError):
    """Raised when persistent store operations fail closed."""


def tsf_home() -> Path:
    return Path(os.environ.get("TSF_HOME") or Path.home() / ".synthetic-firm").expanduser()


def default_db_path() -> Path:
    return tsf_home() / "state" / "synthetic-firm.sqlite3"


class Store:
    def __new__(cls, path: str | Path | None = None):
        if cls is Store and path is None and os.environ.get("TSF_STORE_BACKEND", "sqlite").strip().lower() == "postgres":
            from synthetic_firm.postgres_repositories import PostgresStore

            return object.__new__(PostgresStore)
        return super().__new__(cls)

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else default_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.parent.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        initialize_schema(self.connection)
        self.connection.execute(
            "INSERT OR IGNORE INTO schema_migrations (version, applied_at) VALUES (?, ?)",
            (SCHEMA_VERSION, utc_iso()),
        )
        self.connection.execute(
            "INSERT OR IGNORE INTO runtime_status (singleton_id, status, updated_at) VALUES (1, 'active', ?)",
            (utc_iso(),),
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def status(self) -> dict[str, Any]:
        tables = self.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        return {
            "path": str(self.path),
            "schema_version": SCHEMA_VERSION,
            "tables": [row["name"] for row in tables],
        }

    def append_audit(
        self,
        *,
        actor_type: str,
        actor_id: str,
        action: str,
        target_type: str,
        target_id: str,
        risk_level: str = "low",
        external_effect: bool = False,
        summary: str,
        metadata: dict[str, Any] | None = None,
    ):
        return append_audit_entry(
            self.connection,
            actor_type=actor_type,
            actor_id=actor_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            risk_level=risk_level,
            external_effect=external_effect,
            summary=summary,
            metadata=metadata,
        )

    def verify_audit(self) -> tuple[bool, str]:
        return verify_audit_chain(self.connection)

    def create_task(
        self,
        *,
        title: str,
        objective: str,
        created_by_agent_id: str,
        assigned_agent_id: str | None = None,
        risk_level: str = "low",
        external_effect: bool = False,
        budget_limit: float | None = None,
        max_steps: int | None = None,
        plain_english_summary: str | None = None,
    ) -> Task:
        task = build_task(
            title=title,
            objective=objective,
            created_by_agent_id=created_by_agent_id,
            assigned_agent_id=assigned_agent_id,
            risk_level=risk_level,
            external_effect=external_effect,
            budget_limit=budget_limit,
            max_steps=max_steps,
        )
        if plain_english_summary:
            task = replace(task, plain_english_summary=plain_english_summary)
        self._insert_task(task)
        self.append_audit(
            actor_type="agent",
            actor_id=created_by_agent_id,
            action="task_create",
            target_type="task",
            target_id=task.task_id,
            risk_level=task.risk_level,
            external_effect=task.external_effect,
            summary=task.plain_english_summary,
        )
        return task

    def get_task(self, task_id: str) -> Task:
        row = self.connection.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        if not row:
            raise StoreError(f"Task not found: {task_id}")
        return _task_from_row(row)

    def list_tasks(self) -> list[Task]:
        rows = self.connection.execute("SELECT * FROM tasks ORDER BY created_at, task_id").fetchall()
        return [_task_from_row(row) for row in rows]

    def update_task_status(self, task_id: str, status: str, *, summary: str | None = None) -> Task:
        current = self.get_task(task_id)
        updated = transition_task(current, status, summary=summary)
        self._replace_task(updated)
        self.append_task_event(task_id, f"Task moved to {updated.status}.", {"status": updated.status})
        self.append_audit(
            actor_type="orchestrator",
            actor_id="store",
            action="task_status_update",
            target_type="task",
            target_id=task_id,
            risk_level=updated.risk_level,
            external_effect=updated.external_effect,
            summary=f"Task status changed to {updated.status}.",
        )
        return updated

    def append_task_event(self, task_id: str, summary: str, metadata: dict[str, Any] | None = None) -> None:
        self.connection.execute(
            "INSERT INTO task_events VALUES (?, ?, ?, ?, ?)",
            (f"event_{uuid4().hex[:12]}", task_id, utc_iso(), summary, _json(metadata or {})),
        )
        self.connection.commit()

    def assign_task(self, task_id: str, agent_id: str) -> Task:
        task = self.get_task(task_id)
        if task.status == "proposed":
            task = transition_task(task, "accepted")
        if task.status == "accepted":
            task = transition_task(task, "assigned")
        else:
            task = transition_task(task, "assigned")
        task = replace(task, assigned_agent_id=agent_id)
        self._replace_task(task)
        self.append_audit(
            actor_type="orchestrator",
            actor_id="store",
            action="task_assign",
            target_type="task",
            target_id=task_id,
            risk_level=task.risk_level,
            external_effect=task.external_effect,
            summary=f"Task assigned to {agent_id}.",
        )
        return task

    def mark_blocked(self, task_id: str, summary: str | None = None) -> Task:
        return self.update_task_status(task_id, "blocked", summary=summary)

    def mark_review_required(self, task_id: str, summary: str | None = None) -> Task:
        return self.update_task_status(task_id, "review_required", summary=summary)

    def mark_approval_required(self, task_id: str, summary: str | None = None) -> Task:
        return self.update_task_status(task_id, "approval_required", summary=summary)

    def complete_task(self, task_id: str, summary: str | None = None) -> Task:
        return self.update_task_status(task_id, "completed", summary=summary)

    def cancel_task(self, task_id: str, summary: str | None = None) -> Task:
        return self.update_task_status(task_id, "cancelled", summary=summary)

    def fail_task(self, task_id: str, summary: str | None = None) -> Task:
        return self.update_task_status(task_id, "failed", summary=summary)

    def create_message(
        self,
        *,
        sender_agent_id: str,
        content: str,
        recipient_agent_id: str | None = None,
        channel: str | None = None,
        task_id: str | None = None,
        message_type: str = "note",
    ) -> AgentMessage:
        _validate_agent(sender_agent_id)
        if recipient_agent_id:
            _validate_agent(recipient_agent_id)
        if channel and channel not in CHANNELS:
            raise StoreError(f"Invalid channel: {channel}")
        if task_id:
            self.get_task(task_id)
        message = create_message(
            sender_agent_id=sender_agent_id,
            recipient_agent_id=recipient_agent_id,
            channel=channel,
            task_id=task_id,
            message_type=message_type,
            content=content,
        )
        self.connection.execute(
            "INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                message.message_id,
                message.sender_agent_id,
                message.recipient_agent_id,
                message.channel,
                message.task_id,
                message.message_type,
                message.content,
                utc_iso(message.created_at),
            ),
        )
        self.connection.commit()
        self.append_audit(
            actor_type="agent",
            actor_id=message.sender_agent_id,
            action="message_create",
            target_type="message",
            target_id=message.message_id,
            summary=f"Message routed through {message.channel or message.recipient_agent_id}.",
        )
        return message

    def list_messages(self, *, task_id: str | None = None, channel: str | None = None) -> list[AgentMessage]:
        query = "SELECT * FROM messages"
        params: list[Any] = []
        clauses: list[str] = []
        if task_id:
            clauses.append("task_id = ?")
            params.append(task_id)
        if channel:
            clauses.append("channel = ?")
            params.append(channel)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at, message_id"
        return [_message_from_row(row) for row in self.connection.execute(query, params).fetchall()]

    def create_approval(self, **kwargs: Any) -> ApprovalRequest:
        approval = create_approval_request(**kwargs)
        self.connection.execute(
            "INSERT INTO approval_requests VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                approval.approval_id,
                approval.task_id,
                approval.agent_id,
                approval.requested_action,
                approval.risk_level,
                int(approval.external_effect),
                approval.plain_english_request,
                approval.guardian_review,
                approval.status,
                utc_iso(approval.created_at),
                None,
            ),
        )
        self.connection.commit()
        self.append_audit(
            actor_type="agent",
            actor_id=approval.agent_id,
            action="approval_create",
            target_type="approval",
            target_id=approval.approval_id,
            risk_level=approval.risk_level,
            external_effect=approval.external_effect,
            summary=approval.plain_english_request,
        )
        return approval

    def get_approval(self, approval_id: str) -> ApprovalRequest:
        row = self.connection.execute(
            "SELECT * FROM approval_requests WHERE approval_id = ?", (approval_id,)
        ).fetchone()
        if not row:
            raise StoreError(f"Approval not found: {approval_id}")
        return _approval_from_row(row)

    def update_approval_status(self, approval_id: str, status: str) -> ApprovalRequest:
        if status not in {"pending", "approved", "denied", "expired", "cancelled", "executed", "failed"}:
            raise StoreError(f"Invalid approval status: {status}")
        approval = self.get_approval(approval_id)
        self.connection.execute(
            "UPDATE approval_requests SET status = ?, decided_at = ? WHERE approval_id = ?",
            (status, utc_iso(), approval_id),
        )
        self.connection.commit()
        self.append_audit(
            actor_type="control",
            actor_id="human",
            action="approval_status_update",
            target_type="approval",
            target_id=approval_id,
            risk_level=approval.risk_level,
            external_effect=approval.external_effect,
            summary=f"Approval status changed to {status}.",
        )
        return self.get_approval(approval_id)

    def persist_approval_decision(self, decision: SignedApprovalDecision) -> None:
        self.connection.execute(
            "INSERT INTO approval_decisions VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                decision.decision_id,
                decision.payload["approval_id"],
                decision_to_json(decision),
                decision.signature,
                int(decision.dry_run),
                int(decision.executable),
                utc_iso(),
            ),
        )
        self.connection.commit()
        self.update_approval_status(decision.payload["approval_id"], decision.payload["decision"])

    def latest_approval_decision(self, approval_id: str) -> SignedApprovalDecision | None:
        row = self.connection.execute(
            """
            SELECT payload_json FROM approval_decisions
            WHERE approval_id = ? ORDER BY created_at DESC LIMIT 1
            """,
            (approval_id,),
        ).fetchone()
        return decision_from_json(row["payload_json"]) if row else None

    def record_budget_usage(
        self,
        *,
        amount_usd: float,
        loop_steps: int,
        tool_calls: int,
        summary: str,
        agent_id: str | None = None,
        task_id: str | None = None,
    ) -> str:
        usage_id = f"budget_{uuid4().hex[:12]}"
        self.connection.execute(
            "INSERT INTO budget_usage VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (usage_id, agent_id, task_id, amount_usd, loop_steps, tool_calls, summary, utc_iso()),
        )
        self.connection.commit()
        self.append_audit(
            actor_type="orchestrator",
            actor_id="budget",
            action="budget_usage_record",
            target_type="budget_usage",
            target_id=usage_id,
            summary=summary,
        )
        return usage_id

    def budget_totals(self, *, agent_id: str | None = None, task_id: str | None = None) -> dict[str, float | int]:
        clauses = ["date(created_at) = date('now')"]
        params: list[Any] = []
        if agent_id:
            clauses.append("agent_id = ?")
            params.append(agent_id)
        if task_id:
            clauses.append("task_id = ?")
            params.append(task_id)
        row = self.connection.execute(
            f"""
            SELECT COALESCE(SUM(amount_usd), 0) AS spend,
                   COALESCE(SUM(loop_steps), 0) AS loop_steps,
                   COALESCE(SUM(tool_calls), 0) AS tool_calls
            FROM budget_usage WHERE {' AND '.join(clauses)}
            """,
            params,
        ).fetchone()
        return {"spend": float(row["spend"]), "loop_steps": int(row["loop_steps"]), "tool_calls": int(row["tool_calls"])}

    def evaluate_persisted_budget(
        self,
        *,
        agent_id: str,
        task_id: str,
        policy: BudgetPolicy,
    ) -> BudgetDecision:
        agent = self.budget_totals(agent_id=agent_id)
        task = self.budget_totals(task_id=task_id)
        company = self.budget_totals()
        decision = evaluate_budget(
            policy,
            BudgetUsage(
                agent_daily_spend_usd=float(agent["spend"]),
                task_spend_usd=float(task["spend"]),
                company_daily_spend_usd=float(company["spend"]),
                loop_steps=int(task["loop_steps"]),
                tool_calls=int(task["tool_calls"]),
            ),
        )
        self.append_audit(
            actor_type="orchestrator",
            actor_id="budget",
            action="budget_check",
            target_type="task",
            target_id=task_id,
            summary=decision.reason,
        )
        return decision

    def save_worker_proposal(self, proposal: WorkerProposal) -> None:
        self.connection.execute(
            "INSERT INTO worker_proposals VALUES (?, ?, ?, ?)",
            (proposal.proposal_id, _json(proposal_to_dict(proposal)), proposal.status, utc_iso(proposal.created_at)),
        )
        self.connection.commit()
        self.append_audit(
            actor_type="agent",
            actor_id=proposal.proposed_by_agent_id,
            action="worker_proposal",
            target_type="worker_proposal",
            target_id=proposal.proposal_id,
            risk_level=proposal.risk_level,
            summary=proposal.business_reason,
        )

    def save_self_improvement_proposal(self, proposal: SelfImprovementProposal) -> None:
        self.connection.execute(
            "INSERT INTO self_improvement_proposals VALUES (?, ?, ?, ?)",
            (proposal.proposal_id, _json(proposal_to_dict(proposal)), proposal.status, utc_iso(proposal.created_at)),
        )
        self.connection.commit()
        self.append_audit(
            actor_type="agent",
            actor_id=proposal.agent_id,
            action="self_improvement_proposal",
            target_type="self_improvement_proposal",
            target_id=proposal.proposal_id,
            risk_level=proposal.risk_level,
            summary=proposal.proposed_change,
        )

    def save_daily_report(self, *, report_date: str, content: str, telegram_summary: str) -> str:
        report_id = f"report_{uuid4().hex[:12]}"
        self.connection.execute(
            "INSERT INTO daily_reports VALUES (?, ?, ?, ?, ?)",
            (report_id, report_date, content, telegram_summary, utc_iso()),
        )
        self.connection.commit()
        self.append_audit(
            actor_type="orchestrator",
            actor_id="report",
            action="report_generation",
            target_type="daily_report",
            target_id=report_id,
            summary=f"Daily report saved for {report_date}.",
        )
        return report_id

    def list_daily_reports(self) -> list[dict[str, str]]:
        rows = self.connection.execute("SELECT * FROM daily_reports ORDER BY created_at DESC").fetchall()
        return [dict(row) for row in rows]

    def create_human_task(self, **kwargs: Any) -> HumanTask:
        task = create_human_task(**kwargs)
        self.connection.execute(
            """
            INSERT INTO human_tasks VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            _human_task_values(task),
        )
        self.connection.commit()
        self.append_audit(
            actor_type="agent",
            actor_id=task.requested_by_agent_id,
            action="human_task_create",
            target_type="human_task",
            target_id=task.human_task_id,
            risk_level=task.risk_level,
            summary=task.public_summary,
        )
        return task

    def get_human_task(self, human_task_id: str) -> HumanTask:
        row = self.connection.execute(
            "SELECT * FROM human_tasks WHERE human_task_id = ?", (human_task_id,)
        ).fetchone()
        if not row:
            raise StoreError(f"Human task not found: {human_task_id}")
        return _human_task_from_row(row)

    def list_human_tasks(self, *, status: str | None = None) -> list[HumanTask]:
        if status:
            rows = self.connection.execute(
                "SELECT * FROM human_tasks WHERE status = ? ORDER BY created_at, human_task_id", (status,)
            ).fetchall()
        else:
            rows = self.connection.execute("SELECT * FROM human_tasks ORDER BY created_at, human_task_id").fetchall()
        return [_human_task_from_row(row) for row in rows]

    def update_human_task(
        self,
        human_task_id: str,
        *,
        status: str | None = None,
        founder_note: str | None = None,
    ) -> HumanTask:
        current = self.get_human_task(human_task_id)
        new_status = status or current.status
        if new_status not in HUMAN_TASK_STATUSES:
            raise StoreError(f"Invalid human task status: {new_status}")
        completed_at = utc_iso() if new_status == "done" and current.completed_at is None else current.completed_at
        note = redact_auth_text(founder_note) if founder_note is not None else current.founder_note
        self.connection.execute(
            """
            UPDATE human_tasks
            SET status = ?, founder_note = ?, completed_at = ?, updated_at = ?
            WHERE human_task_id = ?
            """,
            (new_status, note, completed_at, utc_iso(), human_task_id),
        )
        self.connection.commit()
        self.append_audit(
            actor_type="control",
            actor_id="founder",
            action="human_task_update",
            target_type="human_task",
            target_id=human_task_id,
            risk_level=current.risk_level,
            summary=f"Human task updated to {new_status}.",
        )
        return self.get_human_task(human_task_id)

    def create_founder_message(self, **kwargs: Any) -> FounderMessage:
        message = create_founder_message(**kwargs)
        self.connection.execute(
            """
            INSERT INTO founder_messages VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            _founder_message_values(message),
        )
        self.connection.commit()
        self.append_audit(
            actor_type="founder",
            actor_id="telegram" if message.source == "telegram" else message.source,
            action="founder_message_received",
            target_type="founder_message",
            target_id=message.message_id,
            risk_level="high" if message.priority == "urgent" else "low",
            summary=f"Founder message queued for {message.target_agent}.",
            metadata={"priority": message.priority, "message_type": message.message_type, "status": message.status},
        )
        if message.priority == "urgent":
            self.append_audit(
                actor_type="founder",
                actor_id="telegram",
                action="urgent_founder_message",
                target_type="founder_message",
                target_id=message.message_id,
                risk_level="high",
                summary="Urgent founder message received for Atlas review.",
            )
        return message

    def list_founder_messages(self, *, status: str | None = None) -> list[FounderMessage]:
        if status:
            if status not in FOUNDER_MESSAGE_STATUSES:
                raise StoreError(f"Invalid founder message status: {status}")
            rows = self.connection.execute(
                "SELECT * FROM founder_messages WHERE status = ? ORDER BY received_at, message_id",
                (status,),
            ).fetchall()
        else:
            rows = self.connection.execute(
                "SELECT * FROM founder_messages ORDER BY received_at, message_id"
            ).fetchall()
        return [_founder_message_from_row(row) for row in rows]

    def review_founder_messages(self, *, reviewed_by_agent_id: str = "atlas", limit: int = 20) -> list[FounderMessage]:
        rows = self.connection.execute(
            """
            SELECT * FROM founder_messages
            WHERE status IN ('received', 'queued')
            ORDER BY priority DESC, received_at, message_id
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        reviewed_at = utc_iso()
        reviewed: list[FounderMessage] = []
        for row in rows:
            self.connection.execute(
                """
                UPDATE founder_messages
                SET status = 'reviewed', reviewed_by_agent_id = ?, reviewed_at = ?
                WHERE message_id = ?
                """,
                (reviewed_by_agent_id, reviewed_at, row["message_id"]),
            )
            reviewed.append(_founder_message_from_row({**dict(row), "status": "reviewed", "reviewed_by_agent_id": reviewed_by_agent_id, "reviewed_at": reviewed_at}))
        self.connection.commit()
        if reviewed:
            self.append_audit(
                actor_type="agent",
                actor_id=reviewed_by_agent_id,
                action="founder_message_review",
                target_type="founder_message",
                target_id="batch",
                summary=f"Atlas reviewed {len(reviewed)} queued founder message(s).",
            )
        return reviewed

    def runtime_status(self) -> str:
        row = self.connection.execute("SELECT status FROM runtime_status WHERE singleton_id = 1").fetchone()
        return str(row["status"])

    def set_runtime_status(self, status: str, *, actor_type: str = "control", actor_id: str = "human") -> None:
        if status not in {"active", "paused", "killed"}:
            raise StoreError(f"Invalid runtime status: {status}")
        current = self.runtime_status()
        if current == "killed" and status != "killed":
            raise StoreError("Killed runtime cannot be resumed")
        if actor_type != "control":
            raise StoreError("Only a human/control actor may change runtime status")
        self.connection.execute(
            "UPDATE runtime_status SET status = ?, updated_at = ? WHERE singleton_id = 1",
            (status, utc_iso()),
        )
        self.connection.commit()
        self.append_audit(
            actor_type=actor_type,
            actor_id=actor_id,
            action=f"runtime_{status}",
            target_type="runtime_status",
            target_id="company",
            risk_level="high" if status == "killed" else "medium",
            summary=f"Runtime status changed to {status}.",
        )

    def _insert_task(self, task: Task) -> None:
        self.connection.execute(
            "INSERT INTO tasks VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            _task_values(task),
        )
        self.connection.commit()

    def _replace_task(self, task: Task) -> None:
        self.connection.execute(
            "REPLACE INTO tasks VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            _task_values(task),
        )
        self.connection.commit()


def init_store(path: str | Path | None = None) -> Store:
    return Store(path)


def _task_values(task: Task) -> tuple[Any, ...]:
    return (
        task.task_id,
        task.title,
        task.objective,
        task.assigned_agent_id,
        task.created_by_agent_id,
        task.risk_level,
        task.status,
        int(task.external_effect),
        task.budget_limit,
        task.max_steps,
        utc_iso(task.created_at),
        utc_iso(task.updated_at),
        task.plain_english_summary,
    )


def _human_task_values(task: HumanTask) -> tuple[Any, ...]:
    return (
        task.human_task_id,
        task.requested_by_agent_id,
        task.related_task_id,
        task.title,
        task.plain_english_request,
        task.reason,
        task.priority,
        task.deadline,
        task.cost_estimate,
        task.risk_level,
        task.public_summary,
        task.private_details_redacted,
        task.status,
        task.created_at,
        task.updated_at,
        task.completed_at,
        task.founder_note,
    )


def _founder_message_values(message: FounderMessage) -> tuple[Any, ...]:
    return (
        message.message_id,
        message.source,
        message.received_at,
        message.sender,
        message.target_agent,
        message.priority,
        message.message_type,
        message.content,
        message.status,
        message.reviewed_by_agent_id,
        message.reviewed_at,
        message.related_human_task_id,
        message.related_task_id,
    )


def _task_from_row(row: sqlite3.Row) -> Task:
    return Task(
        task_id=row["task_id"],
        title=row["title"],
        objective=row["objective"],
        assigned_agent_id=row["assigned_agent_id"],
        created_by_agent_id=row["created_by_agent_id"],
        risk_level=row["risk_level"],
        status=row["status"],
        external_effect=bool(row["external_effect"]),
        budget_limit=row["budget_limit"],
        max_steps=row["max_steps"],
        created_at=parse_utc_iso(row["created_at"]),
        updated_at=parse_utc_iso(row["updated_at"]),
        plain_english_summary=row["plain_english_summary"],
    )


def _message_from_row(row: sqlite3.Row) -> AgentMessage:
    return AgentMessage(
        message_id=row["message_id"],
        sender_agent_id=row["sender_agent_id"],
        recipient_agent_id=row["recipient_agent_id"],
        channel=row["channel"],
        task_id=row["task_id"],
        message_type=row["message_type"],
        content=row["content"],
        created_at=parse_utc_iso(row["created_at"]),
    )


def _approval_from_row(row: sqlite3.Row) -> ApprovalRequest:
    return ApprovalRequest(
        approval_id=row["approval_id"],
        task_id=row["task_id"],
        agent_id=row["agent_id"],
        requested_action=row["requested_action"],
        risk_level=row["risk_level"],
        external_effect=bool(row["external_effect"]),
        plain_english_request=row["plain_english_request"],
        guardian_review=row["guardian_review"],
        status=row["status"],
        created_at=parse_utc_iso(row["created_at"]),
        decided_at=parse_utc_iso(row["decided_at"]) if row["decided_at"] else None,
    )


def _human_task_from_row(row: sqlite3.Row) -> HumanTask:
    return HumanTask(
        human_task_id=row["human_task_id"],
        requested_by_agent_id=row["requested_by_agent_id"],
        related_task_id=row["related_task_id"],
        title=row["title"],
        plain_english_request=row["plain_english_request"],
        reason=row["reason"],
        priority=row["priority"],
        deadline=row["deadline"],
        cost_estimate=row["cost_estimate"],
        risk_level=row["risk_level"],
        public_summary=row["public_summary"],
        private_details_redacted=row["private_details_redacted"],
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        completed_at=row["completed_at"],
        founder_note=row["founder_note"],
    )


def _founder_message_from_row(row: Any) -> FounderMessage:
    return FounderMessage(
        message_id=row["message_id"],
        source=row["source"],
        received_at=row["received_at"],
        sender=row["sender"],
        target_agent=row["target_agent"],
        priority=row["priority"],
        message_type=row["message_type"],
        content=row["content"],
        status=row["status"],
        reviewed_by_agent_id=row["reviewed_by_agent_id"],
        reviewed_at=row["reviewed_at"],
        related_human_task_id=row["related_human_task_id"],
        related_task_id=row["related_task_id"],
    )


def _json(value: dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True)


def _validate_agent(agent_id: str) -> None:
    try:
        AgentRegistry.from_file().get(agent_id)
    except Exception as exc:
        raise StoreError(f"Invalid agent: {agent_id}") from exc
