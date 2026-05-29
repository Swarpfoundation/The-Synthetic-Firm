"""Postgres-backed repository facade for selected TSF runtime paths."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from synthetic_firm.db_redaction import redact_db_text
from synthetic_firm.postgres_connection import PostgresConnectionError, connect_postgres
from synthetic_firm.postgres_store import postgres_migration_plan, verify_postgres_migration_plan
from synthetic_firm.store import Store, StoreError


class PostgresStore(Store):
    """Store-compatible Postgres implementation.

    Most repository behavior is inherited from ``Store``. The Postgres
    connection adapter translates the existing parameterized SQL surface and
    keeps direct ``store.connection.execute(...)`` callers on the selected
    backend.
    """

    backend = "postgres"

    def __init__(self, path: str | Path | None = None):
        if path is not None:
            raise StoreError("PostgresStore does not accept a SQLite path")
        try:
            self.path = Path("[postgres]")
            self.connection = connect_postgres()
            self._ensure_schema()
        except PostgresConnectionError as exc:
            raise StoreError(redact_db_text(str(exc))) from exc

    def status(self) -> dict[str, Any]:
        tables = self.connection.execute(
            """
            SELECT table_name AS name
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            ORDER BY table_name
            """
        ).fetchall()
        version_row = self.connection.execute(
            "SELECT COALESCE(MAX(version), 0) AS version FROM schema_migrations"
        ).fetchone()
        return {
            "path": "[postgres]",
            "backend": "postgres",
            "schema_version": int(version_row["version"]) if version_row else 0,
            "tables": [row["name"] for row in tables],
        }

    def _ensure_schema(self) -> None:
        plan = postgres_migration_plan()
        ok, summary = verify_postgres_migration_plan(plan)
        if not ok:
            raise StoreError(summary)
        try:
            for statement in plan.statements:
                self.connection.execute(statement)
            self.connection.commit()
        except Exception as exc:  # noqa: BLE001
            self.connection.rollback()
            raise StoreError(redact_db_text(f"Postgres schema initialization failed: {exc}")) from exc
