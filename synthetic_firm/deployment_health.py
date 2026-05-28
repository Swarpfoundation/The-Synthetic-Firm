"""Public-safe deployment health checks."""

from __future__ import annotations

from typing import Callable, Mapping
from urllib.error import URLError
from urllib.request import Request, urlopen
from urllib.parse import urlsplit

from synthetic_firm.deployment import DeploymentCheckResult
from synthetic_firm.provider_auth_redaction import redact_auth_text
from synthetic_firm.store import Store

HealthFetcher = Callable[[str, int], tuple[int, str]]


def run_vercel_preview_health_check(
    url: str | None,
    *,
    env: Mapping[str, str] | None = None,
    fetcher: HealthFetcher | None = None,
    store: Store | None = None,
) -> DeploymentCheckResult:
    """Check a Vercel preview URL without exposing private output."""

    if not _safe_vercel_preview_url(url, env=env):
        result = DeploymentCheckResult("preview health check", False, "Preview URL is not public-safe.")
        _audit_health(store, result, url="invalid")
        return result
    timeout = _timeout(env)
    fetcher = fetcher or _fetch_url
    try:
        status_code, body = fetcher(str(url), min(timeout, 30))
    except Exception as exc:
        result = DeploymentCheckResult("preview health check", False, "Preview health check failed.", redact_auth_text(str(exc)))
        _audit_health(store, result, url=str(url))
        return result
    lowered = body.lower()
    forbidden_secret_markers = (
        "api_key",
        "access_token",
        "refresh_token",
        "secret=",
        "token=",
    )
    has_read_only_marker = _has_read_only_marker(lowered)
    has_forbidden_content = any(marker in lowered for marker in forbidden_secret_markers) or _has_mutation_control_marker(lowered)
    passed = 200 <= status_code < 400 and not has_forbidden_content
    summary = "Preview health check passed." if passed else "Preview health check failed."
    if passed and has_read_only_marker:
        summary = "Preview health check passed; read-only marker detected."
    elif passed:
        summary = "Preview health check passed; read-only marker was not detected in bounded content."
    result = DeploymentCheckResult("preview health check", passed, summary, f"HTTP {status_code}")
    _audit_health(store, result, url=str(url))
    return result


def _safe_vercel_preview_url(value: str | None, *, env: Mapping[str, str] | None = None) -> bool:
    text = str(value or "").strip()
    lowered = text.lower()
    if "@" in text or "token" in lowered or "secret" in lowered:
        return False
    try:
        split = urlsplit(text)
    except ValueError:
        return False
    host = split.hostname or ""
    allow_local = bool(env and str(env.get("TSF_DEPLOY_ALLOW_LOCAL_HEALTH", "")).lower() in {"1", "true", "yes", "on"})
    allowed_hosts = {
        item.strip().lower()
        for item in str((env or {}).get("TSF_VERCEL_ALLOWED_PREVIEW_HOSTS", "")).split(",")
        if item.strip()
    }
    if split.scheme == "http" and allow_local and host in {"localhost", "127.0.0.1", "::1"}:
        return True
    if split.scheme != "https":
        return False
    return host.endswith(".vercel.app") or host in allowed_hosts


def _has_read_only_marker(lowered_body: str) -> bool:
    return any(
        marker in lowered_body
        for marker in (
            "public progress window",
            "read-only public view",
            "real tsf runtime data only",
            'data-tsf-public-progress-window="true"',
            "data-tsf-public-progress-window='true'",
            'data-tsf-read-only="true"',
            "data-tsf-read-only='true'",
        )
    )


def _has_mutation_control_marker(lowered_body: str) -> bool:
    control_terms = ("approve", "deny", "pause", "resume", "kill", "create task")
    if "data-tsf-mutation-control" in lowered_body:
        return True
    for element in ("button", "form"):
        if _element_contains_control(lowered_body, element, control_terms):
            return True
    for marker in (
        "approve deployment",
        "deny deployment",
        "pause runtime",
        "resume runtime",
        "kill runtime",
        "command input",
        "chat input",
        "create task",
        'aria-label="approve',
        'aria-label="deny',
        'aria-label="pause',
        'aria-label="resume',
        'aria-label="kill',
        'name="command"',
        'name="chat"',
        'data-action="approve"',
        'data-action="deny"',
        'data-action="pause"',
        'data-action="resume"',
        'data-action="kill"',
    ):
        if marker in lowered_body:
            return True
    return False


def _element_contains_control(lowered_body: str, element: str, control_terms: tuple[str, ...]) -> bool:
    start_token = f"<{element}"
    end_token = f"</{element}>"
    start = 0
    while True:
        index = lowered_body.find(start_token, start)
        if index == -1:
            return False
        end = lowered_body.find(end_token, index)
        snippet = lowered_body[index : end + len(end_token) if end != -1 else index + 500]
        if any(term in snippet for term in control_terms):
            return True
        start = index + len(start_token)


def _fetch_url(url: str, timeout: int) -> tuple[int, str]:
    request = Request(url, headers={"User-Agent": "TSF-preview-health/1.0"})
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read(500_000).decode("utf-8", errors="replace")
            return int(response.status), redact_auth_text(body)
    except URLError as exc:
        raise RuntimeError(redact_auth_text(str(exc))) from exc


def _timeout(env: Mapping[str, str] | None) -> int:
    if not env:
        return 300
    value = env.get("TSF_VERCEL_DEPLOY_TIMEOUT_SECONDS")
    if value in {None, ""}:
        return 300
    try:
        return int(str(value))
    except ValueError:
        return 300


def _audit_health(store: Store | None, result: DeploymentCheckResult, *, url: str) -> None:
    if store is None:
        return
    store.append_audit(
        actor_type="orchestrator",
        actor_id="deployment_health",
        action="deployment_health_check",
        target_type="deployment_preview",
        target_id=url,
        risk_level="low" if result.passed else "medium",
        summary=result.summary,
        metadata={"passed": result.passed, "output": result.output_redacted},
    )
