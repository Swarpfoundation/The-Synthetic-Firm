"""Postgres connection adapter for TSF store compatibility."""

from __future__ import annotations

import re
from typing import Any, Iterable

from synthetic_firm.database_url import resolve_database_url
from synthetic_firm.db_redaction import redact_db_text


class PostgresConnectionError(RuntimeError):
    """Raised when Postgres connection setup fails closed."""


class PostgresCursorAdapter:
    def __init__(self, cursor: Any):
        self._cursor = cursor

    def fetchone(self) -> Any | None:
        return self._cursor.fetchone()

    def fetchall(self) -> list[Any]:
        return list(self._cursor.fetchall())


class PostgresConnectionAdapter:
    """Small sqlite-like wrapper around psycopg for existing TSF SQL paths."""

    def __init__(self, connection: Any):
        self._connection = connection

    @property
    def in_transaction(self) -> bool:
        try:
            status = self._connection.info.transaction_status
            pg_transaction_status = self._connection.pgconn.TransactionStatus
            return status != pg_transaction_status.IDLE
        except Exception:
            return False

    def execute(self, sql: str, params: Iterable[Any] | None = None) -> PostgresCursorAdapter:
        translated = translate_sql(sql)
        try:
            cursor = self._connection.execute(translated, tuple(params or ()))
        except Exception as exc:  # noqa: BLE001
            raise PostgresConnectionError(redact_db_text(f"Postgres query failed: {exc}")) from exc
        return PostgresCursorAdapter(cursor)

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def close(self) -> None:
        self._connection.close()


def connect_postgres() -> PostgresConnectionAdapter:
    db_url = resolve_database_url()
    if not db_url.raw_url:
        raise PostgresConnectionError("Postgres backend requires DATABASE_URL or TSF_DATABASE_URL")
    try:
        import psycopg  # type: ignore[import-not-found]
        from psycopg.rows import dict_row  # type: ignore[import-not-found]
    except Exception as exc:  # noqa: BLE001
        raise PostgresConnectionError(
            "Postgres driver is unavailable. Install with: pip install -e '.[postgres]'"
        ) from exc
    try:
        connection = psycopg.connect(str(db_url.raw_url), connect_timeout=5, row_factory=dict_row)
    except Exception as exc:  # noqa: BLE001
        raise PostgresConnectionError(redact_db_text(f"Postgres connection failed: {exc}")) from exc
    return PostgresConnectionAdapter(connection)


def translate_sql(sql: str) -> str:
    text = sql.strip()
    if text.upper() == "BEGIN IMMEDIATE":
        return "BEGIN"
    if "sqlite_master" in text:
        return """
        SELECT table_name AS name
        FROM information_schema.tables
        WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
        ORDER BY table_name
        """.strip()
    text = text.replace("INSERT OR IGNORE INTO schema_migrations", "INSERT INTO schema_migrations")
    text = text.replace("INSERT OR IGNORE INTO runtime_status", "INSERT INTO runtime_status")
    text = _replace_qmark_params(text)
    if text.startswith("INSERT INTO schema_migrations") and "ON CONFLICT" not in text:
        text = f"{text} ON CONFLICT (version) DO NOTHING"
    if text.startswith("INSERT INTO runtime_status") and "ON CONFLICT" not in text:
        text = f"{text} ON CONFLICT (singleton_id) DO NOTHING"
    if text.startswith("REPLACE INTO tasks"):
        text = _task_upsert_sql()
    text = text.replace("date(created_at) = date('now')", "created_at::date = CURRENT_DATE")
    text = text.replace("date(started_at) = date('now')", "started_at::date = CURRENT_DATE")
    text = re.sub(r"\bCOALESCE\(\?,\s*([A-Za-z_]+)\)", r"COALESCE(%s, \1)", text)
    return text


def _replace_qmark_params(sql: str) -> str:
    return sql.replace("?", "%s")


def _task_upsert_sql() -> str:
    return """
    INSERT INTO tasks VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (task_id) DO UPDATE SET
        title = EXCLUDED.title,
        objective = EXCLUDED.objective,
        assigned_agent_id = EXCLUDED.assigned_agent_id,
        created_by_agent_id = EXCLUDED.created_by_agent_id,
        risk_level = EXCLUDED.risk_level,
        status = EXCLUDED.status,
        external_effect = EXCLUDED.external_effect,
        budget_limit = EXCLUDED.budget_limit,
        max_steps = EXCLUDED.max_steps,
        created_at = EXCLUDED.created_at,
        updated_at = EXCLUDED.updated_at,
        plain_english_summary = EXCLUDED.plain_english_summary
    """.strip()
