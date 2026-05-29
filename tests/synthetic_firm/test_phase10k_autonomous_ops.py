from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from synthetic_firm.autonomous_ops import autonomous_ops_status, run_autonomous_ops_once
from synthetic_firm.cli import main
from synthetic_firm.code_change import create_code_change_proposal, internally_review_code_change_proposal, list_code_change_proposals
from synthetic_firm.control_room_export import build_control_room_snapshot
from synthetic_firm.scheduler import run_checkpoint_once
from synthetic_firm.store import Store


PATCH_TEXT = """diff --git a/forge_ops_note.txt b/forge_ops_note.txt
new file mode 100644
index 0000000..39049ac
--- /dev/null
+++ b/forge_ops_note.txt
@@ -0,0 +1 @@
+Autonomous bounded ops.
"""


def test_autonomous_ops_disabled_by_default(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("TSF_AUTONOMOUS_OPS_ENABLED", raising=False)

    store = Store()
    status = autonomous_ops_status({})
    result = run_autonomous_ops_once(store, env={})

    assert status["enabled"] is False
    assert result["status"] == "skipped"
    assert "disabled" in result["summary"]
    assert store.verify_audit()[0] is True
    store.close()


def test_autonomous_ops_applies_approved_patch(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path / "home"))
    repo = tmp_path / "repo"
    _init_repo(repo)
    store = Store()
    proposal = create_code_change_proposal(
        store,
        title="Add autonomous ops note",
        summary="Forge proposed a bounded autonomous ops patch.",
        rationale="The runtime needs autonomous patch execution after internal review.",
        patch_text=PATCH_TEXT,
    )
    internally_review_code_change_proposal(store, proposal.proposal_id)

    env = {
        "TSF_AUTONOMOUS_OPS_ENABLED": "true",
        "TSF_AUTONOMOUS_CODE_APPLY_ENABLED": "true",
        "TSF_AUTONOMOUS_CODE_PUSH_ENABLED": "false",
        "TSF_CODE_REPO_PATH": str(repo),
        "TSF_CODE_TEST_COMMAND": f"{sys.executable} -c pass",
    }
    result = run_autonomous_ops_once(store, env=env)
    updated = list_code_change_proposals(store)[0]

    assert result["status"] == "completed"
    assert result["codeResults"][0]["status"] == "completed"
    assert result["codeResults"][0]["pushed"] is False
    assert updated.status == "committed"
    assert (repo / "forge_ops_note.txt").read_text(encoding="utf-8").strip() == "Autonomous bounded ops."
    assert store.verify_audit()[0] is True
    store.close()


def test_autonomous_ops_public_export_is_sanitized(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("TSF_AUTONOMOUS_OPS_ENABLED", "true")
    monkeypatch.setenv("TSF_AUTONOMOUS_CODE_APPLY_ENABLED", "true")
    monkeypatch.setenv("TSF_AUTONOMOUS_CODE_PUSH_ENABLED", "true")
    monkeypatch.setenv("TSF_CODE_REPO_PATH", str(tmp_path / "private-repo-path"))
    store = Store()

    snapshot = build_control_room_snapshot(store, audience="public")
    dumped = json.dumps(snapshot)

    assert snapshot["autonomousOps"]["enabled"] is True
    assert snapshot["autonomousOps"]["codePushEnabled"] is True
    assert str(tmp_path) not in dumped
    store.close()


def test_scheduler_cycle_runs_autonomous_ops_when_disabled(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("TSF_AUTONOMOUS_OPS_ENABLED", raising=False)
    store = Store()

    result = run_checkpoint_once(store, now=_utc("2026-05-29T08:30:00+00:00"))

    assert result["status"] == "completed"
    assert result["result"]["autonomous_ops"]["status"] == "skipped"
    assert store.verify_audit()[0] is True
    store.close()


def test_autonomous_ops_cli_commands(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("TSF_HOME", str(tmp_path / "home"))

    assert main(["autonomous-ops-status"]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["enabled"] is False

    assert main(["autonomous-ops-once"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "skipped"


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


def _utc(value: str):
    from datetime import datetime

    return datetime.fromisoformat(value)
