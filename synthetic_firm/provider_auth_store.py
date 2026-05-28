"""SQLite persistence for safe provider auth metadata."""

from __future__ import annotations

import sqlite3

from synthetic_firm.provider_auth import ProviderAuthSession, session_to_dict
from synthetic_firm.time_utils import utc_iso


class ProviderAuthStoreError(ValueError):
    """Raised for provider auth persistence errors."""


def save_auth_session(store, session: ProviderAuthSession) -> ProviderAuthSession:
    store.connection.execute(
        """
        INSERT OR REPLACE INTO provider_auth_sessions (
            session_id, provider, auth_method, requested_by, status, created_at,
            updated_at, expires_at, login_url_present, device_code_present,
            account_label, model_route, credential_storage, safe_summary,
            last_error_redacted
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session.session_id,
            session.provider,
            session.auth_method,
            session.requested_by,
            session.status,
            session.created_at,
            utc_iso(),
            session.expires_at,
            int(session.login_url_present),
            int(session.device_code_present),
            session.account_label,
            session.model_route,
            session.credential_storage,
            session.safe_summary,
            session.last_error_redacted,
        ),
    )
    store.connection.commit()
    store.append_audit(
        actor_type="control" if session.requested_by in {"founder", "human", "system"} else "agent",
        actor_id=session.requested_by,
        action="provider_auth_status" if session.status != "pending_user_login" else "provider_auth_start",
        target_type="provider_auth",
        target_id=session.provider,
        risk_level="medium",
        summary=session.safe_summary,
        metadata={"provider": session.provider, "status": session.status, "credential_storage": session.credential_storage},
    )
    return session


def list_auth_sessions(store) -> list[ProviderAuthSession]:
    rows = store.connection.execute(
        "SELECT * FROM provider_auth_sessions ORDER BY updated_at DESC, provider"
    ).fetchall()
    return [_session_from_row(row) for row in rows]


def latest_auth_session(store, provider: str) -> ProviderAuthSession | None:
    row = store.connection.execute(
        """
        SELECT * FROM provider_auth_sessions
        WHERE provider = ? ORDER BY updated_at DESC LIMIT 1
        """,
        (provider,),
    ).fetchone()
    return _session_from_row(row) if row else None


def revoke_auth_metadata(store, provider: str, *, requested_by: str = "founder") -> ProviderAuthSession:
    current = latest_auth_session(store, provider)
    if current is None:
        raise ProviderAuthStoreError(f"No provider auth metadata found for {provider}")
    revoked = ProviderAuthSession(
        **{
            **session_to_dict(current),
            "session_id": current.session_id,
            "status": "revoked",
            "updated_at": utc_iso(),
            "safe_summary": f"Provider auth metadata revoked for {provider}. Provider-owned credentials were not modified.",
            "requested_by": requested_by,
        }
    )
    return save_auth_session(store, revoked)


def _session_from_row(row: sqlite3.Row) -> ProviderAuthSession:
    return ProviderAuthSession(
        session_id=row["session_id"],
        provider=row["provider"],
        auth_method=row["auth_method"],
        requested_by=row["requested_by"],
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        expires_at=row["expires_at"],
        login_url_present=bool(row["login_url_present"]),
        device_code_present=bool(row["device_code_present"]),
        account_label=row["account_label"],
        model_route=row["model_route"],
        credential_storage=row["credential_storage"],
        safe_summary=row["safe_summary"],
        last_error_redacted=row["last_error_redacted"],
    )
