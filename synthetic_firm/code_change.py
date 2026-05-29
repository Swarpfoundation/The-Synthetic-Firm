"""Bounded Forge code-change proposal and patch adapter."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from synthetic_firm.provider_auth_redaction import redact_auth_text
from synthetic_firm.store import Store
from synthetic_firm.time_utils import utc_iso

CODE_PROPOSAL_STATUSES = frozenset({"proposed", "approved", "applied", "tested", "committed", "pushed", "blocked", "failed"})
FORBIDDEN_PATH_PARTS = frozenset(
    {
        ".env",
        ".git/",
        "id_rsa",
        "id_ed25519",
        "credentials",
        "secrets",
        "token",
        "private_key",
    }
)
SECRET_TEXT_MARKERS = ("sk-", "xoxb-", "ghp_", "github_pat_", "api_key=", "password=", "secret=")


class CodeChangeError(ValueError):
    """Raised when the code-change pipeline fails closed."""


@dataclass(frozen=True)
class CodeChangeProposal:
    proposal_id: str
    title: str
    summary: str
    rationale: str
    patch_text: str
    target_branch: str
    base_branch: str
    status: str
    created_by_agent_id: str
    reviewed_by_atlas: bool
    reviewed_by_sentinel: bool
    tests_command: str
    test_status: str | None
    test_summary: str | None
    commit_sha: str | None
    pushed_branch: str | None
    public_summary: str
    private_notes_redacted: str | None
    created_at: str
    updated_at: str
    applied_at: str | None


def create_code_change_proposal(
    store: Store,
    *,
    title: str,
    summary: str,
    rationale: str,
    patch_text: str,
    created_by_agent_id: str = "forge",
    target_branch: str | None = None,
    base_branch: str = "main",
    tests_command: str | None = None,
    public_summary: str | None = None,
    private_notes: str | None = None,
) -> CodeChangeProposal:
    _validate_patch(patch_text)
    proposal_id = f"ccp_{uuid4().hex[:12]}"
    branch = target_branch or f"{os.environ.get('TSF_CODE_BRANCH_PREFIX', 'tsf/forge')}-{proposal_id}"
    now = utc_iso()
    proposal = CodeChangeProposal(
        proposal_id=proposal_id,
        title=redact_auth_text(title),
        summary=redact_auth_text(summary),
        rationale=redact_auth_text(rationale),
        patch_text=redact_auth_text(patch_text),
        target_branch=_safe_branch(branch),
        base_branch=_safe_branch(base_branch),
        status="proposed",
        created_by_agent_id=created_by_agent_id,
        reviewed_by_atlas=False,
        reviewed_by_sentinel=False,
        tests_command=tests_command or "",
        test_status=None,
        test_summary=None,
        commit_sha=None,
        pushed_branch=None,
        public_summary=redact_auth_text(public_summary or summary),
        private_notes_redacted=redact_auth_text(private_notes) if private_notes else None,
        created_at=now,
        updated_at=now,
        applied_at=None,
    )
    _insert_proposal(store, proposal)
    store.append_audit(
        actor_type="agent",
        actor_id=created_by_agent_id,
        action="code_change_proposal_create",
        target_type="code_change_proposal",
        target_id=proposal_id,
        risk_level="medium",
        summary=proposal.public_summary,
        metadata={"target_branch": proposal.target_branch, "status": proposal.status},
    )
    return proposal


def list_code_change_proposals(store: Store, *, status: str | None = None, limit: int = 20) -> list[CodeChangeProposal]:
    params: list[Any] = []
    query = "SELECT * FROM code_change_proposals"
    if status:
        if status not in CODE_PROPOSAL_STATUSES:
            raise CodeChangeError(f"Invalid code proposal status: {status}")
        query += " WHERE status = ?"
        params.append(status)
    query += " ORDER BY created_at DESC, proposal_id DESC LIMIT ?"
    params.append(limit)
    return [_proposal_from_row(row) for row in store.connection.execute(query, params).fetchall()]


def get_code_change_proposal(store: Store, proposal_id: str) -> CodeChangeProposal:
    row = store.connection.execute("SELECT * FROM code_change_proposals WHERE proposal_id = ?", (proposal_id,)).fetchone()
    if not row:
        raise CodeChangeError(f"Code change proposal not found: {proposal_id}")
    return _proposal_from_row(row)


def internally_review_code_change_proposal(store: Store, proposal_id: str) -> CodeChangeProposal:
    proposal = get_code_change_proposal(store, proposal_id)
    _validate_patch(proposal.patch_text)
    now = utc_iso()
    store.connection.execute(
        """
        UPDATE code_change_proposals
        SET reviewed_by_atlas = 1,
            reviewed_by_sentinel = 1,
            status = 'approved',
            updated_at = ?
        WHERE proposal_id = ?
        """,
        (now, proposal_id),
    )
    store.connection.commit()
    store.append_audit(
        actor_type="orchestrator",
        actor_id="atlas_sentinel_review",
        action="code_change_internal_review",
        target_type="code_change_proposal",
        target_id=proposal_id,
        risk_level="medium",
        summary="Atlas and Sentinel internally approved a bounded code-change proposal.",
        metadata={"target_branch": proposal.target_branch},
    )
    return get_code_change_proposal(store, proposal_id)


def apply_code_change_proposal(
    store: Store,
    proposal_id: str,
    *,
    repo_path: str | Path = ".",
    live: bool = False,
    push: bool = False,
    tests_command: str | None = None,
) -> dict[str, Any]:
    proposal = get_code_change_proposal(store, proposal_id)
    if proposal.status != "approved":
        raise CodeChangeError("Code change proposal must be approved before apply.")
    _validate_patch(proposal.patch_text)
    command_text = tests_command or proposal.tests_command
    test_command = _test_command(command_text)
    if not live:
        return {
            "proposalId": proposal_id,
            "live": False,
            "push": False,
            "targetBranch": proposal.target_branch,
            "summary": "Code-change proposal passed dry-run policy checks. No files changed.",
            "testsCommand": " ".join(test_command),
        }

    repo = Path(repo_path).resolve()
    _ensure_git_repo(repo)
    if _git(repo, "status", "--porcelain").stdout.strip():
        raise CodeChangeError("Repository has uncommitted changes; code-change apply failed closed.")

    _git(repo, "checkout", "-B", proposal.target_branch)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
        handle.write(proposal.patch_text)
        patch_path = Path(handle.name)
    try:
        _git(repo, "apply", "--check", str(patch_path))
        _git(repo, "apply", str(patch_path))
    finally:
        patch_path.unlink(missing_ok=True)

    store.connection.execute(
        "UPDATE code_change_proposals SET status = 'applied', applied_at = ?, updated_at = ? WHERE proposal_id = ?",
        (utc_iso(), utc_iso(), proposal_id),
    )
    store.connection.commit()

    test_result = _run_test_command(repo, test_command)
    if test_result.returncode != 0:
        summary = _command_summary(test_result)
        _update_pipeline_state(store, proposal_id, status="failed", test_status="failed", test_summary=summary)
        store.append_audit(
            actor_type="coding_adapter",
            actor_id="forge_patch_pipeline",
            action="code_change_tests_failed",
            target_type="code_change_proposal",
            target_id=proposal_id,
            risk_level="high",
            summary=summary,
        )
        raise CodeChangeError(f"Code-change tests failed: {summary}")

    summary = _command_summary(test_result) or "Code-change tests passed."
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.email=forge@synthetic-firm.local", "-c", "user.name=TSF Forge", "commit", "-m", _commit_message(proposal))
    commit_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    pushed_branch = None
    if push:
        _git(repo, "push", "-u", "origin", proposal.target_branch)
        pushed_branch = proposal.target_branch

    _update_pipeline_state(
        store,
        proposal_id,
        status="pushed" if pushed_branch else "committed",
        test_status="passed",
        test_summary=summary,
        commit_sha=commit_sha,
        pushed_branch=pushed_branch,
    )
    store.append_audit(
        actor_type="coding_adapter",
        actor_id="forge_patch_pipeline",
        action="code_change_committed" if not pushed_branch else "code_change_pushed",
        target_type="code_change_proposal",
        target_id=proposal_id,
        risk_level="medium",
        summary=f"Code-change proposal committed to {commit_sha[:12]}.",
        metadata={"target_branch": proposal.target_branch, "pushed": bool(pushed_branch)},
    )
    return {
        "proposalId": proposal_id,
        "live": True,
        "push": bool(pushed_branch),
        "targetBranch": proposal.target_branch,
        "commitSha": commit_sha,
        "testStatus": "passed",
        "summary": f"Code-change proposal committed to {commit_sha[:12]}.",
    }


def code_change_public_summary(store: Store) -> dict[str, Any]:
    proposals = list_code_change_proposals(store, limit=50)
    counts = {status: 0 for status in sorted(CODE_PROPOSAL_STATUSES)}
    for proposal in proposals:
        counts[proposal.status] = counts.get(proposal.status, 0) + 1
    recent = [
        {
            "proposalId": proposal.proposal_id,
            "status": proposal.status,
            "publicSummary": proposal.public_summary,
            "targetBranch": proposal.target_branch if proposal.status in {"committed", "pushed"} else None,
            "commitSha": proposal.commit_sha[:12] if proposal.commit_sha else None,
            "testStatus": proposal.test_status,
            "updatedAt": proposal.updated_at,
        }
        for proposal in proposals[:5]
    ]
    return {
        "statusCounts": counts,
        "recent": recent,
        "summary": "No Forge code-change proposals yet." if not proposals else f"{len(proposals)} Forge code-change proposal(s) tracked.",
    }


def proposal_to_dict(proposal: CodeChangeProposal, *, include_patch: bool = False) -> dict[str, Any]:
    payload = asdict(proposal)
    payload.pop("patch_text", None)
    if include_patch:
        payload["patchText"] = proposal.patch_text
    return _camelize(payload)


def _insert_proposal(store: Store, proposal: CodeChangeProposal) -> None:
    store.connection.execute(
        """
        INSERT INTO code_change_proposals VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        _proposal_values(proposal),
    )
    store.connection.commit()


def _update_pipeline_state(
    store: Store,
    proposal_id: str,
    *,
    status: str,
    test_status: str | None = None,
    test_summary: str | None = None,
    commit_sha: str | None = None,
    pushed_branch: str | None = None,
) -> None:
    if status not in CODE_PROPOSAL_STATUSES:
        raise CodeChangeError(f"Invalid code proposal status: {status}")
    store.connection.execute(
        """
        UPDATE code_change_proposals
        SET status = ?,
            test_status = COALESCE(?, test_status),
            test_summary = COALESCE(?, test_summary),
            commit_sha = COALESCE(?, commit_sha),
            pushed_branch = COALESCE(?, pushed_branch),
            updated_at = ?
        WHERE proposal_id = ?
        """,
        (status, test_status, redact_auth_text(test_summary) if test_summary else None, commit_sha, pushed_branch, utc_iso(), proposal_id),
    )
    store.connection.commit()


def _proposal_values(proposal: CodeChangeProposal) -> tuple[Any, ...]:
    return (
        proposal.proposal_id,
        proposal.title,
        proposal.summary,
        proposal.rationale,
        proposal.patch_text,
        proposal.target_branch,
        proposal.base_branch,
        proposal.status,
        proposal.created_by_agent_id,
        int(proposal.reviewed_by_atlas),
        int(proposal.reviewed_by_sentinel),
        proposal.tests_command,
        proposal.test_status,
        proposal.test_summary,
        proposal.commit_sha,
        proposal.pushed_branch,
        proposal.public_summary,
        proposal.private_notes_redacted,
        proposal.created_at,
        proposal.updated_at,
        proposal.applied_at,
    )


def _proposal_from_row(row: Any) -> CodeChangeProposal:
    return CodeChangeProposal(
        proposal_id=row["proposal_id"],
        title=row["title"],
        summary=row["summary"],
        rationale=row["rationale"],
        patch_text=row["patch_text"],
        target_branch=row["target_branch"],
        base_branch=row["base_branch"],
        status=row["status"],
        created_by_agent_id=row["created_by_agent_id"],
        reviewed_by_atlas=bool(row["reviewed_by_atlas"]),
        reviewed_by_sentinel=bool(row["reviewed_by_sentinel"]),
        tests_command=row["tests_command"],
        test_status=row["test_status"],
        test_summary=row["test_summary"],
        commit_sha=row["commit_sha"],
        pushed_branch=row["pushed_branch"],
        public_summary=row["public_summary"],
        private_notes_redacted=row["private_notes_redacted"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        applied_at=row["applied_at"],
    )


def _validate_patch(patch_text: str) -> None:
    if not patch_text.strip():
        raise CodeChangeError("Patch text is required.")
    if "+++" not in patch_text or "---" not in patch_text:
        raise CodeChangeError("Patch must be a unified diff.")
    lowered = patch_text.lower()
    if any(marker in lowered for marker in SECRET_TEXT_MARKERS):
        raise CodeChangeError("Patch contains secret-like text and is blocked.")
    for path in _patch_paths(patch_text):
        _validate_patch_path(path)


def _patch_paths(patch_text: str) -> set[str]:
    paths: set[str] = set()
    for raw_line in patch_text.splitlines():
        line = raw_line.strip()
        for prefix in ("--- ", "+++ "):
            if line.startswith(prefix):
                value = line[len(prefix) :].split("\t", 1)[0].strip()
                if value != "/dev/null":
                    paths.add(_strip_diff_prefix(value))
        if line.startswith("diff --git "):
            parts = line.split()
            if len(parts) >= 4:
                paths.add(_strip_diff_prefix(parts[2]))
                paths.add(_strip_diff_prefix(parts[3]))
    return paths


def _strip_diff_prefix(path: str) -> str:
    if path.startswith(("a/", "b/")):
        return path[2:]
    return path


def _validate_patch_path(path: str) -> None:
    normalized = path.replace("\\", "/")
    if normalized.startswith("/") or normalized.startswith("../") or "/../" in normalized:
        raise CodeChangeError(f"Unsafe patch path blocked: {path}")
    lowered = normalized.lower()
    if any(part in lowered for part in FORBIDDEN_PATH_PARTS):
        raise CodeChangeError(f"Sensitive patch path blocked: {path}")


def _safe_branch(branch: str) -> str:
    if not branch or any(part in branch for part in ("..", " ", "~", "^", ":", "?", "*", "[", "\\", "@{")):
        raise CodeChangeError(f"Unsafe git branch blocked: {branch}")
    return branch


def _ensure_git_repo(repo: Path) -> None:
    if not repo.exists():
        raise CodeChangeError(f"Repository path not found: {repo}")
    _git(repo, "rev-parse", "--show-toplevel")


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
        timeout=120,
    )
    if result.returncode != 0:
        raise CodeChangeError(_command_summary(result) or f"git {' '.join(args)} failed")
    return result


def _test_command(command_text: str | None) -> list[str]:
    if command_text:
        if any(token in command_text for token in (";", "&&", "||", "|", ">", "<", "$(", "`")):
            raise CodeChangeError("Shell control operators are blocked in test command.")
        command = shlex.split(command_text)
    else:
        command = [sys.executable, "-m", "pytest", "tests/synthetic_firm", "-q"]
    if not command:
        raise CodeChangeError("Test command is empty.")
    return command


def _run_test_command(repo: Path, command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=repo, text=True, capture_output=True, check=False, timeout=300)


def _command_summary(result: subprocess.CompletedProcess[str]) -> str:
    text = "\n".join(part for part in (result.stdout, result.stderr) if part).strip()
    return redact_auth_text(text[-1000:] if text else f"Command exited with {result.returncode}.")


def _commit_message(proposal: CodeChangeProposal) -> str:
    title = proposal.title.strip().replace("\n", " ")
    return f"Forge: {title[:64]}"


def _camelize(payload: dict[str, Any]) -> dict[str, Any]:
    return {_camel_key(key): value for key, value in payload.items()}


def _camel_key(key: str) -> str:
    head, *tail = key.split("_")
    return head + "".join(part.capitalize() for part in tail)
