"""The Synthetic Firm command line interface."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path

from synthetic_firm.agent_registry import AgentRegistry
from synthetic_firm.autonomous_workday import (
    autonomous_status,
    close_workday,
    generate_private_founder_report,
    generate_public_daily_report,
    get_current_workday,
    get_latest_plan,
    list_agent_work,
    plan_to_dict,
    run_agent_turn,
    run_cycle,
    start_workday,
    workday_to_dict,
)
from synthetic_firm.autonomous_ops import autonomous_ops_status, run_autonomous_ops_once
from synthetic_firm.approval import approval_to_dict, create_approval_request, format_telegram_approval
from synthetic_firm.approval_inbox import (
    approval_to_inbox_dict,
    decide_pending_approval,
    format_approval_detail,
    list_pending_approvals,
)
from synthetic_firm.approval_signing import default_expiry, sign_approval_decision, verify_signed_decision
from synthetic_firm.budget import BudgetPolicy, BudgetUsage, budget_status_text, evaluate_budget
from synthetic_firm.budget_gate import check_budget_gate
from synthetic_firm.budget_log import append_budget_log
from synthetic_firm.code_change import (
    apply_code_change_proposal,
    code_change_public_summary,
    create_code_change_proposal,
    internally_review_code_change_proposal,
    list_code_change_proposals,
    proposal_to_dict as code_proposal_to_dict,
)
from synthetic_firm.control_room_export import export_control_room_state
from synthetic_firm.control_room_api import serve_control_room_api
from synthetic_firm.cost_ledger import (
    add_cost_item,
    budget_private_report,
    budget_public_summary,
    cost_item_to_dict,
    create_budget_confirmation_tasks,
    list_cost_items,
    monthly_budget_state,
)
from synthetic_firm.deployment import (
    credential_status_to_dict,
    deployment_plan_to_dict,
    deployment_record_to_dict,
    list_deployment_records,
    save_deployment_record,
)
from synthetic_firm.deployment_checks import check_summary, run_deployment_checks
from synthetic_firm.deployment_policy import evaluate_deployment_policy, sentinel_review_deployment_plan
from synthetic_firm.render_adapter import (
    create_render_deployment_plan,
    deploy_render_service,
    render_credential_status,
    render_readiness,
    render_status,
)
from synthetic_firm.render_runtime import (
    public_api_smoke,
    render_api_readiness,
    scheduler_checkpoint_smoke,
    scheduler_render_readiness,
)
from synthetic_firm.human_tasks import format_human_task_for_telegram, human_task_to_dict
from synthetic_firm.execution_queue import (
    enqueue_action,
    list_queue,
    process_execution_queue,
    queue_item_to_dict,
)
from synthetic_firm.agent_reasoning import build_agent_reasoning_request
from synthetic_firm.llm_client import complete_agent_reasoning, provider_status as model_provider_status, response_to_dict
from synthetic_firm.llm_router import env_with_api_key_alias, resolve_model_route
from synthetic_firm.message_bus import create_message, message_to_dict
from synthetic_firm.notification_queue import (
    enqueue_notification,
    list_notifications,
    notification_to_dict,
    send_notifications,
)
from synthetic_firm.policy import load_project_policy, validate_agent_profile
from synthetic_firm.provider_auth import provider_routes, route_to_dict, session_to_dict
from synthetic_firm.provider_auth import get_provider_route
from synthetic_firm.provider_auth_adapters import provider_auth_status, start_provider_auth
from synthetic_firm.provider_auth_redaction import redact_auth_text
from synthetic_firm.provider_auth_store import list_auth_sessions, revoke_auth_metadata, save_auth_session
from synthetic_firm.provider_auth_telegram import format_auth_handoff, format_auth_status
from synthetic_firm.provider_runtime import (
    build_runtime_invocation,
    invocation_to_dict,
    invoke_provider_runtime,
    provider_runtime_status,
    result_to_dict,
)
from synthetic_firm.public_progress_smoke import run_public_progress_e2e_smoke
from synthetic_firm.proposals import (
    create_self_improvement_proposal,
    create_worker_proposal,
    proposal_to_dict,
)
from synthetic_firm.report import DailyReportInput, generate_daily_report
from synthetic_firm.runtime_permissions import (
    RuntimeAction,
    RuntimePermissionError,
    evaluate_runtime_action,
    validate_provider_auth_actor,
)
from synthetic_firm.scheduler import (
    run_checkpoint_once,
    run_scheduler_loop,
    scheduler_dry_run_plan,
    scheduler_lock_status,
    scheduler_status,
)
from synthetic_firm.store import Store, init_store
from synthetic_firm.store_backend import db_migrate, db_redaction_smoke, db_smoke, db_status, db_verify
from synthetic_firm.task import create_task, task_to_dict
from synthetic_firm.vercel_adapter import (
    create_vercel_deployment_plan,
    deploy_vercel_preview,
    run_vercel_preview_health_check,
    vercel_credential_status,
    vercel_status,
)
from synthetic_firm.telegram_adapter import (
    format_outgoing_approval,
    handle_telegram_command_dry_run,
    parse_telegram_command,
)
from synthetic_firm.telegram_live import (
    handle_control_command,
    handle_founder_telegram_text,
    load_telegram_config,
    poll_once,
    send_pending_notifications,
    telegram_founder_sync_once,
    telegram_founder_smoke,
    telegram_status,
)
from synthetic_firm.workday import evaluate_workday, load_workday_config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="synthetic-firm",
        description="Run The Synthetic Firm agent profile.",
    )
    parser.add_argument("agent", help="Agent id: atlas, scout, forge, pulse, sentinel")
    parser.add_argument("--profiles", default="agents/profiles.yaml", help="Path to agent profiles YAML")
    parser.add_argument("--policy", default="agents/policy.yaml", help="Path to policy YAML")
    parser.add_argument("--dry-run", action="store_true", help="Print resolved non-secret routing metadata")
    return parser


ORCHESTRATOR_COMMANDS = frozenset(
    {
        "show-workday-status",
        "create-dry-run-task",
        "simulate-agent-message",
        "create-approval-request",
        "format-telegram-approval",
        "propose-worker",
        "propose-self-improvement",
        "generate-daily-report",
        "show-budget-status",
        "init-store",
        "store-status",
        "create-task",
        "list-tasks",
        "send-agent-message",
        "list-messages",
        "create-approval",
        "decide-approval",
        "verify-approval",
        "parse-telegram-command",
        "handle-telegram-command-dry-run",
        "audit-log",
        "verify-audit-log",
        "pause",
        "resume",
        "kill",
        "runtime-status",
        "list-daily-reports",
        "budget-status",
        "budget-add-cost",
        "budget-list-costs",
        "budget-monthly-report",
        "budget-check-action",
        "budget-create-confirmation-tasks",
        "budget-public-summary",
        "code-proposal-create",
        "code-proposal-list",
        "code-proposal-review",
        "code-proposal-apply",
        "code-proposal-public-summary",
        "autonomous-ops-status",
        "autonomous-ops-once",
        "telegram-status",
        "telegram-founder-status",
        "telegram-dry-run-command",
        "telegram-poll-once",
        "telegram-founder-sync-once",
        "telegram-send-pending-notifications",
        "telegram-founder-smoke",
        "list-approvals",
        "show-approval",
        "approve",
        "deny",
        "list-execution-queue",
        "process-execution-queue",
        "list-notifications",
        "send-notifications",
        "send-daily-report",
        "enqueue-action",
        "auth-start",
        "auth-status",
        "auth-list",
        "auth-revoke",
        "provider-routes",
        "provider-route-status",
        "auth-redact-test",
        "auth-telegram-message",
        "provider-runtime-status",
        "provider-runtime-plan",
        "provider-runtime-invoke",
        "provider-status",
        "run-agent-reasoning",
        "run-model-smoke",
        "export-control-room-state",
        "serve-control-room-api",
        "autonomous-status",
        "start-workday",
        "run-workday-cycle",
        "run-agent-turn",
        "close-workday",
        "generate-atlas-report",
        "list-agent-work",
        "list-human-tasks",
        "show-human-task",
        "scheduler-status",
        "scheduler-checkpoint-once",
        "scheduler-loop",
        "scheduler-lock-status",
        "scheduler-dry-run-plan",
        "deploy-status",
        "deploy-plan",
        "deploy-checks",
        "deploy-preview",
        "deploy-production",
        "render-status",
        "vercel-status",
        "deployment-history",
        "deployment-credentials-status",
        "deployment-setup-status",
        "create-deployment-setup-human-tasks",
        "validate-deploy-tools",
        "validate-vercel-setup",
        "validate-render-setup",
        "vercel-preview",
        "vercel-health-check",
        "render-readiness",
        "render-deploy-staging",
        "deployment-human-tasks",
        "deployment-notifications",
        "public-progress-e2e-smoke",
        "db-status",
        "db-migrate",
        "db-verify",
        "db-smoke",
        "db-redaction-smoke",
        "scheduler-render-readiness",
        "scheduler-checkpoint-smoke",
        "render-api-readiness",
        "public-api-smoke",
    }
)


def build_orchestrator_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="synthetic-firm",
        description="The Synthetic Firm safe orchestration commands.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-store", help="Initialize the persistent local store")
    sub.add_parser("store-status", help="Show persistent local store status")

    workday = sub.add_parser("show-workday-status", help="Show whether the firm is inside work hours")
    workday.add_argument("--config", default="agents/workday.yaml")

    task = sub.add_parser("create-dry-run-task", help="Create a safe dry-run task object")
    task.add_argument("--title", required=True)
    task.add_argument("--objective", required=True)
    task.add_argument("--created-by", default="atlas")
    task.add_argument("--assigned-agent")
    task.add_argument("--risk-level", default="low")
    task.add_argument("--external-effect", action="store_true")
    task.add_argument("--budget-limit", type=float)
    task.add_argument("--max-steps", type=int)

    message = sub.add_parser("simulate-agent-message", help="Route an internal message through the orchestrator")
    message.add_argument("--sender", required=True)
    message.add_argument("--recipient")
    message.add_argument("--channel")
    message.add_argument("--task-id")
    message.add_argument("--message-type", default="note")
    message.add_argument("--content", required=True)

    approval = sub.add_parser("create-approval-request", help="Create an approval request object")
    _add_approval_args(approval)

    telegram = sub.add_parser("format-telegram-approval", help="Format an approval request for Telegram")
    _add_approval_args(telegram)

    worker = sub.add_parser("propose-worker", help="Create a proposed worker spec")
    worker.add_argument("--proposed-by", required=True)
    worker.add_argument("--name", required=True)
    worker.add_argument("--role", required=True)
    worker.add_argument("--reason", required=True)
    worker.add_argument("--tool", action="append", default=[])
    worker.add_argument("--budget", type=float)
    worker.add_argument("--risk-level", default="low")

    improvement = sub.add_parser("propose-self-improvement", help="Create a self-improvement proposal")
    improvement.add_argument("--agent-id", required=True)
    improvement.add_argument("--capability-gap", required=True)
    improvement.add_argument("--proposed-change", required=True)
    improvement.add_argument("--file", action="append", default=[], dest="files")
    improvement.add_argument("--permission-change", action="store_true")
    improvement.add_argument("--budget-change", action="store_true")
    improvement.add_argument("--risk-level", default="low")

    report = sub.add_parser("generate-daily-report", help="Generate a safe plain-English sample report")
    report.add_argument("--question", action="append", default=[])
    report.add_argument("--next-action", action="append", default=[])

    budget = sub.add_parser("show-budget-status", help="Evaluate budget and loop limits")
    budget.add_argument("--agent-limit", type=float, required=True)
    budget.add_argument("--task-limit", type=float, required=True)
    budget.add_argument("--company-limit", type=float, required=True)
    budget.add_argument("--max-loop-steps", type=int, required=True)
    budget.add_argument("--max-tool-calls", type=int, required=True)
    budget.add_argument("--agent-spend", type=float, required=True)
    budget.add_argument("--task-spend", type=float, required=True)
    budget.add_argument("--company-spend", type=float, required=True)
    budget.add_argument("--loop-steps", type=int, required=True)
    budget.add_argument("--tool-calls", type=int, required=True)
    budget.add_argument("--dry-run", action="store_true")

    persisted_task = sub.add_parser("create-task", help="Create and persist an internal task")
    persisted_task.add_argument("--title", required=True)
    persisted_task.add_argument("--objective", required=True)
    persisted_task.add_argument("--created-by", default="atlas")
    persisted_task.add_argument("--assigned-agent")
    persisted_task.add_argument("--risk-level", default="low")
    persisted_task.add_argument("--external-effect", action="store_true")
    persisted_task.add_argument("--budget-limit", type=float)
    persisted_task.add_argument("--max-steps", type=int)
    persisted_task.add_argument("--summary", required=True)

    list_tasks = sub.add_parser("list-tasks", help="List persisted tasks")
    list_tasks.add_argument("--status")

    send_message = sub.add_parser("send-agent-message", help="Persist an orchestrator-routed agent message")
    send_message.add_argument("--sender", required=True)
    send_message.add_argument("--recipient")
    send_message.add_argument("--channel")
    send_message.add_argument("--task-id")
    send_message.add_argument("--message-type", default="note")
    send_message.add_argument("--content", required=True)

    list_messages = sub.add_parser("list-messages", help="List persisted agent messages")
    list_messages.add_argument("--task-id")
    list_messages.add_argument("--channel")

    persistent_approval = sub.add_parser("create-approval", help="Persist an approval request")
    _add_approval_args(persistent_approval)

    decision = sub.add_parser("decide-approval", help="Create a signed or dry-run approval decision")
    decision.add_argument("--approval-id", required=True)
    decision.add_argument("--decision", choices=["approved", "denied"], required=True)
    decision.add_argument("--decided-by", default="founder")
    decision.add_argument("--dry-run", action="store_true")

    verify = sub.add_parser("verify-approval", help="Verify the latest persisted approval decision")
    verify.add_argument("--approval-id", required=True)

    parse = sub.add_parser("parse-telegram-command", help="Parse a dry-run Telegram command")
    parse.add_argument("text")

    handle = sub.add_parser("handle-telegram-command-dry-run", help="Handle a Telegram command without network calls")
    handle.add_argument("text")

    sub.add_parser("audit-log", help="Print append-only audit entries")
    sub.add_parser("verify-audit-log", help="Verify audit hash-chain integrity")
    sub.add_parser("pause", help="Pause agent work")
    sub.add_parser("resume", help="Resume paused agent work")
    sub.add_parser("kill", help="Kill agent work until manual recovery outside Phase 3")
    sub.add_parser("runtime-status", help="Show runtime status")

    persistent_report = sub.add_parser("list-daily-reports", help="List saved daily reports")
    persistent_report.add_argument("--limit", type=int, default=10)

    budget_status = sub.add_parser("budget-status", help="Show persisted budget totals")
    budget_status.add_argument("--agent-id")
    budget_status.add_argument("--task-id")
    budget_add = sub.add_parser("budget-add-cost", help="Internal/dev: add infrastructure budget cost item")
    budget_add.add_argument("--provider", required=True)
    budget_add.add_argument("--service", required=True)
    budget_add.add_argument("--description", default="Infrastructure cost item.")
    budget_add.add_argument("--amount-eur", type=float)
    budget_add.add_argument("--category", default="other_infrastructure")
    budget_add.add_argument("--recurrence", default="monthly")
    budget_add.add_argument("--confidence", default="estimated")
    budget_add.add_argument("--source", default="manual")
    budget_add.add_argument("--public-summary")
    budget_list = sub.add_parser("budget-list-costs", help="Internal/dev: list infrastructure budget cost items")
    budget_list.add_argument("--month")
    budget_list.add_argument("--category")
    sub.add_parser("budget-monthly-report", help="Internal/dev: show private infrastructure budget report")
    budget_check = sub.add_parser("budget-check-action", help="Internal/dev: check an infrastructure budget action")
    budget_check.add_argument("action_name")
    budget_check.add_argument("--new-recurring-cost", action="store_true")
    budget_check.add_argument("--unknown-cost-possible", action="store_true")
    sub.add_parser("budget-create-confirmation-tasks", help="Internal/dev: create infrastructure cost confirmation HumanTasks")
    sub.add_parser("budget-public-summary", help="Internal/dev: show public-safe infrastructure budget summary")

    code_create = sub.add_parser("code-proposal-create", help="Internal/dev: create a Forge code-change proposal")
    code_create.add_argument("--title", required=True)
    code_create.add_argument("--summary", required=True)
    code_create.add_argument("--rationale", required=True)
    code_create.add_argument("--patch-file", required=True)
    code_create.add_argument("--created-by", default="forge")
    code_create.add_argument("--target-branch")
    code_create.add_argument("--base-branch", default="main")
    code_create.add_argument("--tests-command")
    code_create.add_argument("--public-summary")
    code_list = sub.add_parser("code-proposal-list", help="Internal/dev: list Forge code-change proposals")
    code_list.add_argument("--status")
    code_list.add_argument("--limit", type=int, default=20)
    code_review = sub.add_parser("code-proposal-review", help="Internal/dev: run internal safety review for a code proposal")
    code_review.add_argument("proposal_id")
    code_apply = sub.add_parser("code-proposal-apply", help="Internal/dev: apply, test, commit, and optionally push an approved code proposal")
    code_apply.add_argument("proposal_id")
    code_apply.add_argument("--repo-path", default=".")
    code_apply.add_argument("--tests-command")
    code_apply.add_argument("--live", action="store_true")
    code_apply.add_argument("--push", action="store_true")
    sub.add_parser("code-proposal-public-summary", help="Internal/dev: show public-safe Forge code proposal summary")
    sub.add_parser("autonomous-ops-status", help="Internal/dev: show bounded autonomous code/deploy ops status")
    sub.add_parser("autonomous-ops-once", help="Internal/dev: run one bounded autonomous code/deploy ops pass")

    sub.add_parser("telegram-status", help="Show Telegram founder-interface configuration status")
    sub.add_parser("telegram-founder-status", help="Internal/dev: show Telegram Founder Inbox readiness")
    telegram_dry = sub.add_parser("telegram-dry-run-command", help="Handle a Telegram command without network calls")
    telegram_dry.add_argument("text")
    telegram_dry.add_argument("--chat-id", default="dry-run-founder")
    sub.add_parser("telegram-poll-once", help="Run one safe Telegram polling cycle")
    telegram_sync = sub.add_parser("telegram-founder-sync-once", help="Run one bounded Telegram inbox sync")
    telegram_sync.add_argument("--live", action="store_true")
    telegram_sync.add_argument("--retry-dry-run-sent", action="store_true")
    send_pending = sub.add_parser(
        "telegram-send-pending-notifications",
        help="Internal/dev: send or dry-run queued Telegram notifications",
    )
    send_pending.add_argument("--live", action="store_true")
    send_pending.add_argument("--retry-dry-run-sent", action="store_true")
    founder_smoke = sub.add_parser("telegram-founder-smoke", help="Internal/dev: validate Telegram Founder Inbox")
    founder_smoke.add_argument("--dry-run", action="store_true")
    founder_smoke.add_argument("--live", action="store_true")

    sub.add_parser("list-approvals", help="List pending approval inbox items")
    show_approval = sub.add_parser("show-approval", help="Show one approval inbox item")
    show_approval.add_argument("approval_id")
    approve = sub.add_parser("approve", help="Approve a pending approval")
    approve.add_argument("approval_id")
    approve.add_argument("--decided-by", default="founder")
    deny = sub.add_parser("deny", help="Deny a pending approval")
    deny.add_argument("approval_id")
    deny.add_argument("--decided-by", default="founder")

    enqueue = sub.add_parser("enqueue-action", help=argparse.SUPPRESS)
    enqueue.add_argument("--task-id", required=True)
    enqueue.add_argument("--agent-id", required=True)
    enqueue.add_argument("--action", required=True)
    enqueue.add_argument("--payload-json", default="{}")
    enqueue.add_argument("--external-effect", action="store_true")
    enqueue.add_argument("--approval-id")

    sub.add_parser("list-execution-queue", help="List queued execution items")
    process = sub.add_parser("process-execution-queue", help="Process queued safe actions")
    process.add_argument("--dry-run", action="store_true")

    sub.add_parser("list-notifications", help="List outgoing notifications")
    send = sub.add_parser("send-notifications", help="Send or dry-run queued notifications")
    send.add_argument("--dry-run", action="store_true")
    report_send = sub.add_parser("send-daily-report", help="Queue or send the daily report")
    report_send.add_argument("--dry-run", action="store_true")
    report_send.add_argument("--live", action="store_true")

    auth_start = sub.add_parser("auth-start", help="Start safe provider auth metadata flow")
    auth_start.add_argument("provider")
    auth_start.add_argument("--dry-run", action="store_true")
    auth_start.add_argument("--telegram-dry-run", action="store_true")
    auth_start.add_argument("--requested-by", default="founder")
    auth_start.add_argument("--actor-type", default="control")

    auth_status = sub.add_parser("auth-status", help="Show safe provider auth status")
    auth_status.add_argument("provider", nargs="?")
    sub.add_parser("auth-list", help="List safe provider auth metadata")
    auth_revoke = sub.add_parser("auth-revoke", help="Revoke TSF provider auth metadata")
    auth_revoke.add_argument("provider")
    auth_revoke.add_argument("--requested-by", default="founder")
    sub.add_parser("provider-routes", help="List supported provider routes")
    route_status = sub.add_parser("provider-route-status", help="Show one provider route")
    route_status.add_argument("provider")
    redact = sub.add_parser("auth-redact-test", help="Redact a string using provider-auth rules")
    redact.add_argument("text")
    handoff = sub.add_parser("auth-telegram-message", help="Format a Telegram-safe auth handoff")
    handoff.add_argument("provider")
    handoff.add_argument("--dry-run", action="store_true")

    runtime_status = sub.add_parser("provider-runtime-status", help="Show provider-owned runtime status")
    runtime_status.add_argument("provider")
    runtime_plan = sub.add_parser("provider-runtime-plan", help="Plan a provider runtime invocation without executing")
    runtime_plan.add_argument("provider")
    runtime_plan.add_argument("--agent-id", required=True)
    runtime_plan.add_argument("--prompt", required=True)
    runtime_invoke = sub.add_parser("provider-runtime-invoke", help="Invoke or dry-run a provider runtime")
    runtime_invoke.add_argument("provider")
    runtime_invoke.add_argument("--agent-id", required=True)
    runtime_invoke.add_argument("--task-id")
    runtime_invoke.add_argument("--prompt", required=True)
    runtime_invoke.add_argument("--dry-run", action="store_true")
    sub.add_parser("provider-status", help="Show internal model provider status")
    agent_reasoning = sub.add_parser("run-agent-reasoning", help="Run bounded internal agent reasoning")
    agent_reasoning.add_argument("agent_id")
    agent_reasoning.add_argument("--dry-run", action="store_true")
    model_smoke = sub.add_parser("run-model-smoke", help="Run an internal model smoke check")
    model_smoke.add_argument("--dry-run", action="store_true")
    model_smoke.add_argument("--live", action="store_true")
    export = sub.add_parser("export-control-room-state", help="Export read-only public progress snapshot JSON")
    export.add_argument("--output")
    export.add_argument("--stdout", action="store_true")
    export.add_argument("--audience", choices=["public", "founder"], default="public")
    serve_api = sub.add_parser("serve-control-room-api", help="Serve the read-only public progress API")
    serve_api.add_argument("--host", default="127.0.0.1")
    serve_api.add_argument("--port", type=int, default=8787)
    serve_api.add_argument("--audience", choices=["public"], default="public")
    serve_api.add_argument("--reload", action="store_true")
    sub.add_parser("autonomous-status", help="Show autonomous workday status")
    start_auto = sub.add_parser("start-workday", help="Start the autonomous workday")
    start_auto.add_argument("--dry-run", action="store_true")
    cycle = sub.add_parser("run-workday-cycle", help="Run one bounded autonomous cycle")
    cycle.add_argument("--dry-run", action="store_true")
    turn = sub.add_parser("run-agent-turn", help="Run one bounded autonomous agent turn")
    turn.add_argument("agent_id")
    turn.add_argument("--dry-run", action="store_true")
    close_auto = sub.add_parser("close-workday", help="Close the active autonomous workday")
    close_auto.add_argument("--dry-run", action="store_true")
    report_auto = sub.add_parser("generate-atlas-report", help="Generate public and private manager reports")
    report_auto.add_argument("--public-only", action="store_true")
    agent_work = sub.add_parser("list-agent-work", help="List autonomous agent work")
    agent_work.add_argument("--agent-id")
    human_list = sub.add_parser("list-human-tasks", help="List founder human tasks")
    human_list.add_argument("--status")
    human_show = sub.add_parser("show-human-task", help="Show one founder human task")
    human_show.add_argument("human_task_id")
    sub.add_parser("scheduler-status", help="Internal/dev: show autonomous scheduler status")
    sub.add_parser("scheduler-checkpoint-once", help="Internal/dev: run one bounded scheduler checkpoint")
    scheduler_loop = sub.add_parser("scheduler-loop", help="Internal/dev: run a bounded local scheduler loop")
    scheduler_loop.add_argument("--max-runtime-seconds", type=int, required=True)
    scheduler_loop.add_argument("--max-checkpoints", type=int, required=True)
    scheduler_loop.add_argument("--sleep-seconds", type=int, default=60)
    sub.add_parser("scheduler-lock-status", help="Internal/dev: show scheduler lock status")
    sub.add_parser("scheduler-dry-run-plan", help="Internal/dev: show deterministic scheduler checkpoint plan")
    sub.add_parser("deploy-status", help="Internal/dev: show deployment operations status")
    deploy_plan = sub.add_parser("deploy-plan", help="Internal/dev: create a deployment plan")
    deploy_plan.add_argument("--target", required=True)
    deploy_plan.add_argument("--env", choices=["local", "preview", "staging", "production"], default="preview")
    deploy_checks = sub.add_parser("deploy-checks", help="Internal/dev: run deployment validation checks")
    deploy_checks.add_argument("--target", required=True)
    deploy_checks.add_argument("--heavy", action="store_true")
    deploy_preview = sub.add_parser("deploy-preview", help="Internal/dev: dry-run or execute preview deployment if policy allows")
    deploy_preview.add_argument("--target", required=True)
    deploy_preview.add_argument("--dry-run", action="store_true", default=True)
    deploy_production = sub.add_parser("deploy-production", help="Internal/dev: dry-run production deployment candidate")
    deploy_production.add_argument("--target", required=True)
    deploy_production.add_argument("--dry-run", action="store_true", default=True)
    sub.add_parser("render-status", help="Internal/dev: show Render adapter status")
    sub.add_parser("vercel-status", help="Internal/dev: show Vercel adapter status")
    history = sub.add_parser("deployment-history", help="Internal/dev: show deployment records")
    history.add_argument("--limit", type=int, default=20)
    sub.add_parser("deployment-credentials-status", help="Internal/dev: validate deployment credential setup safely")
    sub.add_parser("deployment-setup-status", help="Internal/dev: show deployment setup readiness safely")
    sub.add_parser("create-deployment-setup-human-tasks", help="Internal/dev: create missing deployment setup HumanTasks")
    sub.add_parser("validate-deploy-tools", help="Internal/dev: validate deployment CLIs safely")
    sub.add_parser("validate-vercel-setup", help="Internal/dev: validate Vercel setup safely")
    sub.add_parser("validate-render-setup", help="Internal/dev: validate Render setup safely")
    vercel_preview = sub.add_parser("vercel-preview", help="Internal/dev: preview-only Vercel deployment path")
    vercel_preview_mode = vercel_preview.add_mutually_exclusive_group()
    vercel_preview_mode.add_argument("--dry-run", action="store_true", default=True)
    vercel_preview_mode.add_argument("--live", action="store_true")
    vercel_health = sub.add_parser("vercel-health-check", help="Internal/dev: check a Vercel preview URL")
    vercel_health.add_argument("url")
    sub.add_parser("render-readiness", help="Internal/dev: validate Render deployment readiness")
    render_staging = sub.add_parser("render-deploy-staging", help="Internal/dev: dry-run or execute Render staging deployment")
    render_staging_mode = render_staging.add_mutually_exclusive_group()
    render_staging_mode.add_argument("--dry-run", action="store_true", default=True)
    render_staging_mode.add_argument("--live", action="store_true")
    sub.add_parser("deployment-human-tasks", help="Internal/dev: list deployment setup HumanTasks")
    sub.add_parser("deployment-notifications", help="Internal/dev: list deployment-related notifications")
    public_smoke = sub.add_parser("public-progress-e2e-smoke", help="Internal/dev: read-only public frontend/API smoke")
    public_smoke.add_argument("--frontend-url", required=True)
    public_smoke.add_argument("--api-url", required=True)
    sub.add_parser("db-status", help="Internal/dev: show redacted store backend status")
    db_migrate_parser = sub.add_parser("db-migrate", help="Internal/dev: dry-run or apply database migrations")
    db_migrate_mode = db_migrate_parser.add_mutually_exclusive_group()
    db_migrate_mode.add_argument("--dry-run", action="store_true", default=True)
    db_migrate_mode.add_argument("--apply", action="store_true")
    sub.add_parser("db-verify", help="Internal/dev: verify configured database schema readiness")
    sub.add_parser("db-smoke", help="Internal/dev: run safe database smoke checks")
    sub.add_parser("db-redaction-smoke", help="Internal/dev: verify database URL redaction")
    sub.add_parser("scheduler-render-readiness", help="Internal/dev: check Render scheduler readiness")
    scheduler_smoke = sub.add_parser("scheduler-checkpoint-smoke", help="Internal/dev: dry-run or apply one scheduler checkpoint smoke")
    scheduler_smoke_mode = scheduler_smoke.add_mutually_exclusive_group()
    scheduler_smoke_mode.add_argument("--dry-run", action="store_true", default=True)
    scheduler_smoke_mode.add_argument("--apply", action="store_true")
    render_api = sub.add_parser("render-api-readiness", help="Internal/dev: check Render public API readiness")
    render_api.add_argument("--api-url")
    public_api = sub.add_parser("public-api-smoke", help="Internal/dev: smoke-test public read-only API")
    public_api.add_argument("--api-url", required=True)
    return parser


def _add_approval_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--agent-id", required=True)
    parser.add_argument("--requested-action", required=True)
    parser.add_argument("--risk-level", default="medium")
    parser.add_argument("--external-effect", action="store_true")
    parser.add_argument("--request", required=True)
    parser.add_argument("--sentinel-review", dest="guardian_review")


def main(argv: list[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    if not raw_argv or raw_argv[0] in {"-h", "--help"}:
        build_orchestrator_parser().parse_args(raw_argv)
        return 0
    if raw_argv and raw_argv[0] in ORCHESTRATOR_COMMANDS:
        return _main_orchestrator(raw_argv)
    return _main_run_agent(raw_argv)


def _main_run_agent(raw_argv: list[str]) -> int:
    if "--" in raw_argv:
        split_at = raw_argv.index("--")
        parser_argv = raw_argv[:split_at]
        forwarded = raw_argv[split_at + 1 :]
    else:
        parser_argv = raw_argv
        forwarded = []

    args = build_parser().parse_args(parser_argv)
    registry = AgentRegistry.from_file(args.profiles)
    profile = registry.get(args.agent)
    policy = load_project_policy(args.policy)
    validate_agent_profile(profile, policy)
    route = resolve_model_route(profile)

    metadata = {
        "agent_id": profile.agent_id,
        "display_name": profile.display_name,
        "provider": route.provider,
        "model": route.model,
        "api_mode": route.api_mode,
        "api_key_env": route.api_key_env,
        "api_key_alias": route.api_key_alias,
        "api_key_available": route.api_key_available,
        "toolsets": list(profile.toolsets),
        "budget": {
            "daily_usd": profile.budget.daily_usd,
            "monthly_usd": profile.budget.monthly_usd,
            "max_turns": profile.budget.max_turns,
        },
        "approval_channel": profile.approval_channel,
    }
    if args.dry_run:
        print(json.dumps(metadata, indent=2, sort_keys=True))
        return 0

    append_budget_log(profile, route, event="agent_run_start")

    env = env_with_api_key_alias(route)
    env["TSF_AGENT_ID"] = profile.agent_id
    env["TSF_AGENT_NAME"] = profile.display_name
    if profile.budget.daily_usd is not None:
        env["TSF_BUDGET_DAILY_USD"] = str(profile.budget.daily_usd)
    if profile.budget.monthly_usd is not None:
        env["TSF_BUDGET_MONTHLY_USD"] = str(profile.budget.monthly_usd)

    upstream_cli = os.environ.get("TSF_UPSTREAM_CLI") or ("her" + "mes")
    command = [upstream_cli, *route.upstream_runtime_args()]
    if profile.toolsets:
        command.extend(["--toolsets", ",".join(_runtime_toolsets(profile.toolsets))])
    if profile.budget.max_turns is not None:
        env["TSF_MAX_TURNS"] = str(profile.budget.max_turns)
    command.extend(forwarded)

    return subprocess.call(command, env=env)


def _main_orchestrator(argv: list[str]) -> int:
    args = build_orchestrator_parser().parse_args(argv)
    if args.command == "init-store":
        store = init_store()
        _print_json({"summary": "The Synthetic Firm store is initialized.", **store.status()})
        store.close()
        return 0
    if args.command == "store-status":
        store = Store()
        _print_json({"summary": "The Synthetic Firm store is available.", **store.status()})
        store.close()
        return 0
    if args.command == "show-workday-status":
        config = load_workday_config(args.config)
        status = evaluate_workday(config)
        _print_json(
            {
                "inside_work_hours": status.inside_work_hours,
                "timezone": status.timezone,
                "now": status.now.isoformat(),
                "summary": status.plain_english(),
            }
        )
        return 0
    if args.command == "create-dry-run-task":
        task = create_task(
            title=args.title,
            objective=args.objective,
            created_by_agent_id=args.created_by,
            assigned_agent_id=args.assigned_agent,
            risk_level=args.risk_level,
            external_effect=args.external_effect,
            budget_limit=args.budget_limit,
            max_steps=args.max_steps,
        )
        _print_json(task_to_dict(task))
        return 0
    if args.command == "simulate-agent-message":
        message = create_message(
            sender_agent_id=args.sender,
            recipient_agent_id=args.recipient,
            channel=args.channel,
            task_id=args.task_id,
            message_type=args.message_type,
            content=args.content,
        )
        _print_json(message_to_dict(message))
        return 0
    if args.command == "create-approval-request":
        approval = _approval_from_args(args)
        _print_json(approval_to_dict(approval))
        return 0
    if args.command == "format-telegram-approval":
        approval = _approval_from_args(args)
        print(format_outgoing_approval(approval))
        return 0
    if args.command == "propose-worker":
        proposal = create_worker_proposal(
            proposed_by_agent_id=args.proposed_by,
            proposed_worker_name=args.name,
            proposed_role=args.role,
            business_reason=args.reason,
            requested_tools=args.tool,
            requested_budget=args.budget,
            risk_level=args.risk_level,
        )
        _print_json(proposal_to_dict(proposal))
        return 0
    if args.command == "propose-self-improvement":
        proposal = create_self_improvement_proposal(
            agent_id=args.agent_id,
            capability_gap=args.capability_gap,
            proposed_change=args.proposed_change,
            files_or_modules_affected=args.files,
            permission_change_requested=args.permission_change,
            budget_change_requested=args.budget_change,
            risk_level=args.risk_level,
        )
        _print_json(proposal_to_dict(proposal))
        return 0
    if args.command == "generate-daily-report":
        report = generate_daily_report(
            DailyReportInput(
                questions_for_founder=tuple(args.question),
                next_actions=tuple(args.next_action),
            )
        )
        store = Store()
        store.save_daily_report(
            report_date=date.today().isoformat(),
            content=report,
            telegram_summary=_telegram_safe_report(report),
        )
        store.close()
        print(report, end="")
        return 0
    if args.command == "show-budget-status":
        policy = BudgetPolicy(
            agent_daily_limit_usd=args.agent_limit,
            task_limit_usd=args.task_limit,
            company_daily_limit_usd=args.company_limit,
            max_loop_steps=args.max_loop_steps,
            max_tool_calls=args.max_tool_calls,
            dry_run=args.dry_run,
        )
        usage = BudgetUsage(
            agent_daily_spend_usd=args.agent_spend,
            task_spend_usd=args.task_spend,
            company_daily_spend_usd=args.company_spend,
            loop_steps=args.loop_steps,
            tool_calls=args.tool_calls,
        )
        decision = evaluate_budget(policy, usage)
        _print_json({"summary": budget_status_text(policy, usage), **asdict(decision)})
        return 0
    if args.command == "budget-add-cost":
        store = Store()
        item = add_cost_item(
            store,
            category=args.category,
            provider=args.provider,
            service_name=args.service,
            description=args.description,
            amount_eur=args.amount_eur,
            recurrence=args.recurrence,
            confidence=args.confidence,
            source=args.source,
            public_summary=args.public_summary,
        )
        _print_json({"summary": "Infrastructure cost item recorded.", "costItem": cost_item_to_dict(item)})
        store.close()
        return 0
    if args.command == "budget-list-costs":
        store = Store()
        _print_json({"costItems": [cost_item_to_dict(item) for item in list_cost_items(store, month=args.month, category=args.category)]})
        store.close()
        return 0
    if args.command == "budget-monthly-report":
        store = Store()
        _print_json(budget_private_report(store))
        store.close()
        return 0
    if args.command == "budget-check-action":
        store = Store()
        decision = check_budget_gate(
            store,
            args.action_name,
            new_recurring_cost=args.new_recurring_cost,
            unknown_cost_possible=args.unknown_cost_possible,
        )
        _print_json({"decision": decision.to_dict()})
        store.close()
        return 0 if decision.allowed else 1
    if args.command == "budget-create-confirmation-tasks":
        store = Store()
        task_ids = create_budget_confirmation_tasks(store)
        _print_json({"summary": f"Created {len(task_ids)} budget confirmation HumanTask(s).", "humanTaskIds": list(task_ids)})
        store.close()
        return 0
    if args.command == "budget-public-summary":
        store = Store()
        _print_json(budget_public_summary(store))
        store.close()
        return 0
    if args.command == "code-proposal-create":
        store = Store()
        patch_text = Path(args.patch_file).read_text(encoding="utf-8")
        proposal = create_code_change_proposal(
            store,
            title=args.title,
            summary=args.summary,
            rationale=args.rationale,
            patch_text=patch_text,
            created_by_agent_id=args.created_by,
            target_branch=args.target_branch,
            base_branch=args.base_branch,
            tests_command=args.tests_command,
            public_summary=args.public_summary,
        )
        _print_json({"summary": "Forge code-change proposal created.", "proposal": code_proposal_to_dict(proposal)})
        store.close()
        return 0
    if args.command == "code-proposal-list":
        store = Store()
        proposals = list_code_change_proposals(store, status=args.status, limit=args.limit)
        _print_json({"proposals": [code_proposal_to_dict(proposal) for proposal in proposals]})
        store.close()
        return 0
    if args.command == "code-proposal-review":
        store = Store()
        proposal = internally_review_code_change_proposal(store, args.proposal_id)
        _print_json({"summary": "Atlas and Sentinel approved code-change proposal internally.", "proposal": code_proposal_to_dict(proposal)})
        store.close()
        return 0
    if args.command == "code-proposal-apply":
        store = Store()
        result = apply_code_change_proposal(
            store,
            args.proposal_id,
            repo_path=args.repo_path,
            live=args.live,
            push=args.push,
            tests_command=args.tests_command,
        )
        _print_json(result)
        store.close()
        return 0
    if args.command == "code-proposal-public-summary":
        store = Store()
        _print_json(code_change_public_summary(store))
        store.close()
        return 0
    if args.command == "autonomous-ops-status":
        _print_json(autonomous_ops_status())
        return 0
    if args.command == "autonomous-ops-once":
        _print_json(run_autonomous_ops_once())
        return 0
    if args.command == "create-task":
        store = Store()
        task = store.create_task(
            title=args.title,
            objective=args.objective,
            created_by_agent_id=args.created_by,
            assigned_agent_id=args.assigned_agent,
            risk_level=args.risk_level,
            external_effect=args.external_effect,
            budget_limit=args.budget_limit,
            max_steps=args.max_steps,
            plain_english_summary=args.summary,
        )
        _print_json(task_to_dict(task))
        store.close()
        return 0
    if args.command == "list-tasks":
        store = Store()
        tasks = store.list_tasks()
        if args.status:
            tasks = [task for task in tasks if task.status == args.status]
        _print_json({"tasks": [task_to_dict(task) for task in tasks]})
        store.close()
        return 0
    if args.command == "send-agent-message":
        store = Store()
        message = store.create_message(
            sender_agent_id=args.sender,
            recipient_agent_id=args.recipient,
            channel=args.channel,
            task_id=args.task_id,
            message_type=args.message_type,
            content=args.content,
        )
        _print_json(message_to_dict(message))
        store.close()
        return 0
    if args.command == "list-messages":
        store = Store()
        messages = store.list_messages(task_id=args.task_id, channel=args.channel)
        _print_json({"messages": [message_to_dict(message) for message in messages]})
        store.close()
        return 0
    if args.command == "create-approval":
        store = Store()
        approval = store.create_approval(
            task_id=args.task_id,
            agent_id=args.agent_id,
            requested_action=args.requested_action,
            risk_level=args.risk_level,
            external_effect=args.external_effect,
            plain_english_request=args.request,
            guardian_review=args.guardian_review,
        )
        _print_json(approval_to_dict(approval))
        store.close()
        return 0
    if args.command == "decide-approval":
        store = Store()
        approval = store.get_approval(args.approval_id)
        decision = sign_approval_decision(
            approval_id=approval.approval_id,
            task_id=approval.task_id,
            requested_action=approval.requested_action,
            decision=args.decision,
            decided_by=args.decided_by,
            expires_at=default_expiry(),
            dry_run=args.dry_run,
        )
        store.persist_approval_decision(decision)
        _print_json(
            {
                "approval_id": approval.approval_id,
                "decision": decision.payload["decision"],
                "dry_run": decision.dry_run,
                "executable": decision.executable and not decision.dry_run,
                "summary": "Approval decision recorded.",
            }
        )
        store.close()
        return 0
    if args.command == "verify-approval":
        store = Store()
        approval = store.get_approval(args.approval_id)
        decision = store.latest_approval_decision(args.approval_id)
        verified = False
        if decision:
            verified = verify_signed_decision(decision, requested_action=approval.requested_action)
        _print_json({"approval_id": args.approval_id, "verified": verified})
        store.close()
        return 0 if verified else 1
    if args.command == "parse-telegram-command":
        command = parse_telegram_command(args.text)
        _print_json(asdict(command))
        return 0
    if args.command == "handle-telegram-command-dry-run":
        print(handle_telegram_command_dry_run(args.text))
        return 0
    if args.command == "audit-log":
        store = Store()
        rows = store.connection.execute("SELECT * FROM audit_log ORDER BY sequence_number").fetchall()
        _print_json({"entries": [dict(row) for row in rows]})
        store.close()
        return 0
    if args.command == "verify-audit-log":
        store = Store()
        ok, summary = store.verify_audit()
        _print_json({"verified": ok, "summary": summary})
        store.close()
        return 0 if ok else 1
    if args.command in {"pause", "resume", "kill"}:
        store = Store()
        target = {"pause": "paused", "resume": "active", "kill": "killed"}[args.command]
        store.set_runtime_status(target)
        _print_json({"runtime_status": store.runtime_status(), "summary": f"Runtime is {target}."})
        store.close()
        return 0
    if args.command == "runtime-status":
        store = Store()
        _print_json({"runtime_status": store.runtime_status(), "summary": "Runtime status read."})
        store.close()
        return 0
    if args.command == "list-daily-reports":
        store = Store()
        reports = store.list_daily_reports()[: args.limit]
        _print_json({"reports": reports})
        store.close()
        return 0
    if args.command == "budget-status":
        store = Store()
        totals = store.budget_totals(agent_id=args.agent_id, task_id=args.task_id)
        _print_json(
            {
                "summary": "Persisted budget totals loaded.",
                "runtimeBudget": totals,
                "infrastructureBudget": monthly_budget_state(store).to_dict(),
            }
        )
        store.close()
        return 0
    if args.command in {"telegram-status", "telegram-founder-status"}:
        _print_json(telegram_status())
        return 0
    if args.command == "telegram-dry-run-command":
        store = Store()
        config = load_telegram_config()
        chat_id = args.chat_id
        if not config.allowed_chat_ids:
            config = config.__class__(
                enabled=False,
                bot_token=None,
                allowed_chat_ids=frozenset({chat_id}),
                mode="dry_run",
            )
        if str(args.text).strip().startswith("/"):
            response = handle_control_command(store, parse_telegram_command(args.text), chat_id=chat_id, config=config)
        else:
            response = handle_founder_telegram_text(store, args.text, chat_id=chat_id, config=config)
        print(response)
        store.close()
        return 0
    if args.command == "telegram-poll-once":
        store = Store()
        print(poll_once(store))
        store.close()
        return 0
    if args.command == "telegram-founder-sync-once":
        store = Store()
        _print_json(
            telegram_founder_sync_once(
                store,
                live=args.live,
                retry_dry_run_sent=args.retry_dry_run_sent,
            )
        )
        store.close()
        return 0
    if args.command == "telegram-send-pending-notifications":
        store = Store()
        _print_json(send_pending_notifications(store, live=args.live, retry_dry_run_sent=args.retry_dry_run_sent))
        store.close()
        return 0
    if args.command == "telegram-founder-smoke":
        if args.live and args.dry_run:
            raise SystemExit("--live and --dry-run are mutually exclusive")
        _print_json(telegram_founder_smoke(live=args.live))
        return 0
    if args.command == "list-approvals":
        store = Store()
        approvals = [approval_to_inbox_dict(item) for item in list_pending_approvals(store)]
        _print_json({"approvals": approvals})
        store.close()
        return 0
    if args.command == "show-approval":
        store = Store()
        print(format_approval_detail(store.get_approval(args.approval_id)))
        store.close()
        return 0
    if args.command in {"approve", "deny"}:
        store = Store()
        signed = decide_pending_approval(
            store,
            args.approval_id,
            decision="approved" if args.command == "approve" else "denied",
            decided_by=args.decided_by,
            live=True,
        )
        _print_json(
            {
                "approval_id": args.approval_id,
                "decision": signed.payload["decision"],
                "dry_run": signed.dry_run,
                "summary": "Approval decision recorded.",
            }
        )
        store.close()
        return 0
    if args.command == "enqueue-action":
        store = Store()
        item = enqueue_action(
            store,
            task_id=args.task_id,
            agent_id=args.agent_id,
            action=args.action,
            payload=json.loads(args.payload_json),
            external_effect=args.external_effect,
            approval_id=args.approval_id,
        )
        _print_json(queue_item_to_dict(item))
        store.close()
        return 0
    if args.command == "list-execution-queue":
        store = Store()
        _print_json({"queue": [queue_item_to_dict(item) for item in list_queue(store)]})
        store.close()
        return 0
    if args.command == "process-execution-queue":
        store = Store()
        items = process_execution_queue(store, dry_run=args.dry_run)
        _print_json({"queue": [queue_item_to_dict(item) for item in items]})
        store.close()
        return 0
    if args.command == "list-notifications":
        store = Store()
        _print_json({"notifications": [notification_to_dict(item) for item in list_notifications(store)]})
        store.close()
        return 0
    if args.command == "send-notifications":
        store = Store()
        sent = send_notifications(store, dry_run=args.dry_run)
        _print_json({"notifications": [notification_to_dict(item) for item in sent]})
        store.close()
        return 0
    if args.command == "send-daily-report":
        store = Store()
        reports = store.list_daily_reports()
        if reports:
            body = str(reports[0]["telegram_summary"])
        else:
            report = generate_daily_report(DailyReportInput())
            body = _telegram_safe_report(report)
            store.save_daily_report(report_date=date.today().isoformat(), content=report, telegram_summary=body)
        notification = enqueue_notification(store, notification_type="daily_report", body=body, dry_run=not args.live)
        sent = send_notifications(store, dry_run=args.dry_run or not args.live)
        _print_json(
            {
                "notification_id": notification.notification_id,
                "sent": [notification_to_dict(item) for item in sent],
                "summary": "Daily report notification processed.",
            }
        )
        store.close()
        return 0
    if args.command == "auth-start":
        validate_provider_auth_actor(actor_type=args.actor_type, live=not args.dry_run)
        store = Store()
        session = start_provider_auth(args.provider, requested_by=args.requested_by, dry_run=args.dry_run)
        save_auth_session(store, session)
        if args.telegram_dry_run:
            print(format_auth_handoff(session))
        else:
            _print_json(session_to_dict(session))
        store.close()
        return 0
    if args.command == "auth-status":
        store = Store()
        if args.provider:
            session = provider_auth_status(args.provider, requested_by="system")
            save_auth_session(store, session)
            print(format_auth_status(session))
        else:
            sessions = []
            for provider in provider_routes():
                session = provider_auth_status(provider, requested_by="system")
                save_auth_session(store, session)
                sessions.append(session_to_dict(session))
            _print_json({"sessions": sessions})
        store.close()
        return 0
    if args.command == "auth-list":
        store = Store()
        _print_json({"sessions": [session_to_dict(item) for item in list_auth_sessions(store)]})
        store.close()
        return 0
    if args.command == "auth-revoke":
        store = Store()
        session = revoke_auth_metadata(store, args.provider, requested_by=args.requested_by)
        _print_json(session_to_dict(session))
        store.close()
        return 0
    if args.command == "provider-routes":
        _print_json({"routes": [route_to_dict(route) for route in provider_routes().values()]})
        return 0
    if args.command == "provider-route-status":
        _print_json(route_to_dict(get_provider_route(args.provider)))
        return 0
    if args.command == "auth-redact-test":
        print(redact_auth_text(args.text))
        return 0
    if args.command == "auth-telegram-message":
        session = start_provider_auth(args.provider, requested_by="founder", dry_run=args.dry_run)
        print(format_auth_handoff(session))
        return 0
    if args.command == "provider-runtime-status":
        _print_json(provider_runtime_status(args.provider))
        return 0
    if args.command == "provider-runtime-plan":
        invocation = build_runtime_invocation(
            provider=args.provider,
            agent_id=args.agent_id,
            prompt=args.prompt,
            dry_run=True,
        )
        _print_json(invocation_to_dict(invocation))
        return 0
    if args.command == "provider-runtime-invoke":
        store = Store()
        result = invoke_provider_runtime(
            store,
            provider=args.provider,
            agent_id=args.agent_id,
            prompt=args.prompt,
            task_id=args.task_id,
            dry_run=args.dry_run,
        )
        _print_json(result_to_dict(result))
        store.close()
        return 0
    if args.command == "provider-status":
        _print_json(model_provider_status())
        return 0
    if args.command == "run-agent-reasoning":
        if args.dry_run:
            os.environ["TSF_MODEL_DRY_RUN"] = "true"
        store = Store()
        workday = get_current_workday(store)
        request = build_agent_reasoning_request(
            store,
            agent_id=args.agent_id,
            workday_id=workday.workday_id if workday else None,
        )
        response = complete_agent_reasoning(request, store=store)
        _print_json(response_to_dict(response))
        store.close()
        return 0
    if args.command == "run-model-smoke":
        if args.live and os.environ.get("TSF_MODEL_LIVE_SMOKE_ENABLED", "false").lower() != "true":
            raise SystemExit("Live model smoke requires TSF_MODEL_LIVE_SMOKE_ENABLED=true")
        if args.dry_run or not args.live:
            os.environ["TSF_MODEL_DRY_RUN"] = "true"
        store = Store()
        request = build_agent_reasoning_request(store, agent_id="atlas")
        response = complete_agent_reasoning(request, store=store)
        _print_json(response_to_dict(response))
        store.close()
        return 0
    if args.command == "export-control-room-state":
        if not args.stdout and not args.output:
            raise SystemExit("export-control-room-state requires --stdout or --output")
        payload = export_control_room_state(output=args.output, stdout=True, audience=args.audience)
        if args.stdout:
            print(payload, end="")
        else:
            _print_json({"summary": "Public progress snapshot exported.", "output": args.output})
        return 0
    if args.command == "serve-control-room-api":
        serve_control_room_api(host=args.host, port=args.port, audience=args.audience, reload=args.reload)
        return 0
    if args.command == "autonomous-status":
        _print_json(autonomous_status())
        return 0
    if args.command == "start-workday":
        store = Store()
        workday = start_workday(store, dry_run=args.dry_run)
        plan = get_latest_plan(store, workday.workday_id) if not args.dry_run else None
        _print_json(
            {
                "summary": workday.summary,
                "workday": workday_to_dict(workday),
                "daily_plan": plan_to_dict(plan) if plan else None,
            }
        )
        store.close()
        return 0
    if args.command == "run-workday-cycle":
        store = Store()
        result = run_cycle(store, dry_run=args.dry_run)
        _print_json(result)
        store.close()
        return 0
    if args.command == "run-agent-turn":
        store = Store()
        result = run_agent_turn(store, agent_id=args.agent_id, dry_run=args.dry_run)
        _print_json(result)
        store.close()
        return 0
    if args.command == "close-workday":
        store = Store()
        workday = close_workday(store, dry_run=args.dry_run)
        _print_json({"summary": workday.summary, "workday": workday_to_dict(workday)})
        store.close()
        return 0
    if args.command == "generate-atlas-report":
        store = Store()
        workday = get_current_workday(store) or start_workday(store)
        public_report_id = generate_public_daily_report(store, workday.workday_id)
        private_report_id = None if args.public_only else generate_private_founder_report(store, workday.workday_id)
        _print_json(
            {
                "summary": "Atlas reports generated from persisted TSF state.",
                "public_report_id": public_report_id,
                "private_report_id": private_report_id,
            }
        )
        store.close()
        return 0
    if args.command == "list-agent-work":
        store = Store()
        _print_json(list_agent_work(store, args.agent_id))
        store.close()
        return 0
    if args.command == "list-human-tasks":
        store = Store()
        tasks = store.list_human_tasks(status=args.status)
        _print_json({"human_tasks": [human_task_to_dict(task, audience="founder") for task in tasks]})
        store.close()
        return 0
    if args.command == "show-human-task":
        store = Store()
        print(format_human_task_for_telegram(store.get_human_task(args.human_task_id)))
        store.close()
        return 0
    if args.command == "scheduler-status":
        _print_json(scheduler_status())
        return 0
    if args.command == "scheduler-checkpoint-once":
        _print_json(run_checkpoint_once())
        return 0
    if args.command == "scheduler-loop":
        _print_json(
            run_scheduler_loop(
                max_runtime_seconds=args.max_runtime_seconds,
                max_checkpoints=args.max_checkpoints,
                sleep_seconds=args.sleep_seconds,
            )
        )
        return 0
    if args.command == "scheduler-lock-status":
        _print_json(scheduler_lock_status())
        return 0
    if args.command == "scheduler-dry-run-plan":
        _print_json(scheduler_dry_run_plan())
        return 0
    if args.command == "deploy-status":
        store = Store()
        _print_json(
            {
                "summary": "Deployment operations status loaded.",
                "vercel": vercel_status(),
                "render": render_status(),
                "history": [deployment_record_to_dict(item, public=True) for item in list_deployment_records(store, limit=5)],
            }
        )
        store.close()
        return 0
    if args.command == "vercel-status":
        _print_json(vercel_status())
        return 0
    if args.command == "render-status":
        _print_json(render_status())
        return 0
    if args.command == "deploy-plan":
        store = Store()
        plan = _deployment_plan_from_args(args.target, args.env)
        record = save_deployment_record(store, plan=plan, state=plan.state)
        _print_json({"plan": deployment_plan_to_dict(plan), "deployment": deployment_record_to_dict(record, public=True)})
        store.close()
        return 0
    if args.command == "deploy-checks":
        store = Store()
        checks = run_deployment_checks(store, target=args.target, run_heavy=args.heavy)
        _print_json(check_summary(checks))
        store.close()
        return 0
    if args.command == "deploy-preview":
        store = Store()
        if args.target == "vercel_frontend":
            result = deploy_vercel_preview(store, dry_run=args.dry_run)
        elif args.target in {"render_backend_api", "render_scheduler_worker"}:
            result = deploy_render_service(store, target=args.target, environment="preview", dry_run=args.dry_run)
        else:
            raise SystemExit(f"Unsupported preview deployment target: {args.target}")
        _print_json(result)
        store.close()
        return 0
    if args.command == "deploy-production":
        store = Store()
        plan = _deployment_plan_from_args(args.target, "production")
        checks = run_deployment_checks(store, target=args.target, run_heavy=False)
        sentinel = sentinel_review_deployment_plan(plan, checks)
        decision = evaluate_deployment_policy(store, plan, checks)
        record = save_deployment_record(store, plan=plan, checks=checks, state=decision.state)
        _print_json(
            {
                "dry_run": args.dry_run,
                "executed": False,
                "deployment": deployment_record_to_dict(record, public=True),
                "policy": decision.__dict__,
                "sentinel": sentinel.__dict__,
                "summary": "Production deployment candidate evaluated; no production deploy executed.",
            }
        )
        store.close()
        return 0
    if args.command == "deployment-history":
        store = Store()
        records = [deployment_record_to_dict(item) for item in list_deployment_records(store, limit=args.limit)]
        _print_json({"deployments": records})
        store.close()
        return 0
    if args.command in {"deployment-credentials-status", "deployment-setup-status", "create-deployment-setup-human-tasks"}:
        store = Store()
        vercel = vercel_credential_status(store=store)
        render = render_credential_status(store=store)
        if args.command == "create-deployment-setup-human-tasks":
            _create_deployment_advisory_human_tasks(store)
        _print_json(
            {
                "summary": "Deployment credential status checked safely.",
                "vercel": credential_status_to_dict(vercel),
                "render": credential_status_to_dict(render),
            }
        )
        store.close()
        return 0
    if args.command == "validate-vercel-setup":
        store = Store()
        status = vercel_credential_status(store=store)
        _print_json({"summary": status.safe_summary, "vercel": credential_status_to_dict(status)})
        store.close()
        return 0
    if args.command == "validate-render-setup":
        store = Store()
        status = render_credential_status(store=store)
        _print_json({"summary": status.safe_summary, "render": credential_status_to_dict(status)})
        store.close()
        return 0
    if args.command == "validate-deploy-tools":
        store = Store()
        vercel = vercel_credential_status(store=store)
        render = render_credential_status(store=store)
        _print_json(
            {
                "summary": "Deployment tool validation completed.",
                "vercelCliAvailable": vercel.cli_available,
                "renderCliAvailable": render.cli_available,
                "missingRequirements": list(vercel.missing_requirements + render.missing_requirements),
            }
        )
        store.close()
        return 0
    if args.command == "vercel-preview":
        store = Store()
        result = deploy_vercel_preview(store, dry_run=not args.live)
        _print_json(result)
        store.close()
        return 0
    if args.command == "vercel-health-check":
        result = run_vercel_preview_health_check(args.url)
        _print_json({"health": result.__dict__})
        return 0 if result.passed else 1
    if args.command == "render-readiness":
        store = Store()
        _print_json(render_readiness(store))
        store.close()
        return 0
    if args.command == "render-deploy-staging":
        store = Store()
        result = deploy_render_service(store, target="render_backend_api", environment="staging", dry_run=not args.live)
        _print_json(result)
        store.close()
        return 0
    if args.command == "deployment-human-tasks":
        store = Store()
        tasks = [
            human_task_to_dict(task)
            for task in store.list_human_tasks(status="pending")
            if "deployment" in f"{task.title} {task.public_summary}".lower()
            or "Vercel" in task.title
            or "Render" in task.title
        ]
        _print_json({"humanTasks": tasks})
        store.close()
        return 0
    if args.command == "deployment-notifications":
        store = Store()
        notifications = [
            notification_to_dict(notification)
            for notification in list_notifications(store)
            if "deployment" in notification.body.lower()
            or "Vercel" in notification.body
            or "Render" in notification.body
        ]
        _print_json({"notifications": notifications})
        store.close()
        return 0
    if args.command == "public-progress-e2e-smoke":
        result = run_public_progress_e2e_smoke(frontend_url=args.frontend_url, api_url=args.api_url)
        _print_json(result.to_dict())
        return 0 if result.passed else 1
    if args.command == "db-status":
        _print_json(db_status())
        return 0
    if args.command == "db-migrate":
        _print_json(db_migrate(apply=args.apply))
        return 0
    if args.command == "db-verify":
        result = db_verify()
        _print_json(result)
        return 0 if result.get("verified", False) else 1
    if args.command == "db-smoke":
        result = db_smoke()
        _print_json(result)
        return 0 if result.get("smokePassed", False) else 1
    if args.command == "db-redaction-smoke":
        result = db_redaction_smoke()
        _print_json(result)
        return 0 if result.get("passed", False) else 1
    if args.command == "scheduler-render-readiness":
        result = scheduler_render_readiness()
        _print_json(result)
        return 0
    if args.command == "scheduler-checkpoint-smoke":
        result = scheduler_checkpoint_smoke(apply=args.apply)
        _print_json(result)
        return 0
    if args.command == "render-api-readiness":
        result = render_api_readiness(api_url=args.api_url)
        _print_json(result)
        return 0
    if args.command == "public-api-smoke":
        result = public_api_smoke(api_url=args.api_url)
        _print_json(result)
        return 0 if result.get("passed", False) else 1
    raise AssertionError(f"Unhandled command: {args.command}")


def _approval_from_args(args: argparse.Namespace):
    return create_approval_request(
        task_id=args.task_id,
        agent_id=args.agent_id,
        requested_action=args.requested_action,
        risk_level=args.risk_level,
        external_effect=args.external_effect,
        plain_english_request=args.request,
        guardian_review=args.guardian_review,
    )


def _print_json(payload: dict) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def _deployment_plan_from_args(target: str, environment: str):
    if target == "vercel_frontend":
        return create_vercel_deployment_plan(environment=environment)
    if target in {"render_backend_api", "render_scheduler_worker", "render_postgres_future"}:
        return create_render_deployment_plan(target=target, environment=environment)
    raise SystemExit(f"Unsupported deployment target: {target}")


def _create_deployment_advisory_human_tasks(store: Store) -> None:
    existing_titles = {task.title for task in store.list_human_tasks(status="pending")}
    advisories = [
        (
            "Confirm Vercel preview policy",
            "Confirm preview deployment is allowed for the public Progress Window.",
            "Forge needs explicit founder confirmation before live preview deployment can be enabled.",
            "Frontend deployment setup is pending.",
            "Related deployment target: vercel_frontend. Expected unblock condition: preview-only deployment policy can be enabled safely.",
        ),
        (
            "Confirm Vercel production remains blocked",
            "Confirm production deployment remains blocked.",
            "Production release authority is intentionally outside this phase.",
            "Frontend production deployment remains blocked.",
            "Related deployment target: vercel_frontend. Expected unblock condition: no production deployment flag is enabled.",
        ),
        (
            "Confirm Render deploy mode",
            "Confirm whether Render backend deploys should use a Git-connected service or Docker image.",
            "Forge needs the deployment model before backend readiness can move beyond planning.",
            "Backend deployment setup is pending.",
            "Related deployment target: render_backend_api. Expected unblock condition: Render deployment mode is documented.",
        ),
        (
            "Confirm Render production remains blocked",
            "Confirm no production backend deployment should run in this phase.",
            "Production backend deployment remains intentionally unavailable.",
            "Backend production deployment remains blocked.",
            "Related deployment target: render_backend_api. Expected unblock condition: production deploy policy remains disabled.",
        ),
    ]
    for title, request, reason, public_summary, private_details in advisories:
        if title in existing_titles:
            continue
        store.create_human_task(
            requested_by_agent_id="forge",
            title=title,
            plain_english_request=request,
            reason=reason,
            priority="medium",
            risk_level="medium",
            public_summary=public_summary,
            private_details=private_details,
        )


def _telegram_safe_report(report: str) -> str:
    lines = [line.strip() for line in report.splitlines() if line.strip()]
    return "\n".join(lines[:12])


def _runtime_toolsets(toolsets: tuple[str, ...]) -> list[str]:
    return [("her" + "mes-cli") if item == "tsf-core" else item for item in toolsets]


if __name__ == "__main__":
    raise SystemExit(main())
