import json

from synthetic_firm.agent_registry import AgentRegistry
from synthetic_firm.budget_log import append_budget_log
from synthetic_firm.llm_router import resolve_model_route


def test_budget_log_writes_non_secret_metadata(tmp_path, monkeypatch):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    profile = AgentRegistry.from_file("agents/profiles.yaml").get("atlas")
    route = resolve_model_route(profile, env={"TSF_KIMI_API_KEY": "sensitive-test-value"})

    path = append_budget_log(profile, route, event="agent_run_start")

    payload = json.loads(path.read_text(encoding="utf-8").strip())
    assert payload["agent_id"] == "atlas"
    assert payload["provider"] == "kimi-coding"
    assert payload["budget"]["daily_usd"] == 10.0
    assert payload["enforcement"] == "not_enforced_phase_1"
    assert "sensitive-test-value" not in path.read_text(encoding="utf-8")
