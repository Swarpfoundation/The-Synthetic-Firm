"""Postgres migration foundation for TSF runtime state.

This module intentionally avoids importing a Postgres driver unless an apply or
connectivity check needs it. Unit tests and local development remain SQLite by
default.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from synthetic_firm.db_redaction import redact_db_text
from synthetic_firm.migrations import SCHEMA_VERSION


POSTGRES_SCHEMA_VERSION = SCHEMA_VERSION


@dataclass(frozen=True)
class PostgresMigrationPlan:
    schema_version: int
    statements: tuple[str, ...]
    destructive: bool
    summary: str

    def to_dict(self, *, include_sql: bool = True) -> dict[str, object]:
        return {
            "schemaVersion": self.schema_version,
            "statementCount": len(self.statements),
            "destructive": self.destructive,
            "summary": self.summary,
            "statements": list(self.statements) if include_sql else [],
        }


def postgres_migration_plan() -> PostgresMigrationPlan:
    statements = tuple(_postgres_statements())
    destructive = any(_is_destructive(statement) for statement in statements)
    return PostgresMigrationPlan(
        schema_version=POSTGRES_SCHEMA_VERSION,
        statements=statements,
        destructive=destructive,
        summary="Postgres migration plan is non-destructive and idempotent.",
    )


def verify_postgres_migration_plan(plan: PostgresMigrationPlan | None = None) -> tuple[bool, str]:
    plan = plan or postgres_migration_plan()
    if plan.destructive:
        return False, "Postgres migration plan contains destructive SQL and is blocked."
    required = {"tasks", "audit_log", "human_tasks", "scheduler_runs", "deployment_records"}
    present = {
        token.strip('"')
        for statement in plan.statements
        for token in _table_name_from_create(statement)
    }
    missing = sorted(required - present)
    if missing:
        return False, f"Postgres migration plan is missing required tables: {', '.join(missing)}"
    return True, "Postgres migration plan verified."


def apply_postgres_migrations(database_url: str) -> dict[str, object]:
    """Apply non-destructive migrations using psycopg when available."""

    plan = postgres_migration_plan()
    ok, summary = verify_postgres_migration_plan(plan)
    if not ok:
        return {"applied": False, "summary": summary}
    try:
        import psycopg  # type: ignore[import-not-found]
    except Exception:
        return {
            "applied": False,
            "summary": "Postgres driver is unavailable. Install the TSF postgres extra before applying migrations.",
        }
    try:
        with psycopg.connect(database_url) as connection:
            with connection.cursor() as cursor:
                for statement in plan.statements:
                    cursor.execute(statement)
            connection.commit()
    except Exception as exc:  # noqa: BLE001 - message is redacted before returning.
        return {"applied": False, "summary": redact_db_text(f"Postgres migration failed: {exc}")}
    return {"applied": True, "summary": "Postgres migrations applied safely.", "schemaVersion": plan.schema_version}


def check_postgres_connectivity(database_url: str) -> dict[str, object]:
    try:
        import psycopg  # type: ignore[import-not-found]
    except Exception:
        return {"connected": False, "summary": "Postgres driver is unavailable."}
    try:
        with psycopg.connect(database_url, connect_timeout=5) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
    except Exception as exc:  # noqa: BLE001
        return {"connected": False, "summary": redact_db_text(f"Postgres connectivity failed: {exc}")}
    return {"connected": True, "summary": "Postgres connectivity verified."}


def inspect_postgres_schema(database_url: str) -> dict[str, object]:
    try:
        import psycopg  # type: ignore[import-not-found]
        from psycopg.rows import dict_row  # type: ignore[import-not-found]
    except Exception:
        return {"connected": False, "schemaReady": False, "summary": "Postgres driver is unavailable."}
    try:
        with psycopg.connect(database_url, connect_timeout=5, row_factory=dict_row) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT table_name AS name
                    FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
                    ORDER BY table_name
                    """
                )
                tables = {str(row["name"]) for row in cursor.fetchall()}
                version = 0
                if "schema_migrations" in tables:
                    cursor.execute("SELECT COALESCE(MAX(version), 0) AS version FROM schema_migrations")
                    row = cursor.fetchone()
                    version = int(row["version"]) if row else 0
    except Exception as exc:  # noqa: BLE001
        return {"connected": False, "schemaReady": False, "summary": redact_db_text(f"Postgres schema check failed: {exc}")}
    required = {"tasks", "audit_log", "human_tasks", "scheduler_runs", "deployment_records"}
    missing = sorted(required - tables)
    ready = not missing and version >= POSTGRES_SCHEMA_VERSION
    return {
        "connected": True,
        "schemaReady": ready,
        "schemaVersion": version,
        "missingTables": missing,
        "summary": "Postgres schema verified." if ready else "Postgres schema is not migrated.",
    }


def _postgres_statements() -> Iterable[str]:
    yield """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);
""".strip()
    yield """
CREATE TABLE IF NOT EXISTS runtime_status (
    singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
    status TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
""".strip()
    yield """
CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    objective TEXT NOT NULL,
    assigned_agent_id TEXT,
    created_by_agent_id TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    status TEXT NOT NULL,
    external_effect INTEGER NOT NULL,
    budget_limit DOUBLE PRECISION,
    max_steps INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    plain_english_summary TEXT NOT NULL
);
""".strip()
    yield """
CREATE TABLE IF NOT EXISTS task_events (
    event_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    summary TEXT NOT NULL,
    metadata_json TEXT NOT NULL
);
""".strip()
    yield """
CREATE TABLE IF NOT EXISTS messages (
    message_id TEXT PRIMARY KEY,
    sender_agent_id TEXT NOT NULL,
    recipient_agent_id TEXT,
    channel TEXT,
    task_id TEXT,
    message_type TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);
""".strip()
    yield """
CREATE TABLE IF NOT EXISTS approval_requests (
    approval_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    requested_action TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    external_effect INTEGER NOT NULL,
    plain_english_request TEXT NOT NULL,
    guardian_review TEXT,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    decided_at TEXT
);
""".strip()
    yield """
CREATE TABLE IF NOT EXISTS approval_decisions (
    decision_id TEXT PRIMARY KEY,
    approval_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    signature TEXT,
    dry_run INTEGER NOT NULL,
    executable INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
""".strip()
    yield """
CREATE TABLE IF NOT EXISTS budget_usage (
    usage_id TEXT PRIMARY KEY,
    agent_id TEXT,
    task_id TEXT,
    amount_usd DOUBLE PRECISION NOT NULL,
    loop_steps INTEGER NOT NULL,
    tool_calls INTEGER NOT NULL,
    summary TEXT NOT NULL,
    created_at TEXT NOT NULL
);
""".strip()
    yield """
CREATE TABLE IF NOT EXISTS audit_log (
    audit_id TEXT PRIMARY KEY,
    sequence_number INTEGER NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    actor_type TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    action TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    external_effect INTEGER NOT NULL,
    summary TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    previous_hash TEXT NOT NULL,
    entry_hash TEXT NOT NULL
);
""".strip()
    for table in ("worker_proposals", "self_improvement_proposals"):
        yield f"""
CREATE TABLE IF NOT EXISTS {table} (
    proposal_id TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);
""".strip()
    yield """
CREATE TABLE IF NOT EXISTS daily_reports (
    report_id TEXT PRIMARY KEY,
    report_date TEXT NOT NULL,
    content TEXT NOT NULL,
    telegram_summary TEXT NOT NULL,
    created_at TEXT NOT NULL
);
""".strip()
    yield """
CREATE TABLE IF NOT EXISTS execution_queue (
    queue_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    action TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    external_effect INTEGER NOT NULL,
    approval_id TEXT,
    approval_decision_id TEXT,
    action_hash TEXT NOT NULL,
    status TEXT NOT NULL,
    result_summary TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
""".strip()
    yield """
CREATE TABLE IF NOT EXISTS notification_queue (
    notification_id TEXT PRIMARY KEY,
    notification_type TEXT NOT NULL,
    chat_id TEXT,
    body TEXT NOT NULL,
    status TEXT NOT NULL,
    dry_run INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    sent_at TEXT
);
""".strip()
    yield """
CREATE TABLE IF NOT EXISTS kill_confirmations (
    confirmation_id TEXT PRIMARY KEY,
    chat_id TEXT NOT NULL,
    code TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    used INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
""".strip()
    yield """
CREATE TABLE IF NOT EXISTS provider_auth_sessions (
    session_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    auth_method TEXT NOT NULL,
    requested_by TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    expires_at TEXT,
    login_url_present INTEGER NOT NULL,
    device_code_present INTEGER NOT NULL,
    account_label TEXT,
    model_route TEXT NOT NULL,
    credential_storage TEXT NOT NULL,
    safe_summary TEXT NOT NULL,
    last_error_redacted TEXT
);
""".strip()
    yield """
CREATE TABLE IF NOT EXISTS human_tasks (
    human_task_id TEXT PRIMARY KEY,
    requested_by_agent_id TEXT NOT NULL,
    related_task_id TEXT,
    title TEXT NOT NULL,
    plain_english_request TEXT NOT NULL,
    reason TEXT NOT NULL,
    priority TEXT NOT NULL,
    deadline TEXT,
    cost_estimate TEXT,
    risk_level TEXT NOT NULL,
    public_summary TEXT NOT NULL,
    private_details_redacted TEXT,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    founder_note TEXT
);
""".strip()
    yield """
CREATE TABLE IF NOT EXISTS workdays (
    workday_id TEXT PRIMARY KEY,
    workday_date TEXT NOT NULL,
    timezone TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT,
    closed_at TEXT,
    atlas_plan_id TEXT,
    public_report_id TEXT,
    private_report_id TEXT,
    cycle_count INTEGER NOT NULL,
    last_cycle_at TEXT,
    summary TEXT NOT NULL
);
""".strip()
    yield """
CREATE TABLE IF NOT EXISTS daily_plans (
    plan_id TEXT PRIMARY KEY,
    workday_id TEXT NOT NULL,
    created_by_agent_id TEXT NOT NULL,
    objective TEXT NOT NULL,
    priorities_json TEXT NOT NULL,
    agent_assignments_json TEXT NOT NULL,
    constraints_json TEXT NOT NULL,
    real_data_sources_used_json TEXT NOT NULL,
    assumptions_json TEXT NOT NULL,
    open_questions_json TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);
""".strip()
    yield """
CREATE TABLE IF NOT EXISTS founder_messages (
    message_id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    received_at TEXT NOT NULL,
    sender TEXT NOT NULL,
    target_agent TEXT NOT NULL,
    priority TEXT NOT NULL,
    message_type TEXT NOT NULL,
    content TEXT NOT NULL,
    status TEXT NOT NULL,
    reviewed_by_agent_id TEXT,
    reviewed_at TEXT,
    related_human_task_id TEXT,
    related_task_id TEXT
);
""".strip()
    yield """
CREATE TABLE IF NOT EXISTS scheduler_runs (
    scheduler_run_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    mode TEXT NOT NULL,
    status TEXT NOT NULL,
    checkpoint_type TEXT NOT NULL,
    workday_id TEXT,
    cycle_id TEXT,
    lock_id TEXT,
    summary TEXT NOT NULL,
    error_redacted TEXT
);
""".strip()
    yield """
CREATE TABLE IF NOT EXISTS scheduler_locks (
    lock_id TEXT PRIMARY KEY,
    acquired_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    owner TEXT NOT NULL,
    status TEXT NOT NULL
);
""".strip()
    yield """
CREATE TABLE IF NOT EXISTS deployment_records (
    deployment_id TEXT PRIMARY KEY,
    target TEXT NOT NULL,
    environment TEXT NOT NULL,
    state TEXT NOT NULL,
    plan_json TEXT NOT NULL,
    checks_json TEXT NOT NULL,
    health_check_json TEXT NOT NULL,
    rollback_plan_json TEXT NOT NULL,
    preview_url TEXT,
    public_summary TEXT NOT NULL,
    blocked_reason TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
""".strip()
    yield """
CREATE TABLE IF NOT EXISTS deployment_credential_status (
    check_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    enabled INTEGER NOT NULL,
    cli_available INTEGER NOT NULL,
    cli_version_redacted TEXT,
    credential_present INTEGER NOT NULL,
    credential_source TEXT NOT NULL,
    project_linked INTEGER NOT NULL,
    target_configured INTEGER NOT NULL,
    safe_summary TEXT NOT NULL,
    missing_requirements_json TEXT NOT NULL,
    human_task_required INTEGER NOT NULL,
    checked_at TEXT NOT NULL
);
""".strip()
    yield "CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);"
    yield "CREATE INDEX IF NOT EXISTS idx_tasks_agent ON tasks(assigned_agent_id);"
    yield "CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(created_at);"
    yield "CREATE INDEX IF NOT EXISTS idx_audit_sequence ON audit_log(sequence_number);"
    yield "CREATE INDEX IF NOT EXISTS idx_human_tasks_status ON human_tasks(status);"
    yield "CREATE INDEX IF NOT EXISTS idx_scheduler_runs_started ON scheduler_runs(started_at);"
    yield "CREATE INDEX IF NOT EXISTS idx_deployment_records_updated ON deployment_records(updated_at);"
    yield f"INSERT INTO schema_migrations (version, applied_at) VALUES ({POSTGRES_SCHEMA_VERSION}, now()::text) ON CONFLICT (version) DO NOTHING;"
    yield "INSERT INTO runtime_status (singleton_id, status, updated_at) VALUES (1, 'active', now()::text) ON CONFLICT (singleton_id) DO NOTHING;"


def _is_destructive(statement: str) -> bool:
    lowered = statement.lower()
    return any(token in lowered for token in ("drop table", "drop database", "truncate ", "delete from", "alter table"))


def _table_name_from_create(statement: str) -> set[str]:
    lowered = statement.lower()
    marker = "create table if not exists "
    if marker not in lowered:
        return set()
    tail = statement[lowered.index(marker) + len(marker) :]
    return {tail.split("(", 1)[0].strip().split()[0]}
