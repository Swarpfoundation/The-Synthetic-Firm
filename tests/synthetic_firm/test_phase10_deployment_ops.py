from __future__ import annotations

import json
import subprocess

from synthetic_firm.cli import main
from synthetic_firm.control_room_export import build_control_room_snapshot
from synthetic_firm.deployment import DeploymentCheckResult, deployment_plan_to_dict
from synthetic_firm.deployment_checks import run_deployment_checks
from synthetic_firm.deployment_policy import evaluate_deployment_policy, load_deployment_policy, sentinel_review_deployment_plan
from synthetic_firm.render_adapter import (
    create_render_deployment_plan,
    deploy_render_service,
    render_status,
    validate_render_command,
)
from synthetic_firm.store import Store
from synthetic_firm.vercel_adapter import (
    create_vercel_deployment_plan,
    deploy_vercel_preview,
    validate_vercel_command,
    vercel_status,
)


def test_deployment_policy_defaults(monkeypatch):
    monkeypatch.delenv("TSF_DEPLOY_DRY_RUN", raising=False)
    monkeypatch.delenv("TSF_DEPLOY_AUTONOMOUS_PRODUCTION", raising=False)

    policy = load_deployment_policy()

    assert policy.dry_run is True
    assert policy.autonomous_preview is True
    assert policy.autonomous_production is False


def test_vercel_disabled_by_default_and_missing_token_creates_human_task(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    monkeypatch.delenv("TSF_VERCEL_ENABLED", raising=False)
    monkeypatch.delenv("TSF_VERCEL_TOKEN", raising=False)
    store = Store()

    status = vercel_status()
    result = deploy_vercel_preview(store, dry_run=True)

    assert status["enabled"] is False
    assert result["executed"] is False
    assert result["policy"]["allowed"] is False
    assert store.list_human_tasks(status="pending")
    dumped = _dump_sqlite(store)
    assert "TSF_VERCEL_TOKEN" not in dumped
    assert store.verify_audit()[0] is True
    store.close()


def test_vercel_token_presence_never_printed_or_persisted(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    monkeypatch.setenv("TSF_VERCEL_TOKEN", "vercel-secret-token-value")
    store = Store()

    plan = create_vercel_deployment_plan(environment="preview")
    record = deploy_vercel_preview(store, dry_run=True)
    dumped = json.dumps(record) + json.dumps(deployment_plan_to_dict(plan)) + _dump_sqlite(store)

    assert "vercel-secret-token-value" not in dumped
    store.close()


def test_vercel_command_boundaries():
    assert validate_vercel_command("vercel --version") is True
    assert validate_vercel_command("vercel deploy") is True
    assert validate_vercel_command("vercel deploy --prod") is True
    assert validate_vercel_command("vercel env add SECRET") is False
    assert validate_vercel_command("vercel domains add example.com") is False
    assert validate_vercel_command("vercel project delete") is False


def test_render_disabled_missing_access_creates_human_task(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    monkeypatch.delenv("TSF_RENDER_ENABLED", raising=False)
    monkeypatch.delenv("TSF_RENDER_API_KEY", raising=False)
    store = Store()

    status = render_status()
    result = deploy_render_service(store, target="render_backend_api", dry_run=True)

    assert status["enabled"] is False
    assert result["executed"] is False
    assert any("Render" in task.title for task in store.list_human_tasks(status="pending"))
    assert "TSF_RENDER_API_KEY" not in _dump_sqlite(store)
    store.close()


def test_render_command_boundaries():
    assert validate_render_command("render --version") is True
    assert validate_render_command("render blueprints validate render.yaml") is True
    assert validate_render_command("render deploys list SERVICE_ID") is True
    assert validate_render_command("render deploys create SERVICE_ID --wait --confirm") is True
    assert validate_render_command("render services update SERVICE_ID") is False
    assert validate_render_command("render ssh SERVICE_ID") is False
    assert validate_render_command("render psql DATABASE_URL") is False


def test_policy_blocks_production_by_default(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    monkeypatch.setenv("TSF_VERCEL_TOKEN", "present-but-not-printed")
    monkeypatch.delenv("TSF_DEPLOY_AUTONOMOUS_PRODUCTION", raising=False)
    store = Store()
    plan = create_vercel_deployment_plan(environment="production")
    checks = (DeploymentCheckResult("all checks", True, "All validation passed."),)

    decision = evaluate_deployment_policy(store, plan, checks)

    assert decision.allowed is False
    assert decision.state == "production_blocked"
    assert "disabled" in decision.reason
    store.close()


def test_failed_check_and_secret_like_output_block_deploy(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    monkeypatch.setenv("TSF_VERCEL_TOKEN", "present-but-not-printed")
    store = Store()
    plan = create_vercel_deployment_plan(environment="preview")

    failed = evaluate_deployment_policy(store, plan, (DeploymentCheckResult("brand guard", False, "failed"),))
    secret = evaluate_deployment_policy(store, plan, (DeploymentCheckResult("build", True, "ok", "secret=abc"),))

    assert failed.allowed is False
    assert failed.state == "validation_failed"
    assert secret.allowed is False
    assert secret.state == "validation_failed"
    store.close()


def test_sentinel_blocks_missing_health_or_rollback():
    plan = create_vercel_deployment_plan(environment="production")
    object.__setattr__(plan, "rollback_plan", type(plan.rollback_plan)(steps=(), summary="missing"))

    decision = sentinel_review_deployment_plan(plan, (DeploymentCheckResult("checks", True, "passed"),))

    assert decision.allowed is False
    assert "rollback" in decision.reason.lower()


def test_deployment_checks_support_mocked_runner(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    store = Store()

    def runner(command, cwd):
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    checks = run_deployment_checks(store, target="vercel_frontend", runner=runner, run_heavy=True)

    assert checks
    assert all(check.passed for check in checks)
    store.close()


def test_public_export_includes_safe_deployment_summary(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    monkeypatch.setenv("TSF_VERCEL_TOKEN", "vercel-secret-token-value")
    store = Store()
    deploy_vercel_preview(store, dry_run=True)

    snapshot = build_control_room_snapshot(store, audience="public")
    dumped = json.dumps(snapshot)

    assert snapshot["deploymentSummary"]["latestState"]
    assert "deploymentSummary" in snapshot
    assert "vercel-secret-token-value" not in dumped
    assert "token" not in dumped.lower()
    assert "service_id" not in dumped.lower()
    store.close()


def test_internal_cli_deployment_commands(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))

    assert main(["deploy-status"]) == 0
    assert "Deployment operations status loaded" in capsys.readouterr().out

    assert main(["deploy-plan", "--target", "vercel_frontend", "--env", "preview"]) == 0
    assert "vercel_frontend" in capsys.readouterr().out

    assert main(["deploy-preview", "--target", "vercel_frontend", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "executed" in out
    assert "TSF_VERCEL_TOKEN" not in out


def _dump_sqlite(store: Store) -> str:
    chunks: list[str] = []
    for table in ("deployment_records", "human_tasks", "audit_log"):
        rows = store.connection.execute(f"SELECT * FROM {table}").fetchall()
        chunks.append(json.dumps([dict(row) for row in rows], sort_keys=True))
    return "\n".join(chunks)
