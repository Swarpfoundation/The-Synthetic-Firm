from __future__ import annotations

import json
import subprocess

from synthetic_firm.cli import main
from synthetic_firm.control_room_export import build_control_room_snapshot
from synthetic_firm.cost_ledger import add_cost_item
from synthetic_firm.deployment_health import run_vercel_preview_health_check
from synthetic_firm.render_adapter import render_credential_status
from synthetic_firm.store import Store
from synthetic_firm.vercel_adapter import deploy_vercel_preview, vercel_credential_status


def test_credential_status_snapshots_are_persisted_without_values(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    monkeypatch.setenv("TSF_VERCEL_TOKEN", "vercel-secret-value")
    monkeypatch.setenv("TSF_RENDER_API_KEY", "render-secret-value")
    store = Store()

    vercel_credential_status(store=store)
    render_credential_status(store=store)

    rows = store.connection.execute("SELECT * FROM deployment_credential_status").fetchall()
    dumped = json.dumps([dict(row) for row in rows], sort_keys=True)
    assert len(rows) == 2
    assert "vercel-secret-value" not in dumped
    assert "render-secret-value" not in dumped
    assert store.verify_audit()[0] is True
    store.close()


def test_create_deployment_setup_human_tasks_adds_advisory_confirmations(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))

    assert main(["create-deployment-setup-human-tasks"]) == 0
    out = capsys.readouterr().out

    assert "Confirm Vercel preview policy" in out or "Deployment credential status checked safely" in out
    store = Store()
    titles = {task.title for task in store.list_human_tasks(status="pending")}
    assert "Confirm Vercel production remains blocked" in titles
    assert "Confirm Render deploy mode" in titles
    dumped = _dump_sqlite(store)
    assert "secret-value" not in dumped
    store.close()


def test_vercel_preview_live_gate_executes_only_with_explicit_setup(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    monkeypatch.setenv("TSF_VERCEL_ENABLED", "true")
    monkeypatch.setenv("TSF_VERCEL_PREVIEW_DEPLOY_ENABLED", "true")
    monkeypatch.setenv("TSF_DEPLOY_DRY_RUN", "false")
    monkeypatch.setenv("TSF_VERCEL_TOKEN", "vercel-secret-value")
    project = tmp_path / "apps" / "control-room"
    (project / ".vercel").mkdir(parents=True)
    (project / ".vercel" / "project.json").write_text("{}", encoding="utf-8")
    (project / "package.json").write_text('{"scripts":{"build":"vite build","typecheck":"tsc -b"}}', encoding="utf-8")
    monkeypatch.setenv("TSF_VERCEL_PROJECT_PATH", str(project))
    monkeypatch.setattr("synthetic_firm.vercel_adapter.shutil.which", lambda name: "/usr/bin/vercel")
    monkeypatch.setattr("synthetic_firm.vercel_adapter._vercel_version_redacted", lambda: "vercel 1.0.0")
    monkeypatch.setattr(
        "synthetic_firm.vercel_adapter.run_vercel_preview_health_check",
        lambda url, env=None, store=None: _check(True, "Preview health check passed.", "HTTP 200"),
    )
    seen: dict[str, object] = {}

    def runner(command, cwd, env):
        seen["command"] = command
        seen["env"] = env
        return subprocess.CompletedProcess(command, 0, stdout="https://phase10c-preview.vercel.app\n", stderr="")

    store = Store()
    add_cost_item(
        store,
        category="vercel",
        provider="vercel",
        service_name="Vercel public Progress Window",
        description="Founder-confirmed preview deployment cost is within budget.",
        amount_eur=0,
        recurrence="monthly",
        confidence="estimated",
    )
    result = deploy_vercel_preview(store, dry_run=False, runner=runner)

    assert result["executed"] is True
    assert seen["command"] == ["vercel", "deploy", "--yes", "--target", "preview"]
    assert "vercel-secret-value" not in " ".join(seen["command"])
    assert seen["env"]["VERCEL_TOKEN"] == "vercel-secret-value"
    assert "vercel-secret-value" not in json.dumps(result) + _dump_sqlite(store)
    store.close()


def test_vercel_health_check_audits_failure_without_raw_secret(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    store = Store()

    result = run_vercel_preview_health_check(
        "https://phase10c-preview.vercel.app",
        fetcher=lambda url, timeout: (200, "token=raw-secret-value pause runtime"),
        store=store,
    )
    dumped = _dump_sqlite(store)

    assert result.passed is False
    assert "raw-secret-value" not in dumped
    assert store.verify_audit()[0] is True
    store.close()


def test_public_export_includes_safe_credential_and_health_metadata(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    monkeypatch.setenv("TSF_RENDER_API_SERVICE_ID", "srv-private-id")
    store = Store()
    render_credential_status(store=store)

    snapshot = build_control_room_snapshot(store, audience="public")
    dumped = json.dumps(snapshot)

    assert "credentialStatus" in snapshot["deploymentSummary"]
    assert "lastCheckedAt" in snapshot["deploymentSummary"]
    assert "srv-private-id" not in dumped
    assert "RENDER_API_KEY" not in dumped
    store.close()


def test_new_internal_phase10c_commands(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))

    assert main(["deployment-setup-status"]) == 0
    assert "Deployment credential status checked safely" in capsys.readouterr().out

    assert main(["validate-vercel-setup"]) == 0
    assert "Vercel" in capsys.readouterr().out

    assert main(["validate-render-setup"]) == 0
    assert "Render" in capsys.readouterr().out

    assert main(["deployment-notifications"]) == 0
    assert "notifications" in capsys.readouterr().out


def _check(passed: bool, summary: str, output: str):
    from synthetic_firm.deployment import DeploymentCheckResult

    return DeploymentCheckResult("preview health check", passed, summary, output)


def _dump_sqlite(store: Store) -> str:
    chunks: list[str] = []
    for table in ("deployment_records", "deployment_credential_status", "human_tasks", "audit_log", "notification_queue"):
        rows = store.connection.execute(f"SELECT * FROM {table}").fetchall()
        chunks.append(json.dumps([dict(row) for row in rows], sort_keys=True))
    return "\n".join(chunks)
