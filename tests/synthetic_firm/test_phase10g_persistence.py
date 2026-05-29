from __future__ import annotations

import json

import pytest

from synthetic_firm.control_room_export import build_control_room_snapshot
from synthetic_firm.database_url import resolve_database_url
from synthetic_firm.db_redaction import redact_database_url, redact_db_text
from synthetic_firm.postgres_store import postgres_migration_plan, verify_postgres_migration_plan
from synthetic_firm.render_runtime import render_api_readiness, scheduler_render_readiness
from synthetic_firm.store import Store
from synthetic_firm.store_backend import (
    StoreBackendError,
    db_migrate,
    db_redaction_smoke,
    db_status,
    db_verify,
    resolve_store_backend,
)


def test_sqlite_is_default_backend(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    monkeypatch.delenv("TSF_STORE_BACKEND", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("TSF_DATABASE_URL", raising=False)

    config = resolve_store_backend()
    status = db_status()

    assert config.backend == "sqlite"
    assert status["backend"] == "sqlite"
    assert status["connected"] is True
    assert status["publicStatus"] == "sqlite_preview"


def test_postgres_mode_requires_database_url(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    monkeypatch.setenv("TSF_STORE_BACKEND", "postgres")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("TSF_DATABASE_URL", raising=False)

    with pytest.raises(StoreBackendError):
        resolve_store_backend()

    status = db_status()
    assert status["connected"] is False
    assert "DATABASE_URL" in status["safeSummary"]


def test_database_url_redaction_excludes_credentials_and_host():
    raw = "postgres://alice:super-secret@db.internal.example:5432/tsf?sslmode=require&token=abc123"

    redacted = redact_database_url(raw)
    free_text = redact_db_text(f"Connect through {raw}")
    config = resolve_database_url({"TSF_DATABASE_URL": raw})

    dumped = json.dumps({"redacted": redacted, "freeText": free_text, "safe": config.safe_url})
    assert "alice" not in dumped
    assert "super-secret" not in dumped
    assert "db.internal.example" not in dumped
    assert "abc123" not in dumped
    assert "[redacted" in dumped


def test_postgres_migration_plan_is_non_destructive_and_idempotent():
    plan = postgres_migration_plan()
    ok, summary = verify_postgres_migration_plan(plan)
    sql = "\n".join(plan.statements).lower()

    assert ok, summary
    assert "create table if not exists tasks" in sql
    assert "create table if not exists human_tasks" in sql
    assert "create table if not exists scheduler_runs" in sql
    assert "create table if not exists deployment_records" in sql
    assert "create table if not exists code_change_proposals" in sql
    for forbidden in ("drop table", "truncate", "delete from", "alter table"):
        assert forbidden not in sql


def test_postgres_migrate_dry_run_redacts_url(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    env = {
        "TSF_STORE_BACKEND": "postgres",
        "DATABASE_URL": "postgres://bob:db-password@private.db.render.com:5432/tsf",
    }

    result = db_migrate(env=env)
    dumped = json.dumps(result)

    assert result["dryRun"] is True
    assert result["applied"] is False
    assert "CREATE TABLE IF NOT EXISTS" in dumped
    assert "db-password" not in dumped
    assert "private.db.render.com" not in dumped


def test_postgres_apply_requires_explicit_env_gate(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    env = {
        "TSF_STORE_BACKEND": "postgres",
        "DATABASE_URL": "postgres://bob:db-password@private.db.render.com:5432/tsf",
    }

    result = db_migrate(apply=True, env=env)

    assert result["applied"] is False
    assert result["dryRun"] is True
    assert "requires TSF_DB_MIGRATION_DRY_RUN=false" in result["summary"]


def test_sqlite_repository_and_export_paths_still_work(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    store = Store()
    task = store.create_task(
        title="Persist runtime state",
        objective="Keep SQLite behavior working while Postgres is added.",
        created_by_agent_id="atlas",
        assigned_agent_id="forge",
        plain_english_summary="Forge validates SQLite compatibility.",
    )
    store.create_human_task(
        requested_by_agent_id="forge",
        related_task_id=task.task_id,
        title="Create Render Postgres database",
        plain_english_request="Create the shared Render Postgres database.",
        reason="The deployed API and scheduler need shared durable state.",
        public_summary="Founder database setup task pending.",
    )
    store.create_founder_message(content="Private founder note", source="telegram")
    store.save_daily_report(
        report_date="2026-05-29",
        content="The Synthetic Firm - Daily Public Report\nReal persisted report.",
        telegram_summary="Real persisted report.",
    )

    snapshot = build_control_room_snapshot(store, audience="public")
    verify = db_verify()

    assert snapshot["tasks"][0]["id"] == task.task_id
    assert snapshot["storeBackendPublicStatus"] == "sqlite_preview"
    assert snapshot["storage"]["backend"] == "sqlite"
    assert snapshot["lastAtlasReportAt"] is not None
    assert "Private founder note" not in json.dumps(snapshot)
    assert verify["verified"] is True
    assert store.verify_audit()[0] is True
    store.close()


def test_render_readiness_creates_safe_human_tasks_for_missing_postgres(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    monkeypatch.delenv("TSF_STORE_BACKEND", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("TSF_DATABASE_URL", raising=False)
    store = Store()

    result = scheduler_render_readiness(store)
    tasks = store.list_human_tasks(status="pending")
    dumped = json.dumps([task.__dict__ for task in tasks])

    assert result["ready"] is False
    assert result["storeBackendPublicStatus"] == "sqlite_preview"
    assert any("Render Postgres" in task.plain_english_request for task in tasks)
    assert "DATABASE_URL" in dumped
    assert "postgres://" not in dumped
    assert "password" not in dumped.lower()
    store.close()


def test_render_api_readiness_is_safe_without_api_url(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    store = Store()

    result = render_api_readiness(store=store)
    dumped = json.dumps(result)

    assert result["ready"] is False
    assert "Render API durable runtime setup is pending" in result["summary"]
    assert "postgres://" not in dumped
    assert store.list_human_tasks(status="pending")
    store.close()


def test_db_redaction_smoke_passes():
    result = db_redaction_smoke()

    assert result["passed"] is True
    assert "password" not in result["redacted"]
    assert "example.internal" not in result["redacted"]
