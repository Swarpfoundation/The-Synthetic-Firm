"""Render runtime readiness checks for durable TSF operation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from synthetic_firm.public_progress_smoke import _clean_url, _fetch_text
from synthetic_firm.store import Store, default_db_path
from synthetic_firm.store_backend import db_status


@dataclass(frozen=True)
class ReadinessResult:
    ready: bool
    summary: str
    details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"ready": self.ready, "summary": self.summary, **self.details}


def scheduler_render_readiness(store: Store | None = None) -> dict[str, Any]:
    store, own_store, store_open_error = _readiness_store(store)
    try:
        backend = db_status()
        backend_name = str(backend.get("backend", "unknown"))
        public_status = str(backend.get("publicStatus", "postgres_unavailable"))
        missing: list[str] = []
        if backend_name != "postgres":
            missing.extend(
                (
                    "Create a Render Postgres database.",
                    "Set TSF_STORE_BACKEND=postgres on the API and scheduler services.",
                    "Set DATABASE_URL on the API and scheduler services through Render environment variables.",
                )
            )
        elif not backend.get("connected"):
            missing.append("Install the TSF Postgres extra and verify Render DATABASE_URL connectivity.")
        elif not backend.get("schemaReady"):
            missing.append("Run/apply TSF Postgres migrations.")
        if not _has_scheduler_service_configured():
            missing.append("Create a Render cron job or worker that runs scheduler-checkpoint-once.")
        for item in missing:
            _create_readiness_human_task(store, item, "Scheduler durable runtime setup is pending.")
        ready = not missing
        return {
            "ready": ready,
            "backend": backend_name,
            "storeBackendPublicStatus": public_status,
            "storeOpenError": store_open_error,
            "missingRequirements": missing,
            "summary": "Scheduler Render readiness is available." if ready else "Scheduler Render readiness setup is pending.",
        }
    finally:
        if own_store:
            store.close()


def scheduler_checkpoint_smoke(*, apply: bool = False, store: Store | None = None) -> dict[str, Any]:
    own_store = store is None
    store = store or Store()
    try:
        readiness = scheduler_render_readiness(store)
        if not readiness["ready"]:
            return {"applied": False, "ready": False, "summary": readiness["summary"], "readiness": readiness}
        if not apply:
            return {"applied": False, "ready": True, "summary": "Scheduler checkpoint smoke dry-run passed."}
        from synthetic_firm.scheduler import run_checkpoint_once

        result = run_checkpoint_once(store)
        return {"applied": True, "ready": True, "summary": "Scheduler checkpoint smoke applied.", "result": result}
    finally:
        if own_store:
            store.close()


def render_api_readiness(api_url: str | None = None, store: Store | None = None) -> dict[str, Any]:
    store, own_store, store_open_error = _readiness_store(store)
    try:
        backend = db_status()
        missing: list[str] = []
        if backend.get("backend") != "postgres":
            missing.append("Configure Render API service with TSF_STORE_BACKEND=postgres and DATABASE_URL.")
        elif not backend.get("connected"):
            missing.append("Install the TSF Postgres extra and verify Render DATABASE_URL connectivity.")
        elif not backend.get("schemaReady"):
            missing.append("Run/apply TSF Postgres migrations.")
        api_summary = "API URL not checked."
        api_ok = False
        if api_url:
            smoke = public_api_smoke(api_url=api_url)
            api_ok = bool(smoke["passed"])
            api_summary = smoke["summary"]
        if missing:
            _create_readiness_human_task(store, missing[0], "Render API durable runtime setup is pending.")
        return {
            "ready": not missing and (api_ok if api_url else True),
            "dbStatus": backend,
            "storeOpenError": store_open_error,
            "apiChecked": bool(api_url),
            "apiSummary": api_summary,
            "missingRequirements": missing,
            "summary": "Render API readiness is available." if not missing else "Render API durable runtime setup is pending.",
        }
    finally:
        if own_store:
            store.close()


def public_api_smoke(*, api_url: str) -> dict[str, Any]:
    clean_api = _clean_url(api_url)
    checks: dict[str, Any] = {}
    errors: list[str] = []
    for path in (
        "/health",
        "/api/public/control-room/snapshot",
        "/api/public/reports/latest",
        "/api/public/human-tasks/summary",
    ):
        try:
            status, body = _fetch_text(f"{clean_api}{path}", max_bytes=800_000)
            payload = json.loads(body)
            checks[path] = {"status": status, "keys": sorted(payload.keys())[:12]}
            if path.endswith("/snapshot"):
                checks[path]["audience"] = payload.get("audience")
                checks[path]["truthfulness"] = payload.get("truthfulness")
                if payload.get("audience") != "public" or payload.get("truthfulness") != "real_runtime_data_only":
                    errors.append("Public snapshot audience/truthfulness did not match expected values.")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{path} failed: {type(exc).__name__}")
    try:
        status, body = _fetch_text(f"{clean_api}/api/public/control-room/events", max_bytes=512)
        checks["/api/public/control-room/events"] = {"status": status, "reachable": "event:" in body or "data:" in body}
    except Exception as exc:  # noqa: BLE001
        errors.append(f"/api/public/control-room/events failed: {type(exc).__name__}")
    return {
        "passed": not errors,
        "apiUrl": clean_api,
        "checks": checks,
        "errors": errors,
        "summary": "Public API smoke passed." if not errors else "Public API smoke failed safely.",
    }


def _has_scheduler_service_configured() -> bool:
    import os

    return bool(
        os.environ.get("TSF_RENDER_SCHEDULER_SERVICE_ID", "").strip()
        or os.environ.get("TSF_RENDER_WORKER_SERVICE_ID", "").strip()
        or os.environ.get("TSF_RENDER_SCHEDULER_CRON_CONFIGURED", "").strip().lower() in {"1", "true", "yes", "on"}
    )


def _readiness_store(store: Store | None) -> tuple[Store, bool, str | None]:
    if store is not None:
        return store, False, None
    try:
        return Store(), True, None
    except Exception as exc:  # noqa: BLE001
        fallback = Store(default_db_path())
        return fallback, True, f"Selected store unavailable for advisory persistence: {type(exc).__name__}"


def _create_readiness_human_task(store: Store, request: str, public_summary: str) -> None:
    existing = [
        task
        for task in store.list_human_tasks(status="pending")
        if task.plain_english_request == request and task.public_summary == public_summary
    ]
    if existing:
        return
    store.create_human_task(
        requested_by_agent_id="forge",
        title="Complete Render runtime persistence setup",
        plain_english_request=request,
        reason="The public Progress Window needs durable shared runtime state before deployed scheduler checkpoints can publish real workday progress.",
        priority="high",
        risk_level="medium",
        public_summary=public_summary,
        private_details="Configure this only through Render environment variables or dashboard controls. Do not paste database credentials into Telegram or reports.",
    )
