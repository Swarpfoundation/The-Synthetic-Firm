from __future__ import annotations

import json

import pytest

from synthetic_firm.agent_reasoning import build_agent_context
from synthetic_firm.budget_gate import check_budget_gate
from synthetic_firm.cli import main
from synthetic_firm.control_room_export import build_control_room_snapshot
from synthetic_firm.cost_budget import load_infrastructure_budget_config
from synthetic_firm.cost_ledger import (
    add_cost_item,
    create_budget_confirmation_tasks,
    list_cost_items,
    monthly_budget_state,
)
from synthetic_firm.deployment import DeploymentCheckResult
from synthetic_firm.deployment_policy import evaluate_deployment_policy, load_deployment_policy
from synthetic_firm.postgres_store import postgres_migration_plan
from synthetic_firm.store import Store, StoreError
from synthetic_firm.vercel_adapter import create_vercel_deployment_plan


def test_infrastructure_budget_defaults_to_100_eur_and_excludes_model_api():
    config = load_infrastructure_budget_config()

    assert config.currency == "EUR"
    assert config.monthly_infrastructure_budget_eur == 100
    assert config.target_monthly_infrastructure_eur == 70
    assert config.warning_threshold_eur == 50
    assert config.high_threshold_eur == 75
    assert config.critical_threshold_eur == 90
    assert config.hard_stop_eur == 100
    assert config.model_api_budget_included is False
    assert config.unknown_cost_policy == "block"


def test_cost_ledger_adds_lists_and_rejects_secret_like_values(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    store = Store()

    item = add_cost_item(
        store,
        category="render",
        provider="render",
        service_name="Render API service",
        description="Starter web service cost confirmed by founder.",
        amount_eur=7,
        recurrence="monthly",
        confidence="estimated",
        public_summary="Backend hosting cost is tracked.",
    )

    assert list_cost_items(store)[0].cost_item_id == item.cost_item_id
    assert monthly_budget_state(store).known_monthly_burn_eur == 7
    with pytest.raises(StoreError):
        add_cost_item(
            store,
            category="postgres",
            provider="neon",
            service_name="Neon Postgres",
            description="postgresql://user:password@host/db",
            amount_eur=0,
            recurrence="monthly",
            confidence="exact",
        )
    assert store.verify_audit()[0] is True
    store.close()


def test_budget_gate_blocks_unknown_cost_action_and_creates_human_tasks(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    store = Store()

    decision = check_budget_gate(store, "vercel_preview_deploy", unknown_cost_possible=True)

    assert decision.allowed is False
    assert "Unknown infrastructure cost" in decision.reason
    assert decision.human_task_ids
    assert any("cost" in task.title.lower() for task in store.list_human_tasks(status="pending"))
    assert store.verify_audit()[0] is True
    store.close()


def test_budget_gate_blocks_over_100_projected_new_paid_action(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    store = Store()
    add_cost_item(
        store,
        category="render",
        provider="render",
        service_name="Render API service",
        description="Founder-confirmed high infrastructure burn.",
        amount_eur=101,
        recurrence="monthly",
        confidence="exact",
    )

    decision = check_budget_gate(store, "render_deploy", new_recurring_cost=True)

    assert decision.allowed is False
    assert decision.status == "blocked"
    store.close()


def test_agent_context_and_public_export_include_sanitized_budget(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    store = Store()
    create_budget_confirmation_tasks(store)

    context = build_agent_context(store, agent_id="atlas")
    snapshot = build_control_room_snapshot(store, audience="public")
    dumped = json.dumps(snapshot) + context

    assert "monthly_infrastructure_budget_eur" in context
    assert snapshot["infrastructureBudget"]["monthlyInfrastructureBudgetEur"] == 100
    assert snapshot["infrastructureBudget"]["unknownCostCount"] >= 1
    assert "DATABASE_URL" not in dumped
    assert "card" not in dumped.lower()
    store.close()


def test_deployment_policy_budget_gate_blocks_live_unknown_preview(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    monkeypatch.setenv("TSF_DEPLOY_DRY_RUN", "false")
    monkeypatch.setenv("TSF_VERCEL_TOKEN", "present-but-redacted")
    store = Store()
    plan = create_vercel_deployment_plan(environment="preview")
    checks = (DeploymentCheckResult("all checks", True, "passed"),)

    decision = evaluate_deployment_policy(store, plan, checks, policy=load_deployment_policy())

    assert decision.allowed is False
    assert "cost" in decision.reason.lower()
    store.close()


def test_budget_cli_commands_work_and_output_is_safe(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))

    assert main(["budget-status"]) == 0
    assert "infrastructureBudget" in capsys.readouterr().out

    assert main(["budget-create-confirmation-tasks"]) == 0
    assert "budget confirmation" in capsys.readouterr().out

    assert main(["budget-public-summary"]) == 0
    out = capsys.readouterr().out
    assert "monthlyInfrastructureBudgetEur" in out
    assert "DATABASE_URL" not in out


def test_postgres_migration_includes_cost_tables_and_is_non_destructive():
    plan = postgres_migration_plan()
    sql = "\n".join(plan.statements)

    assert plan.destructive is False
    assert "CREATE TABLE IF NOT EXISTS cost_items" in sql
    assert "CREATE TABLE IF NOT EXISTS cost_decisions" in sql
    assert "DROP TABLE" not in sql.upper()
