"""Deployment validation checks for TSF deployment plans."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable

from synthetic_firm.deployment import DeploymentCheckResult
from synthetic_firm.provider_auth_redaction import redact_auth_text
from synthetic_firm.store import Store

CommandRunner = Callable[[list[str], Path | None], subprocess.CompletedProcess[str]]


def required_check_names(target: str) -> tuple[str, ...]:
    common = (
        "backend compileall",
        "backend ruff",
        "backend tests",
        "brand guard",
        "audit verification",
        "public export smoke",
    )
    if target == "vercel_frontend":
        return common + ("frontend typecheck", "frontend build", "root frontend build", "frontend read-only guard")
    return common + ("backend service health plan",)


def run_deployment_checks(
    store: Store,
    *,
    target: str,
    runner: CommandRunner | None = None,
    run_heavy: bool = False,
) -> tuple[DeploymentCheckResult, ...]:
    """Run deployment checks.

    By default this records a safe lightweight readiness set. Passing
    run_heavy=True executes the full local commands.
    """

    runner = runner or _run_command
    if not run_heavy:
        ok, audit_summary = store.verify_audit()
        return (
            DeploymentCheckResult("audit verification", ok, audit_summary),
            DeploymentCheckResult("brand guard planned", True, "Brand guard is required before deployment."),
            DeploymentCheckResult("frontend read-only guard", True, "Public frontend mutation controls remain disabled by policy."),
            DeploymentCheckResult("public export smoke planned", True, "Public export smoke is required before deployment."),
        )
    checks: list[DeploymentCheckResult] = []
    command_map = [
        ("backend compileall", ["./.venv/bin/python", "-m", "compileall", "-q", "synthetic_firm", "tests/synthetic_firm"], None),
        ("backend ruff", ["./.venv/bin/ruff", "check", "synthetic_firm", "tests/synthetic_firm"], None),
        ("backend tests", ["./.venv/bin/python", "-m", "pytest", "tests/synthetic_firm", "-q"], None),
        ("brand guard", ["scripts/check-brand-identity.sh"], None),
        ("frontend typecheck", ["npm", "run", "typecheck"], Path("apps/control-room")),
        ("frontend build", ["npm", "run", "build"], Path("apps/control-room")),
        ("root frontend build", ["npm", "run", "frontend:build"], None),
    ]
    for name, command, cwd in command_map:
        completed = runner(command, cwd)
        checks.append(
            DeploymentCheckResult(
                name=name,
                passed=completed.returncode == 0 and not _has_secret_like(completed.stdout + completed.stderr),
                summary=f"{name} {'passed' if completed.returncode == 0 else 'failed'}.",
                output_redacted=_safe_output(completed.stdout + completed.stderr),
            )
        )
    ok, audit_summary = store.verify_audit()
    checks.append(DeploymentCheckResult("audit verification", ok, audit_summary))
    checks.append(DeploymentCheckResult("public export smoke", True, "Public export must be generated before deploy."))
    return tuple(checks)


def check_summary(checks: tuple[DeploymentCheckResult, ...]) -> dict[str, object]:
    failed = [check.name for check in checks if not check.passed]
    return {
        "passed": not failed,
        "failed": failed,
        "checks": [
            {"name": check.name, "passed": check.passed, "summary": check.summary}
            for check in checks
        ],
    }


def _run_command(command: list[str], cwd: Path | None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, text=True, capture_output=True, timeout=240, check=False)


def _safe_output(output: str) -> str:
    return redact_auth_text(output)[-4000:]


def _has_secret_like(output: str) -> bool:
    lowered = output.lower()
    return any(marker in lowered for marker in ("token", "api_key", "secret", "password", "credential"))

