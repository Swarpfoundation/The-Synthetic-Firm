"""Append-only audit log with hash-chain verification."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from synthetic_firm.time_utils import utc_iso

ZERO_HASH = "0" * 64
SECRET_MARKERS = ("api_key", "token", "secret", "password", "credential")


class AuditLogError(ValueError):
    """Raised when audit log integrity or safety checks fail."""


@dataclass(frozen=True)
class AuditEntry:
    audit_id: str
    sequence_number: int
    created_at: str
    actor_type: str
    actor_id: str
    action: str
    target_type: str
    target_id: str
    risk_level: str
    external_effect: bool
    summary: str
    metadata_json: str
    previous_hash: str
    entry_hash: str


def append_audit_entry(
    connection: sqlite3.Connection,
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
) -> AuditEntry:
    safe_summary = _safe_text(summary)
    safe_metadata = _safe_metadata(metadata or {})
    for attempt in range(3):
        try:
            if not connection.in_transaction:
                connection.execute("BEGIN IMMEDIATE")
            previous = connection.execute(
                "SELECT sequence_number, entry_hash FROM audit_log ORDER BY sequence_number DESC LIMIT 1"
            ).fetchone()
            sequence = int(previous["sequence_number"]) + 1 if previous else 1
            previous_hash = str(previous["entry_hash"]) if previous else ZERO_HASH
            entry = {
                "audit_id": f"audit_{uuid4().hex[:12]}",
                "sequence_number": sequence,
                "created_at": utc_iso(),
                "actor_type": _required(actor_type, "actor_type"),
                "actor_id": _required(actor_id, "actor_id"),
                "action": _required(action, "action"),
                "target_type": _required(target_type, "target_type"),
                "target_id": _required(target_id, "target_id"),
                "risk_level": str(risk_level or "low").lower(),
                "external_effect": bool(external_effect),
                "summary": safe_summary,
                "metadata_json": json.dumps(safe_metadata, sort_keys=True),
                "previous_hash": previous_hash,
            }
            entry["entry_hash"] = _entry_hash(entry)
            connection.execute(
                """
                INSERT INTO audit_log (
                    audit_id, sequence_number, created_at, actor_type, actor_id, action,
                    target_type, target_id, risk_level, external_effect, summary,
                    metadata_json, previous_hash, entry_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry["audit_id"],
                    entry["sequence_number"],
                    entry["created_at"],
                    entry["actor_type"],
                    entry["actor_id"],
                    entry["action"],
                    entry["target_type"],
                    entry["target_id"],
                    entry["risk_level"],
                    int(entry["external_effect"]),
                    entry["summary"],
                    entry["metadata_json"],
                    entry["previous_hash"],
                    entry["entry_hash"],
                ),
            )
            connection.commit()
            return AuditEntry(**entry)
        except sqlite3.IntegrityError:
            connection.rollback()
            if attempt == 2:
                raise
    raise AuditLogError("Failed to append audit entry")


def verify_audit_chain(connection: sqlite3.Connection) -> tuple[bool, str]:
    rows = connection.execute("SELECT * FROM audit_log ORDER BY sequence_number ASC").fetchall()
    previous_hash = ZERO_HASH
    expected_sequence = 1
    for row in rows:
        if int(row["sequence_number"]) != expected_sequence:
            return False, f"Audit sequence gap at {row['audit_id']}"
        if row["previous_hash"] != previous_hash:
            return False, f"Audit previous hash mismatch at {row['audit_id']}"
        payload = {
            "audit_id": row["audit_id"],
            "sequence_number": row["sequence_number"],
            "created_at": row["created_at"],
            "actor_type": row["actor_type"],
            "actor_id": row["actor_id"],
            "action": row["action"],
            "target_type": row["target_type"],
            "target_id": row["target_id"],
            "risk_level": row["risk_level"],
            "external_effect": bool(row["external_effect"]),
            "summary": row["summary"],
            "metadata_json": row["metadata_json"],
            "previous_hash": row["previous_hash"],
        }
        actual = _entry_hash(payload)
        if actual != row["entry_hash"]:
            return False, f"Audit entry hash mismatch at {row['audit_id']}"
        previous_hash = row["entry_hash"]
        expected_sequence += 1
    return True, f"Audit chain verified with {len(rows)} entries."


def _entry_hash(entry: dict[str, Any]) -> str:
    canonical = json.dumps(entry, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _safe_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    return {str(key): _redact_value(str(key), value) for key, value in metadata.items()}


def _safe_text(value: str) -> str:
    text = _required(value, "summary")
    lowered = text.lower()
    if any(marker in lowered for marker in SECRET_MARKERS):
        return "[redacted sensitive summary]"
    return text


def _redact_value(key: str, value: Any) -> Any:
    if any(marker in key.lower() for marker in SECRET_MARKERS):
        return "[redacted]"
    if isinstance(value, str) and any(marker in value.lower() for marker in SECRET_MARKERS):
        return "[redacted]"
    if isinstance(value, dict):
        return _safe_metadata(value)
    if isinstance(value, list | tuple):
        return [_redact_value(key, item) for item in value]
    return value


def _required(value: Any, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise AuditLogError(f"{name} is required")
    return text
