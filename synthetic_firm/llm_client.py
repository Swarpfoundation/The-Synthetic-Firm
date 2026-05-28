"""Safe LLM client abstraction for bounded TSF agent reasoning."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from synthetic_firm.model_provider import (
    ModelProviderRoute,
    provider_api_key,
    provider_status as model_provider_status,
    resolve_model_provider,
    safe_provider_error,
)
from synthetic_firm.provider_auth_redaction import redact_auth_text
from synthetic_firm.store import Store


class LlmClientError(ValueError):
    """Raised when a model reasoning call fails closed."""


@dataclass(frozen=True)
class AgentReasoningRequest:
    agent_id: str
    purpose: str
    system_instructions: str
    context_summary: str
    allowed_outputs: tuple[str, ...]
    forbidden_outputs: tuple[str, ...]
    max_output_chars: int
    require_json: bool
    risk_level: str
    budget_context: dict[str, Any]
    task_id: str | None = None
    workday_id: str | None = None


@dataclass(frozen=True)
class AgentReasoningResponse:
    provider: str
    model: str
    dry_run: bool
    output_text: str
    structured_output: dict[str, Any] | None
    input_chars: int
    output_chars: int
    usage_estimate: dict[str, Any]
    redacted_debug_summary: str
    status: str
    error_redacted: str | None = None


def provider_status(env: Mapping[str, str] | None = None) -> dict[str, object]:
    return model_provider_status(env)


def dry_run_agent_reasoning(request: AgentReasoningRequest) -> AgentReasoningResponse:
    structured = _empty_structured_output(request.agent_id, request.purpose)
    output = json.dumps(structured, sort_keys=True)
    return AgentReasoningResponse(
        provider="dry-run",
        model="dry-run",
        dry_run=True,
        output_text=output[: request.max_output_chars],
        structured_output=structured if request.require_json else None,
        input_chars=_input_size(request),
        output_chars=len(output),
        usage_estimate=_usage_estimate(_input_size(request), len(output)),
        redacted_debug_summary=f"Dry-run reasoning prepared for {request.agent_id}.",
        status="success",
    )


def complete_agent_reasoning(
    request: AgentReasoningRequest,
    *,
    store: Store | None = None,
    env: Mapping[str, str] | None = None,
    client_factory: Callable[..., Any] | None = None,
) -> AgentReasoningResponse:
    own_store = False
    if store is None:
        store = Store()
        own_store = True
    try:
        route = resolve_model_provider(env)
        _audit_request(store, request, route)
        if route.provider == "dry-run" or route.dry_run:
            response = dry_run_agent_reasoning(request)
            _record_success(store, request, response)
            return response
        if not route.connected:
            response = _unavailable_response(request, route)
            _audit_failure(store, request, response, action="model_unavailable")
            return response
        if _input_size(request) > route.max_input_chars:
            response = _failed_response(request, route, "Model input exceeded configured character limit.")
            _audit_failure(store, request, response, action="model_budget_block")
            return response
        output = _call_provider(request, route, env=env, client_factory=client_factory)
        if len(output) > min(request.max_output_chars, route.max_output_chars):
            output = output[: min(request.max_output_chars, route.max_output_chars)]
        structured = _parse_structured_output(output) if request.require_json else None
        if request.require_json and structured is None:
            response = _failed_response(request, route, "Model returned malformed JSON.")
            _audit_failure(store, request, response, action="malformed_model_output")
            return response
        response = AgentReasoningResponse(
            provider=route.provider,
            model=route.model,
            dry_run=False,
            output_text=redact_auth_text(output),
            structured_output=structured,
            input_chars=_input_size(request),
            output_chars=len(output),
            usage_estimate=_usage_estimate(_input_size(request), len(output)),
            redacted_debug_summary=f"Model reasoning completed for {request.agent_id} via {route.provider}.",
            status="success",
        )
        _record_success(store, request, response)
        return response
    except Exception as exc:
        try:
            route
        except UnboundLocalError:
            route = resolve_model_provider({"TSF_MODEL_PROVIDER": "dry-run"})
        response = _failed_response(request, route, safe_provider_error(exc))
        _audit_failure(store, request, response, action="model_reasoning_failure")
        return response
    finally:
        if own_store:
            store.close()


def estimate_or_record_usage(
    store: Store | None,
    request: AgentReasoningRequest,
    response: AgentReasoningResponse,
    *,
    record: bool = True,
) -> dict[str, Any]:
    usage = _usage_estimate(response.input_chars, response.output_chars)
    if record and store is not None and request.task_id:
        store.record_budget_usage(
            amount_usd=float(usage["estimated_usd"]),
            loop_steps=1,
            tool_calls=1,
            summary=f"Model reasoning usage recorded for {request.agent_id}.",
            agent_id=request.agent_id,
            task_id=request.task_id,
        )
    return usage


def response_to_dict(response: AgentReasoningResponse) -> dict[str, Any]:
    return {
        "provider": response.provider,
        "model": response.model,
        "dry_run": response.dry_run,
        "status": response.status,
        "output_text": redact_auth_text(response.output_text),
        "structured_output": response.structured_output,
        "input_chars": response.input_chars,
        "output_chars": response.output_chars,
        "usage_estimate": response.usage_estimate,
        "redacted_debug_summary": response.redacted_debug_summary,
        "error_redacted": response.error_redacted,
    }


def _call_provider(
    request: AgentReasoningRequest,
    route: ModelProviderRoute,
    *,
    env: Mapping[str, str] | None,
    client_factory: Callable[..., Any] | None,
) -> str:
    key = provider_api_key(route, env)
    factory = client_factory or _openai_client_factory
    kwargs: dict[str, Any] = {"api_key": key, "timeout": route.timeout_seconds}
    if route.base_url:
        kwargs["base_url"] = route.base_url
    client = factory(**kwargs)
    completion = client.chat.completions.create(
        model=route.model,
        messages=[
            {"role": "system", "content": _trim(request.system_instructions, 4000)},
            {"role": "user", "content": _prompt_from_request(request)},
        ],
        max_tokens=max(64, min(route.max_output_chars // 4, 2048)),
        temperature=0.1,
    )
    return str(completion.choices[0].message.content or "")


def _openai_client_factory(**kwargs: Any) -> Any:
    from openai import OpenAI

    return OpenAI(**kwargs)


def _prompt_from_request(request: AgentReasoningRequest) -> str:
    payload = {
        "agent_id": request.agent_id,
        "task_id": request.task_id,
        "workday_id": request.workday_id,
        "purpose": request.purpose,
        "context_summary": request.context_summary,
        "allowed_outputs": list(request.allowed_outputs),
        "forbidden_outputs": list(request.forbidden_outputs),
        "require_json": request.require_json,
        "budget_context": request.budget_context,
    }
    return redact_auth_text(json.dumps(payload, sort_keys=True))


def _empty_structured_output(agent_id: str, purpose: str) -> dict[str, Any]:
    return {
        "summary": f"Dry-run reasoning for {agent_id}: {purpose}",
        "proposed_tasks": [],
        "messages_to_agents": [],
        "human_tasks": [],
        "assumptions": ["Dry-run mode is active; no live model reasoning was executed."],
        "evidence_refs": [],
        "blocked_reasons": [],
        "public_report_notes": [],
        "private_founder_notes": [],
    }


def _parse_structured_output(output: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(output)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _input_size(request: AgentReasoningRequest) -> int:
    return sum(
        len(item)
        for item in (
            request.agent_id,
            request.purpose,
            request.system_instructions,
            request.context_summary,
            json.dumps(request.budget_context, sort_keys=True),
        )
    )


def _usage_estimate(input_chars: int, output_chars: int) -> dict[str, Any]:
    estimated_tokens = max(1, (input_chars + output_chars) // 4)
    return {
        "input_chars": input_chars,
        "output_chars": output_chars,
        "estimated_tokens": estimated_tokens,
        "estimated_usd": round(estimated_tokens * 0.000002, 6),
    }


def _audit_request(store: Store, request: AgentReasoningRequest, route: ModelProviderRoute) -> None:
    store.append_audit(
        actor_type="agent",
        actor_id=request.agent_id,
        action="model_reasoning_request",
        target_type="workday" if request.workday_id else "model_reasoning",
        target_id=request.workday_id or request.task_id or request.agent_id,
        risk_level=request.risk_level,
        summary=f"{request.agent_id} requested bounded model reasoning via {route.provider}.",
        metadata={"provider": route.provider, "model": route.model, "dry_run": route.dry_run},
    )


def _record_success(store: Store, request: AgentReasoningRequest, response: AgentReasoningResponse) -> None:
    estimate_or_record_usage(store, request, response, record=bool(request.task_id))
    store.append_audit(
        actor_type="agent",
        actor_id=request.agent_id,
        action="model_reasoning_success" if response.status == "success" else "model_reasoning_result",
        target_type="workday" if request.workday_id else "model_reasoning",
        target_id=request.workday_id or request.task_id or request.agent_id,
        risk_level=request.risk_level,
        summary=response.redacted_debug_summary,
        metadata={"provider": response.provider, "model": response.model, "dry_run": response.dry_run},
    )


def _audit_failure(
    store: Store,
    request: AgentReasoningRequest,
    response: AgentReasoningResponse,
    *,
    action: str,
) -> None:
    store.append_audit(
        actor_type="agent",
        actor_id=request.agent_id,
        action=action,
        target_type="workday" if request.workday_id else "model_reasoning",
        target_id=request.workday_id or request.task_id or request.agent_id,
        risk_level="medium",
        summary=response.error_redacted or response.redacted_debug_summary,
        metadata={"provider": response.provider, "model": response.model, "status": response.status},
    )


def _unavailable_response(request: AgentReasoningRequest, route: ModelProviderRoute) -> AgentReasoningResponse:
    return AgentReasoningResponse(
        provider=route.provider,
        model=route.model,
        dry_run=route.dry_run,
        output_text="",
        structured_output=None,
        input_chars=_input_size(request),
        output_chars=0,
        usage_estimate=_usage_estimate(_input_size(request), 0),
        redacted_debug_summary=route.safe_summary,
        status="unavailable",
        error_redacted=route.safe_summary,
    )


def _failed_response(request: AgentReasoningRequest, route: ModelProviderRoute, error: str) -> AgentReasoningResponse:
    return AgentReasoningResponse(
        provider=route.provider,
        model=route.model,
        dry_run=route.dry_run,
        output_text="",
        structured_output=None,
        input_chars=_input_size(request),
        output_chars=0,
        usage_estimate=_usage_estimate(_input_size(request), 0),
        redacted_debug_summary="Model reasoning failed closed.",
        status="failed",
        error_redacted=redact_auth_text(error),
    )


def _trim(value: str, limit: int) -> str:
    text = redact_auth_text(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"
