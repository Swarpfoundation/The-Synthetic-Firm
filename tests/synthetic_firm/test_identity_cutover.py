import subprocess

from synthetic_firm.budget_log import tsf_home
from synthetic_firm.cli import main


def test_tsf_home_is_preferred(monkeypatch, tmp_path):
    preferred = tmp_path / "preferred"
    legacy = tmp_path / "legacy"
    monkeypatch.setenv("TSF_HOME", str(preferred))
    monkeypatch.setenv("HER" + "MES_HOME", str(legacy))

    assert tsf_home() == preferred


def test_legacy_home_fallback_is_intentional(monkeypatch, tmp_path):
    legacy = tmp_path / "legacy"
    monkeypatch.delenv("TSF_HOME", raising=False)
    monkeypatch.setenv("HER" + "MES_HOME", str(legacy))

    assert tsf_home() == legacy


def test_cli_help_uses_tsf_identity(capsys):
    try:
        main(["--help"])
    except SystemExit as exc:
        assert exc.code == 0

    output = capsys.readouterr().out
    assert "synthetic-firm" in output
    assert "The Synthetic Firm" in output
    assert ("Her" + "mes") not in output
    assert ("HER" + "MES_") not in output
    assert "Atlas" not in output  # Help uses ids, not narrative branding.


def test_brand_guard_passes():
    result = subprocess.run(
        ["bash", "scripts/check-brand-identity.sh"],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
