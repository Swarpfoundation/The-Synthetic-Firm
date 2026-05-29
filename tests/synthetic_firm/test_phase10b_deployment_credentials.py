from __future__ import annotations

import json
import subprocess

from synthetic_firm.cli import main
from synthetic_firm.control_room_export import build_control_room_snapshot
from synthetic_firm.cost_ledger import add_cost_item
from synthetic_firm.deployment import credential_status_to_dict
from synthetic_firm import render_adapter
from synthetic_firm.render_adapter import (
    deploy_render_service,
    render_credential_status,
    render_readiness,
    render_status,
    validate_render_command,
)
from synthetic_firm.store import Store
from synthetic_firm.vercel_adapter import (
    deploy_vercel_preview,
    run_vercel_preview_health_check,
    validate_vercel_command,
    vercel_credential_status,
)


def test_vercel_missing_setup_creates_precise_human_tasks(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    monkeypatch.delenv("TSF_VERCEL_TOKEN", raising=False)
    monkeypatch.delenv("VERCEL_TOKEN", raising=False)
    store = Store()

    status = vercel_credential_status(store=store)

    assert status.credential_present is False
    assert status.human_task_required is True
    assert any("Vercel" in task.title for task in store.list_human_tasks(status="pending"))
    dumped = _dump_sqlite(store)
    assert "TSF_VERCEL_TOKEN" not in dumped
    assert "VERCEL_TOKEN=" not in dumped
    store.close()


def test_vercel_token_presence_reports_env_without_printing_value(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    monkeypatch.setenv("TSF_VERCEL_TOKEN", "vercel-token-secret-value")
    store = Store()

    status = vercel_credential_status(store=store)
    payload = json.dumps(credential_status_to_dict(status)) + _dump_sqlite(store)

    assert status.credential_present is True
    assert status.credential_source == "env"
    assert "vercel-token-secret-value" not in payload
    store.close()


def test_vercel_preview_live_disabled_by_default(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    monkeypatch.setenv("TSF_VERCEL_TOKEN", "vercel-token-secret-value")
    monkeypatch.delenv("TSF_VERCEL_PREVIEW_DEPLOY_ENABLED", raising=False)
    store = Store()

    result = deploy_vercel_preview(store, dry_run=False)

    assert result["executed"] is False
    assert result["dry_run"] is True
    assert "vercel-token-secret-value" not in json.dumps(result) + _dump_sqlite(store)
    store.close()


def test_vercel_live_preview_uses_env_token_not_command_string(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    monkeypatch.setenv("TSF_VERCEL_ENABLED", "true")
    monkeypatch.setenv("TSF_VERCEL_PREVIEW_DEPLOY_ENABLED", "true")
    monkeypatch.setenv("TSF_DEPLOY_DRY_RUN", "false")
    monkeypatch.setenv("TSF_VERCEL_TOKEN", "vercel-token-secret-value")
    monkeypatch.setattr("synthetic_firm.vercel_adapter.shutil.which", lambda name: "/usr/bin/vercel")
    monkeypatch.setattr("synthetic_firm.vercel_adapter._vercel_version_redacted", lambda: "vercel 1.0.0")
    project = tmp_path / "apps" / "control-room"
    (project / ".vercel").mkdir(parents=True)
    (project / ".vercel" / "project.json").write_text("{}", encoding="utf-8")
    (project / "package.json").write_text('{"scripts":{"build":"vite build","typecheck":"tsc -b"}}', encoding="utf-8")
    monkeypatch.setenv("TSF_VERCEL_PROJECT_PATH", str(project))
    store = Store()
    add_cost_item(
        store,
        category="vercel",
        provider="vercel",
        service_name="Vercel public Progress Window",
        description="Founder-confirmed preview deploy cost is within budget.",
        amount_eur=0,
        recurrence="monthly",
        confidence="estimated",
    )
    seen: dict[str, object] = {}

    def runner(command, cwd, env):
        seen["command"] = command
        seen["env"] = env
        return subprocess.CompletedProcess(command, 0, stdout="https://preview-safe.vercel.app\n", stderr="")

    monkeypatch.setattr(
        "synthetic_firm.vercel_adapter.run_vercel_preview_health_check",
        lambda url, env=None: type("Health", (), {"name": "preview health check", "passed": True, "summary": "Preview health check passed.", "output_redacted": "HTTP 200"})(),
    )

    result = deploy_vercel_preview(store, dry_run=False, runner=runner)

    assert result["executed"] is True
    assert seen["command"] == ["vercel", "deploy", "--yes", "--target", "preview"]
    assert "vercel-token-secret-value" not in " ".join(seen["command"])
    assert seen["env"]["VERCEL_TOKEN"] == "vercel-token-secret-value"
    assert "vercel-token-secret-value" not in json.dumps(result) + _dump_sqlite(store)
    store.close()


def test_vercel_command_boundaries_phase10b():
    assert validate_vercel_command("vercel deploy") is True
    assert validate_vercel_command("vercel deploy --prod") is True
    assert validate_vercel_command("vercel env pull") is False
    assert validate_vercel_command("vercel domains add example.com") is False
    assert validate_vercel_command("vercel alias set x y") is False
    assert validate_vercel_command("vercel project delete") is False


def test_vercel_health_check_is_mockable_and_blocks_bad_content():
    good = run_vercel_preview_health_check(
        "https://tsf-preview.vercel.app",
        fetcher=lambda url, timeout: (200, "Public Observer Mode - read-only real runtime data"),
    )
    bad = run_vercel_preview_health_check(
        "https://tsf-preview.vercel.app",
        fetcher=lambda url, timeout: (200, "pause runtime token=abc"),
    )

    assert good.passed is True
    assert bad.passed is False
    assert "abc" not in bad.output_redacted


def test_render_missing_setup_creates_human_tasks_and_public_hides_ids(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    monkeypatch.delenv("TSF_RENDER_API_KEY", raising=False)
    monkeypatch.setenv("TSF_RENDER_API_SERVICE_ID", "srv-private-123")
    store = Store()

    result = render_readiness(store)
    snapshot = build_control_room_snapshot(store, audience="public")
    dumped = json.dumps(result) + json.dumps(snapshot) + _dump_sqlite(store)

    assert result["executed"] is False
    assert any("Render" in task.title for task in store.list_human_tasks(status="pending"))
    assert "srv-private-123" not in json.dumps(snapshot)
    assert "TSF_RENDER_API_KEY" not in dumped
    store.close()


def test_render_deploy_disabled_and_production_blocked(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    monkeypatch.setenv("TSF_RENDER_API_KEY", "render-secret-key-value")
    monkeypatch.setenv("TSF_RENDER_API_SERVICE_ID", "srv-private-123")
    monkeypatch.delenv("TSF_RENDER_DEPLOY_ENABLED", raising=False)
    store = Store()

    staging = deploy_render_service(store, target="render_backend_api", environment="staging", dry_run=False)
    production = deploy_render_service(store, target="render_backend_api", environment="production", dry_run=True)

    assert staging["executed"] is False
    assert production["executed"] is False
    assert "render-secret-key-value" not in json.dumps(staging) + json.dumps(production) + _dump_sqlite(store)
    store.close()


def test_render_staging_live_uses_api_without_cli(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    env = {
        "TSF_RENDER_ENABLED": "true",
        "TSF_RENDER_DEPLOY_ENABLED": "true",
        "TSF_RENDER_DEPLOY_METHOD": "api",
        "TSF_RENDER_API_KEY": "render-secret-key-value",
        "TSF_RENDER_API_SERVICE_ID": "srv-private-123",
        "TSF_DEPLOY_DRY_RUN": "false",
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(render_adapter.shutil, "which", lambda _name: None)
    monkeypatch.setattr(render_adapter, "_post_render_deploy", lambda _env, _service_id: {"id": "dep-private-123"})
    store = Store()
    add_cost_item(
        store,
        category="render",
        provider="render",
        service_name="Render API service",
        description="Render backend hosting.",
        amount_eur=7,
        recurrence="monthly",
        confidence="estimated",
        public_summary="Backend hosting cost is tracked.",
    )

    status = render_status(env=env)
    result = deploy_render_service(store, target="render_backend_api", environment="staging", dry_run=False, env=env)
    dumped = json.dumps(result) + _dump_sqlite(store)

    assert status["deploy_method"] == "api"
    assert status["cli_available"] is False
    assert result["executed"] is True
    assert result["render_deploy_id_present"] is True
    assert "render-secret-key-value" not in dumped
    assert "srv-private-123" not in dumped
    assert "dep-private-123" not in dumped
    assert store.verify_audit()[0] is True
    store.close()


def test_render_command_boundaries_phase10b():
    assert validate_render_command("render blueprints validate render.yaml") is True
    assert validate_render_command("render deploys create SERVICE_ID --wait --confirm") is True
    assert validate_render_command("render services update SERVICE_ID") is False
    assert validate_render_command("render ssh SERVICE_ID") is False
    assert validate_render_command("render psql DATABASE_URL") is False


def test_deployment_notifications_dedupe(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    store = Store()

    deploy_vercel_preview(store, dry_run=True)
    deploy_vercel_preview(store, dry_run=True)

    notifications = store.connection.execute("SELECT * FROM notification_queue").fetchall()
    bodies = [row["body"] for row in notifications]
    assert len(bodies) == len(set(bodies))
    assert all("token" not in body.lower() for body in bodies)
    store.close()


def test_internal_cli_phase10b_commands(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))

    assert main(["deployment-credentials-status"]) == 0
    assert "Deployment credential status checked safely" in capsys.readouterr().out

    assert main(["validate-deploy-tools"]) == 0
    assert "Deployment tool validation completed" in capsys.readouterr().out

    assert main(["vercel-preview", "--dry-run"]) == 0
    assert "executed" in capsys.readouterr().out

    assert main(["render-readiness"]) == 0
    assert "Render readiness evaluated" in capsys.readouterr().out

    assert main(["deployment-human-tasks"]) == 0
    assert "humanTasks" in capsys.readouterr().out


def _dump_sqlite(store: Store) -> str:
    chunks: list[str] = []
    for table in ("deployment_records", "human_tasks", "audit_log", "notification_queue"):
        rows = store.connection.execute(f"SELECT * FROM {table}").fetchall()
        chunks.append(json.dumps([dict(row) for row in rows], sort_keys=True))
    return "\n".join(chunks)
