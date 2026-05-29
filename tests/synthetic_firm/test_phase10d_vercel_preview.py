from __future__ import annotations

import json
import subprocess

from synthetic_firm.control_room_export import build_control_room_snapshot
from synthetic_firm.cost_ledger import add_cost_item
from synthetic_firm.deployment_health import run_vercel_preview_health_check
from synthetic_firm.store import Store
from synthetic_firm.vercel_adapter import deploy_vercel_preview, validate_vercel_command, vercel_credential_status


def test_project_local_vercel_binary_detected(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    project = tmp_path / "control-room"
    local_bin = project / "node_modules" / ".bin"
    local_bin.mkdir(parents=True)
    binary = local_bin / "vercel"
    binary.write_text("#!/usr/bin/env sh\necho 54.6.0\n", encoding="utf-8")
    binary.chmod(0o755)
    (project / "package.json").write_text('{"scripts":{"build":"vite build","typecheck":"tsc -b"}}', encoding="utf-8")
    monkeypatch.setenv("TSF_VERCEL_PROJECT_PATH", str(project))
    monkeypatch.setattr("synthetic_firm.vercel_adapter.shutil.which", lambda name: None)

    status = vercel_credential_status()

    assert status.cli_available is True
    assert "Install Vercel CLI" not in "\n".join(status.missing_requirements)


def test_missing_project_link_creates_human_task(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    project = tmp_path / "control-room"
    project.mkdir()
    (project / "package.json").write_text('{"scripts":{"build":"vite build","typecheck":"tsc -b"}}', encoding="utf-8")
    monkeypatch.setenv("TSF_VERCEL_PROJECT_PATH", str(project))
    store = Store()

    status = vercel_credential_status(store=store)

    assert status.project_linked is False
    assert any("Link Vercel project" == task.title for task in store.list_human_tasks(status="pending"))
    store.close()


def test_env_project_metadata_counts_as_link_without_public_ids(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    project = tmp_path / "control-room"
    project.mkdir()
    (project / "package.json").write_text('{"scripts":{"build":"vite build","typecheck":"tsc -b"}}', encoding="utf-8")
    monkeypatch.setenv("TSF_VERCEL_PROJECT_PATH", str(project))
    monkeypatch.setenv("TSF_VERCEL_PROJECT_ID", "prj_private")
    monkeypatch.setenv("TSF_VERCEL_ORG_ID", "org_private")

    status = vercel_credential_status()

    assert status.project_linked is True
    assert "prj_private" not in json.dumps(status.__dict__)


def test_live_preview_blocked_if_production_flag_enabled(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    monkeypatch.setenv("TSF_VERCEL_ENABLED", "true")
    monkeypatch.setenv("TSF_VERCEL_PREVIEW_DEPLOY_ENABLED", "true")
    monkeypatch.setenv("TSF_VERCEL_PRODUCTION_DEPLOY_ENABLED", "true")
    monkeypatch.setenv("TSF_DEPLOY_DRY_RUN", "false")
    monkeypatch.setenv("TSF_VERCEL_TOKEN", "vercel-secret")
    project = _linked_project(tmp_path)
    monkeypatch.setenv("TSF_VERCEL_PROJECT_PATH", str(project))
    monkeypatch.setattr("synthetic_firm.vercel_adapter.shutil.which", lambda name: "/usr/bin/vercel")
    store = Store()

    result = deploy_vercel_preview(store, dry_run=False, runner=lambda command, cwd, env: subprocess.CompletedProcess(command, 0, "", ""))

    assert result["executed"] is False
    assert result["dry_run"] is True
    assert "vercel-secret" not in _dump_sqlite(store) + json.dumps(result)
    store.close()


def test_failed_preview_command_records_safe_failure(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    monkeypatch.setenv("TSF_VERCEL_ENABLED", "true")
    monkeypatch.setenv("TSF_VERCEL_PREVIEW_DEPLOY_ENABLED", "true")
    monkeypatch.setenv("TSF_DEPLOY_DRY_RUN", "false")
    monkeypatch.setenv("TSF_VERCEL_TOKEN", "vercel-secret")
    project = _linked_project(tmp_path)
    monkeypatch.setenv("TSF_VERCEL_PROJECT_PATH", str(project))
    monkeypatch.setattr("synthetic_firm.vercel_adapter.shutil.which", lambda name: "/usr/bin/vercel")
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

    def runner(command, cwd, env):
        assert command == ["vercel", "deploy", "--yes", "--target", "preview"]
        assert "vercel-secret" not in " ".join(command)
        return subprocess.CompletedProcess(command, 1, "", "token=vercel-secret failed")

    result = deploy_vercel_preview(store, dry_run=False, runner=runner)

    assert result["executed"] is False
    assert "vercel-secret" not in _dump_sqlite(store) + json.dumps(result)
    store.close()


def test_preview_command_rejects_production_target_output(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    monkeypatch.setenv("TSF_VERCEL_ENABLED", "true")
    monkeypatch.setenv("TSF_VERCEL_PREVIEW_DEPLOY_ENABLED", "true")
    monkeypatch.setenv("TSF_DEPLOY_DRY_RUN", "false")
    monkeypatch.setenv("TSF_VERCEL_TOKEN", "vercel-secret")
    project = _linked_project(tmp_path)
    monkeypatch.setenv("TSF_VERCEL_PROJECT_PATH", str(project))
    monkeypatch.setattr("synthetic_firm.vercel_adapter.shutil.which", lambda name: "/usr/bin/vercel")
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

    def runner(command, cwd, env):
        return subprocess.CompletedProcess(
            command,
            0,
            '{"deployment":{"url":"https://example.vercel.app","target":"production"}}',
            "",
        )

    result = deploy_vercel_preview(store, dry_run=False, runner=runner)

    assert result["executed"] is False
    assert result["preview_url"] == "https://example.vercel.app"
    assert result["health"]["summary"] == "Vercel returned a production target for a preview command."
    snapshot = build_control_room_snapshot(store, audience="public")
    assert snapshot["deploymentSummary"]["latestPreviewUrl"] is None
    assert "https://example.vercel.app" not in _dump_sqlite(store)
    store.close()


def test_health_check_url_and_body_rules(monkeypatch):
    assert run_vercel_preview_health_check("http://example.vercel.app").passed is False
    assert run_vercel_preview_health_check("https://example.com").passed is False
    assert run_vercel_preview_health_check(
        "http://localhost:5173",
        env={"TSF_DEPLOY_ALLOW_LOCAL_HEALTH": "true"},
        fetcher=lambda url, timeout: (200, "Public Observer Mode read-only"),
    ).passed is True
    assert run_vercel_preview_health_check(
        "https://custom.example.com",
        env={"TSF_VERCEL_ALLOWED_PREVIEW_HOSTS": "custom.example.com"},
        fetcher=lambda url, timeout: (200, "Open Company Progress Window read-only"),
    ).passed is True
    marker_check = run_vercel_preview_health_check(
        "https://example.vercel.app",
        fetcher=lambda url, timeout: (
            200,
            '<div data-tsf-public-progress-window="true" data-tsf-read-only="true">'
            "Public Progress Window - Read-only public view - Real TSF runtime data only"
            "</div>",
        ),
    )
    assert marker_check.passed is True
    assert "marker detected" in marker_check.summary
    assert run_vercel_preview_health_check(
        "https://example.vercel.app",
        fetcher=lambda url, timeout: (200, "pending approval report status without controls"),
    ).passed is True
    assert run_vercel_preview_health_check(
        "https://example.vercel.app",
        fetcher=lambda url, timeout: (200, '<button type="button">Approve</button>'),
    ).passed is False
    assert run_vercel_preview_health_check(
        "https://example.vercel.app",
        fetcher=lambda url, timeout: (200, "approve deployment pause runtime token=abc"),
    ).passed is False


def test_production_and_mutating_commands_blocked():
    assert validate_vercel_command("vercel env add FOO") is False
    assert validate_vercel_command("vercel domains add example.com") is False
    assert validate_vercel_command("vercel alias set x y") is False
    assert validate_vercel_command("vercel project delete") is False
    assert validate_vercel_command("vercel deploy --prod") is True


def _linked_project(tmp_path):
    project = tmp_path / "control-room"
    (project / ".vercel").mkdir(parents=True)
    (project / ".vercel" / "project.json").write_text("{}", encoding="utf-8")
    (project / "package.json").write_text('{"scripts":{"build":"vite build","typecheck":"tsc -b"}}', encoding="utf-8")
    return project


def _dump_sqlite(store: Store) -> str:
    chunks: list[str] = []
    for table in ("deployment_records", "deployment_credential_status", "human_tasks", "audit_log", "notification_queue"):
        rows = store.connection.execute(f"SELECT * FROM {table}").fetchall()
        chunks.append(json.dumps([dict(row) for row in rows], sort_keys=True))
    return "\n".join(chunks)
