from synthetic_firm.cli import main


def test_cli_dry_run_does_not_print_secret(monkeypatch, capsys):
    monkeypatch.setenv("TSF_KIMI_API_KEY", "sensitive-test-value")

    code = main(["atlas", "--dry-run"])

    output = capsys.readouterr().out
    assert code == 0
    assert "sensitive-test-value" not in output
    assert '"api_key_available": true' in output


def test_cli_budget_status_no_secret_output(capsys):
    code = main(
        [
            "show-budget-status",
            "--agent-limit",
            "10",
            "--task-limit",
            "5",
            "--company-limit",
            "25",
            "--max-loop-steps",
            "10",
            "--max-tool-calls",
            "20",
            "--agent-spend",
            "1",
            "--task-spend",
            "1",
            "--company-spend",
            "2",
            "--loop-steps",
            "3",
            "--tool-calls",
            "4",
            "--dry-run",
        ]
    )

    output = capsys.readouterr().out
    assert code == 0
    assert "allowed" in output
    assert "API_KEY" not in output


def test_cli_store_commands_use_tsf_home(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))

    assert main(["init-store"]) == 0
    assert main(["store-status"]) == 0
    assert main(["runtime-status"]) == 0

    output = capsys.readouterr().out
    assert "synthetic-firm.sqlite3" in output
    assert str(tmp_path) in output
    assert "secret" not in output.lower()
