"""Database URL resolution for TSF store backends."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping
from urllib.parse import urlsplit

from synthetic_firm.db_redaction import redact_database_url


class DatabaseUrlError(ValueError):
    """Raised when database URL configuration fails closed."""


@dataclass(frozen=True)
class DatabaseUrlConfig:
    raw_url: str | None
    safe_url: str | None
    source: str
    scheme: str | None
    sslmode: str | None


def resolve_database_url(env: Mapping[str, str] | None = None) -> DatabaseUrlConfig:
    env_map = env or os.environ
    raw = (env_map.get("TSF_DATABASE_URL") or env_map.get("DATABASE_URL") or "").strip()
    source = "TSF_DATABASE_URL" if env_map.get("TSF_DATABASE_URL") else "DATABASE_URL" if env_map.get("DATABASE_URL") else "missing"
    if not raw:
        return DatabaseUrlConfig(raw_url=None, safe_url=None, source="missing", scheme=None, sslmode=None)
    try:
        parsed = urlsplit(raw)
    except ValueError as exc:
        raise DatabaseUrlError("Database URL is malformed") from exc
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise DatabaseUrlError("Postgres backend requires a postgres:// or postgresql:// URL")
    if not parsed.hostname:
        raise DatabaseUrlError("Postgres backend requires a database host")
    return DatabaseUrlConfig(
        raw_url=raw,
        safe_url=redact_database_url(raw),
        source=source,
        scheme=parsed.scheme,
        sslmode=(env_map.get("TSF_POSTGRES_SSLMODE") or "").strip() or None,
    )
