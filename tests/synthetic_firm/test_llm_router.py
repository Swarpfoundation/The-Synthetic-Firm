from synthetic_firm.agent_registry import AgentRegistry
from synthetic_firm.llm_router import env_with_api_key_alias, resolve_model_route


def test_model_route_resolves_without_secret_value():
    profile = AgentRegistry.from_file("agents/profiles.yaml").get("scout")
    route = resolve_model_route(profile, env={"TSF_KIMI_API_KEY": "sensitive-test-value"})

    assert route.provider == "kimi-coding"
    assert route.model == "kimi-for-coding"
    assert route.api_key_alias == "TSF_KIMI_API_KEY"
    assert route.api_key_env == "KIMI_API_KEY"
    assert route.api_key_available is True
    assert "sensitive-test-value" not in repr(route)


def test_env_alias_maps_to_provider_expected_key():
    profile = AgentRegistry.from_file("agents/profiles.yaml").get("atlas")
    route = resolve_model_route(profile, env={"TSF_KIMI_API_KEY": "sensitive-test-value"})

    child_env = env_with_api_key_alias(route, env={"TSF_KIMI_API_KEY": "sensitive-test-value"})

    assert child_env["KIMI_API_KEY"] == "sensitive-test-value"
    assert child_env["TSF_KIMI_API_KEY"] == "sensitive-test-value"


def test_native_env_key_wins_over_alias():
    profile = AgentRegistry.from_file("agents/profiles.yaml").get("atlas")
    route = resolve_model_route(profile, env={"TSF_KIMI_API_KEY": "alias", "KIMI_API_KEY": "native"})

    child_env = env_with_api_key_alias(
        route,
        env={"TSF_KIMI_API_KEY": "alias", "KIMI_API_KEY": "native"},
    )

    assert child_env["KIMI_API_KEY"] == "native"
