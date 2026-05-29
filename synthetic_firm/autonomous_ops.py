"""Bounded autonomous code/deploy operations for TSF agents."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from synthetic_firm.code_change import CodeChangeError, apply_code_change_proposal, list_code_change_proposals
from synthetic_firm.provider_auth_redaction import redact_auth_text
from synthetic_firm.render_adapter import deploy_render_service
from synthetic_firm.store import Store
from synthetic_firm.vercel_adapter import deploy_vercel_preview


DEFAULT_MAX_PROPOSALS = 1


@dataclass(frozen=True)
class AutonomousOpsPolicy:
    enabled: bool
    code_apply_enabled: bool
    code_push_enabled: bool
    preview_deploy_enabled: bool
    render_staging_deploy_enabled: bool
    repo_configured: bool
    tests_configured: bool
    max_proposals: int
    summary: str


def autonomous_ops_status(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Return a secret-free status summary for autonomous code/deploy ops."""

    policy = load_autonomous_ops_policy(env)
    return {
        "enabled": policy.enabled,
        "codeApplyEnabled": policy.code_apply_enabled,
        "codePushEnabled": policy.code_push_enabled,
        "previewDeployEnabled": policy.preview_deploy_enabled,
        "renderStagingDeployEnabled": policy.render_staging_deploy_enabled,
        "repoConfigured": policy.repo_configured,
        "testsConfigured": policy.tests_configured,
        "maxProposals": policy.max_proposals,
        "summary": policy.summary,
    }


def autonomous_ops_public_summary(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Return a public-safe summary for the read-only progress window."""

    policy = load_autonomous_ops_policy(env)
    return {
        "enabled": policy.enabled,
        "codeApplyEnabled": policy.code_apply_enabled,
        "codePushEnabled": policy.code_push_enabled,
        "previewDeployEnabled": policy.preview_deploy_enabled,
        "renderStagingDeployEnabled": policy.render_staging_deploy_enabled,
        "summary": policy.summary,
    }


def run_autonomous_ops_once(store: Store | None = None, *, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Run one bounded autonomous operations pass and exit.

    This is intentionally narrow: no arbitrary shell, no production deploys,
    no secret-bearing output, and no patch execution without internal approval.
    """

    own_store = store is None
    store = store or Store()
    env_map = env if env is not None else os.environ
    policy = load_autonomous_ops_policy(env_map)
    try:
        store.append_audit(
            actor_type="orchestrator",
            actor_id="autonomous_ops",
            action="autonomous_ops_policy",
            target_type="runtime_policy",
            target_id="autonomous_ops",
            risk_level="low" if policy.enabled else "medium",
            summary=policy.summary,
            metadata={
                "enabled": policy.enabled,
                "code_apply_enabled": policy.code_apply_enabled,
                "code_push_enabled": policy.code_push_enabled,
                "preview_deploy_enabled": policy.preview_deploy_enabled,
                "render_staging_deploy_enabled": policy.render_staging_deploy_enabled,
            },
        )
        if not policy.enabled:
            return {"status": "skipped", "summary": policy.summary, "policy": autonomous_ops_status(env_map)}
        if not policy.code_apply_enabled:
            return {
                "status": "skipped",
                "summary": "Autonomous operations are enabled, but code apply is disabled.",
                "policy": autonomous_ops_status(env_map),
            }

        code_results = _run_approved_code_proposals(store, env_map, policy)
        deploy_results = _run_deploys_after_code(store, env_map, policy, code_results)
        status = "completed"
        if any(result.get("status") == "failed" for result in code_results + deploy_results):
            status = "failed"
        elif not code_results:
            status = "skipped"
        return {
            "status": status,
            "summary": _ops_summary(code_results, deploy_results),
            "policy": autonomous_ops_status(env_map),
            "codeResults": code_results,
            "deployResults": deploy_results,
        }
    finally:
        if own_store:
            store.close()


def load_autonomous_ops_policy(env: Mapping[str, str] | None = None) -> AutonomousOpsPolicy:
    env_map = env if env is not None else os.environ
    enabled = _bool(env_map.get("TSF_AUTONOMOUS_OPS_ENABLED"), default=False)
    code_apply = _bool(env_map.get("TSF_AUTONOMOUS_CODE_APPLY_ENABLED"), default=False)
    code_push = _bool(env_map.get("TSF_AUTONOMOUS_CODE_PUSH_ENABLED"), default=False)
    preview_deploy = _bool(env_map.get("TSF_AUTONOMOUS_PREVIEW_DEPLOY_ENABLED"), default=False)
    render_staging = _bool(env_map.get("TSF_AUTONOMOUS_RENDER_DEPLOY_ENABLED"), default=False)
    repo_path = env_map.get("TSF_CODE_REPO_PATH", ".").strip()
    repo_configured = bool(repo_path)
    tests_configured = bool(env_map.get("TSF_CODE_TEST_COMMAND", "").strip())
    max_proposals = _int(env_map.get("TSF_AUTONOMOUS_CODE_MAX_PROPOSALS"), default=DEFAULT_MAX_PROPOSALS)
    if max_proposals < 1:
        max_proposals = DEFAULT_MAX_PROPOSALS
    if not enabled:
        summary = "Autonomous code/deploy operations are disabled by default."
    elif not code_apply:
        summary = "Autonomous operations are enabled, but code apply is disabled."
    elif not repo_configured:
        summary = "Autonomous code apply is blocked until a repository path is configured."
    else:
        summary = "Autonomous code/deploy operations are enabled with bounded policy gates."
    return AutonomousOpsPolicy(
        enabled=enabled,
        code_apply_enabled=code_apply,
        code_push_enabled=code_push,
        preview_deploy_enabled=preview_deploy,
        render_staging_deploy_enabled=render_staging,
        repo_configured=repo_configured,
        tests_configured=tests_configured,
        max_proposals=max_proposals,
        summary=summary,
    )


def _run_approved_code_proposals(
    store: Store,
    env: Mapping[str, str],
    policy: AutonomousOpsPolicy,
) -> list[dict[str, Any]]:
    proposals = list_code_change_proposals(store, status="approved", limit=policy.max_proposals)
    repo_path = Path(env.get("TSF_CODE_REPO_PATH", ".")).resolve()
    tests_command = env.get("TSF_CODE_TEST_COMMAND", "").strip() or None
    results: list[dict[str, Any]] = []
    for proposal in reversed(proposals):
        try:
            applied = apply_code_change_proposal(
                store,
                proposal.proposal_id,
                repo_path=repo_path,
                live=True,
                push=policy.code_push_enabled,
                tests_command=tests_command,
            )
            result = {
                "status": "completed",
                "proposalId": applied["proposalId"],
                "targetBranch": applied["targetBranch"],
                "commitSha": str(applied.get("commitSha", ""))[:12] or None,
                "pushed": bool(applied.get("push")),
                "summary": applied["summary"],
            }
            store.append_audit(
                actor_type="coding_adapter",
                actor_id="autonomous_ops",
                action="autonomous_code_apply",
                target_type="code_change_proposal",
                target_id=proposal.proposal_id,
                risk_level="medium",
                summary=result["summary"],
                metadata={"pushed": result["pushed"], "target_branch": result["targetBranch"]},
            )
        except CodeChangeError as exc:
            summary = redact_auth_text(str(exc))
            _create_ops_blocker_task(store, summary)
            store.append_audit(
                actor_type="coding_adapter",
                actor_id="autonomous_ops",
                action="autonomous_code_apply_blocked",
                target_type="code_change_proposal",
                target_id=proposal.proposal_id,
                risk_level="medium",
                summary=summary,
            )
            result = {"status": "failed", "proposalId": proposal.proposal_id, "summary": summary}
        results.append(result)
    return results


def _run_deploys_after_code(
    store: Store,
    env: Mapping[str, str],
    policy: AutonomousOpsPolicy,
    code_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not any(result.get("status") == "completed" for result in code_results):
        return []
    results: list[dict[str, Any]] = []
    if policy.preview_deploy_enabled:
        results.append(_safe_deploy("vercel_preview", lambda: deploy_vercel_preview(store, dry_run=False, env=env)))
    if policy.render_staging_deploy_enabled:
        results.append(
            _safe_deploy(
                "render_staging",
                lambda: deploy_render_service(store, target="render_backend_api", environment="staging", dry_run=False, env=env),
            )
        )
    return results


def _safe_deploy(name: str, deploy: Any) -> dict[str, Any]:
    try:
        result = deploy()
        return {
            "status": "completed" if result.get("executed") else "skipped",
            "deployment": result.get("deployment"),
            "summary": str(result.get("summary") or f"{name} evaluated."),
            "executed": bool(result.get("executed")),
        }
    except Exception as exc:  # pragma: no cover - external adapters fail closed.
        return {"status": "failed", "summary": redact_auth_text(str(exc)), "executed": False}


def _create_ops_blocker_task(store: Store, reason: str) -> None:
    title = "Autonomous code operations blocked"
    if any(task.title == title for task in store.list_human_tasks(status="pending")):
        return
    store.create_human_task(
        requested_by_agent_id="forge",
        title=title,
        plain_english_request="Review the autonomous code operations blocker and restore the safe patch pipeline.",
        reason=reason,
        priority="high",
        risk_level="medium",
        public_summary="Autonomous code operations need founder attention.",
        private_details="Expected unblock condition: repo state, tests, or deployment credentials are safe to use again.",
    )


def _ops_summary(code_results: list[dict[str, Any]], deploy_results: list[dict[str, Any]]) -> str:
    if not code_results:
        return "No approved code-change proposals were ready for autonomous operations."
    completed = sum(1 for result in code_results if result.get("status") == "completed")
    failed = sum(1 for result in code_results if result.get("status") == "failed")
    deploys = sum(1 for result in deploy_results if result.get("executed"))
    return f"Autonomous operations applied {completed} code proposal(s), failed {failed}, and executed {deploys} deploy action(s)."


def _bool(value: str | None, *, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int(value: str | None, *, default: int) -> int:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default
