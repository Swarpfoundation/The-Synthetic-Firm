from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from synthetic_firm.cli import main
from synthetic_firm.code_change import (
    CodeChangeError,
    apply_code_change_proposal,
    code_change_public_summary,
    create_code_change_proposal,
    internally_review_code_change_proposal,
    list_code_change_proposals,
)
from synthetic_firm.control_room_export import build_control_room_snapshot
from synthetic_firm.store import Store


PATCH_TEXT = """diff --git a/forge_note.txt b/forge_note.txt
new file mode 100644
index 0000000..ce01362
--- /dev/null
+++ b/forge_note.txt
@@ -0,0 +1 @@
+Forge bounded patch pipeline.
"""


def test_code_change_proposal_lifecycle_and_public_export(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path / "home"))
    store = Store()

    proposal = create_code_change_proposal(
        store,
        title="Add Forge note",
        summary="Forge proposed a bounded repo patch.",
        rationale="The runtime needs a safe patch pipeline.",
        patch_text=PATCH_TEXT,
    )
    reviewed = internally_review_code_change_proposal(store, proposal.proposal_id)
    dry_run = apply_code_change_proposal(store, proposal.proposal_id)
    public = code_change_public_summary(store)
    snapshot = build_control_room_snapshot(store, audience="public")
    dumped = json.dumps(snapshot)

    assert proposal.status == "proposed"
    assert reviewed.status == "approved"
    assert dry_run["live"] is False
    assert public["statusCounts"]["approved"] == 1
    assert snapshot["codeChangeSummary"]["statusCounts"]["approved"] == 1
    assert "Forge bounded patch pipeline" not in dumped
    assert store.verify_audit()[0] is True
    store.close()


def test_code_change_blocks_secret_or_sensitive_paths(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path / "home"))
    store = Store()
    secret_patch = PATCH_TEXT.replace("forge_note.txt", ".env").replace("Forge bounded patch pipeline.", "secret=value")

    with pytest.raises(CodeChangeError):
        create_code_change_proposal(
            store,
            title="Unsafe",
            summary="Unsafe patch.",
            rationale="Should fail.",
            patch_text=secret_patch,
        )
    store.close()


def test_code_change_live_apply_tests_and_commit(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path / "home"))
    repo = tmp_path / "repo"
    _init_repo(repo)
    store = Store()
    proposal = create_code_change_proposal(
        store,
        title="Add Forge note",
        summary="Forge proposed a bounded repo patch.",
        rationale="The runtime needs a safe patch pipeline.",
        patch_text=PATCH_TEXT,
        tests_command=f"{sys.executable} -c pass",
    )
    internally_review_code_change_proposal(store, proposal.proposal_id)

    result = apply_code_change_proposal(store, proposal.proposal_id, repo_path=repo, live=True)
    updated = list_code_change_proposals(store)[0]

    assert result["commitSha"]
    assert result["push"] is False
    assert updated.status == "committed"
    assert updated.test_status == "passed"
    assert (repo / "forge_note.txt").read_text(encoding="utf-8").strip() == "Forge bounded patch pipeline."
    assert store.verify_audit()[0] is True
    store.close()


def test_code_change_cli_commands(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("TSF_HOME", str(tmp_path / "home"))
    patch_file = tmp_path / "change.patch"
    patch_file.write_text(PATCH_TEXT, encoding="utf-8")

    assert main(
        [
            "code-proposal-create",
            "--title",
            "Add Forge note",
            "--summary",
            "Forge proposed a bounded repo patch.",
            "--rationale",
            "The runtime needs a safe patch pipeline.",
            "--patch-file",
            str(patch_file),
        ]
    ) == 0
    created = json.loads(capsys.readouterr().out)
    proposal_id = created["proposal"]["proposalId"]

    assert main(["code-proposal-review", proposal_id]) == 0
    assert "approved" in capsys.readouterr().out
    assert main(["code-proposal-public-summary"]) == 0
    assert "Forge code-change proposal" in capsys.readouterr().out


def _init_repo(repo: Path) -> None:
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    (repo / "README.md").write_text("# test repo\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=test@example.com",
            "-c",
            "user.name=Test",
            "commit",
            "-m",
            "initial",
        ],
        cwd=repo,
        check=True,
        capture_output=True,
    )
