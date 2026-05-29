"""Store backend selection, status, and migration readiness."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from synthetic_firm.database_url import DatabaseUrlError, resolve_database_url
from synthetic_firm.db_redaction import redact_database_url, redact_db_text
from synthetic_firm.migrations import SCHEMA_VERSION
from synthetic_firm.postgres_store import (
    apply_postgres_migrations,
    check_postgres_connectivity,
    inspect_postgres_schema,
    postgres_migration_plan,
    verify_postgres_migration_plan,
)
from synthetic_firm.store import Store, default_db_path

STORE_BACKENDS = frozenset({"sqlite", "postgres"})


class StoreBackendError(ValueError):
    """Raised when store backend configuration fails closed."""


@dataclass(frozen=True)
class StoreBackendConfig:
    backend: str
    sqlite_path: Path
    database_url_present: bool
    database_url_safe: str | None
    database_url_source: str
    postgres_sslmode: str | None

    def public_status(self) -> str:
        if self.backend == "sqlite":
            return "sqlite_preview"
        return "postgres_ready" if self.database_url_present else "postgres_unavailable"


def resolve_store_backend(env: Mapping[str, str] | None = None) -> StoreBackendConfig:
    env_map = env or os.environ
    backend = (env_map.get("TSF_STORE_BACKEND") or "sqlite").strip().lower()
    if backend not in STORE_BACKENDS:
        raise StoreBackendError(f"Unsupported TSF_STORE_BACKEND: {backend}")
    try:
        db_url = resolve_database_url(env_map)
    except DatabaseUrlError as exc:
        if backend == "postgres":
            raise StoreBackendError(str(exc)) from exc
        db_url = resolve_database_url({})
    if backend == "postgres" and not db_url.raw_url:
        raise StoreBackendError("Postgres backend requires DATABASE_URL or TSF_DATABASE_URL")
    return StoreBackendConfig(
        backend=backend,
        sqlite_path=default_db_path(),
        database_url_present=bool(db_url.raw_url),
        database_url_safe=db_url.safe_url,
        database_url_source=db_url.source,
        postgres_sslmode=db_url.sslmode,
    )


def db_status(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    try:
        config = resolve_store_backend(env)
    except Exception as exc:  # noqa: BLE001
        return {
            "backend": (env or os.environ).get("TSF_STORE_BACKEND", "sqlite"),
            "connected": False,
            "schemaVersion": None,
            "safeSummary": redact_db_text(str(exc)),
        }
    if config.backend == "sqlite":
        store = Store()
        try:
            status = store.status()
            return {
                "backend": "sqlite",
                "repositoryMode": "sqlite_active",
                "connected": True,
                "schemaVersion": status["schema_version"],
                "safeSummary": "SQLite local/dev store is available.",
                "sqlitePath": str(config.sqlite_path),
                "tableCount": len(status["tables"]),
                "publicStatus": config.public_status(),
            }
        finally:
            store.close()
    url = str(resolve_database_url(env).raw_url)
    connectivity = check_postgres_connectivity(url)
    schema = inspect_postgres_schema(url) if connectivity["connected"] else {}
    schema_ready = bool(schema.get("schemaReady"))
    return {
        "backend": "postgres",
        "repositoryMode": "postgres_active" if schema_ready else "postgres_schema_pending",
        "connected": bool(connectivity["connected"]),
        "schemaVersion": schema.get("schemaVersion") if connectivity["connected"] else None,
        "schemaReady": schema_ready,
        "missingTables": schema.get("missingTables", []),
        "safeSummary": (
            f"{connectivity['summary']} {schema.get('summary', '')}".strip()
            if connectivity["connected"]
            else connectivity["summary"]
        ),
        "databaseUrlPresent": config.database_url_present,
        "databaseUrlSource": config.database_url_source,
        "databaseUrlRedacted": config.database_url_safe,
        "publicStatus": "postgres_ready" if schema_ready else "postgres_unavailable",
    }


def db_migrate(*, apply: bool = False, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    config = resolve_store_backend(env)
    if config.backend == "sqlite":
        if apply:
            store = Store()
            store.close()
        return {
            "backend": "sqlite",
            "dryRun": not apply,
            "applied": bool(apply),
            "schemaVersion": SCHEMA_VERSION,
            "summary": "SQLite schema is initialized idempotently by Store().",
        }
    plan = postgres_migration_plan()
    ok, summary = verify_postgres_migration_plan(plan)
    if not ok:
        return {"backend": "postgres", "dryRun": not apply, "applied": False, "summary": summary}
    if not apply:
        return {
            "backend": "postgres",
            "dryRun": True,
            "applied": False,
            "migration": plan.to_dict(include_sql=True),
            "summary": "Postgres migration dry-run generated non-destructive SQL.",
        }
    env_map = env or os.environ
    if (env_map.get("TSF_DB_MIGRATION_DRY_RUN", "true").strip().lower() != "false"):
        return {
            "backend": "postgres",
            "dryRun": True,
            "applied": False,
            "summary": "Postgres migration apply requires TSF_DB_MIGRATION_DRY_RUN=false.",
        }
    result = apply_postgres_migrations(str(resolve_database_url(env).raw_url))
    result.update({"backend": "postgres", "dryRun": False})
    return result


def db_verify(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    config = resolve_store_backend(env)
    if config.backend == "sqlite":
        store = Store()
        try:
            tables = set(store.status()["tables"])
            required = {"tasks", "audit_log", "human_tasks", "scheduler_runs", "deployment_records"}
            missing = sorted(required - tables)
            return {
                "backend": "sqlite",
                "verified": not missing,
                "missingTables": missing,
                "summary": "SQLite schema verified." if not missing else "SQLite schema is missing required tables.",
            }
        finally:
            store.close()
    status = db_status(env)
    if not status.get("connected"):
        return {"backend": "postgres", "verified": False, "summary": status.get("safeSummary"), "schemaVersion": None}
    if not status.get("schemaReady"):
        return {
            "backend": "postgres",
            "verified": False,
            "summary": "Postgres schema is not migrated.",
            "schemaVersion": status.get("schemaVersion"),
            "missingTables": status.get("missingTables", []),
        }
    return {"backend": "postgres", "verified": True, "summary": "Postgres schema verified.", "schemaVersion": status.get("schemaVersion")}


def db_smoke(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    config = resolve_store_backend(env)
    if config.backend == "sqlite":
        store = Store()
        try:
            ok, audit_summary = store.verify_audit()
            return {
                "backend": "sqlite",
                "smokePassed": ok,
                "summary": "SQLite smoke passed." if ok else audit_summary,
                "runtimeStatus": store.runtime_status(),
            }
        finally:
            store.close()
    status = db_status(env)
    return {
        "backend": "postgres",
        "smokePassed": bool(status.get("connected")) and bool(status.get("schemaReady")),
        "summary": status.get("safeSummary", "Postgres smoke completed."),
    }


def db_redaction_smoke() -> dict[str, Any]:
    sample = "postgres://user:password@example.internal:5432/tsf?sslmode=require&token=abc"
    redacted = redact_database_url(sample)
    leaked = any(secret in redacted for secret in ("user", "password", "example.internal", "abc"))
    return {"passed": not leaked, "redacted": redacted, "summary": "Database URL redaction smoke completed."}
