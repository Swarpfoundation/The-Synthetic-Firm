"""Redaction helpers for provider auth output."""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

SECRET_KEYS = {
    "access_token",
    "refresh_token",
    "id_token",
    "token",
    "code",
    "authorization_code",
    "session",
    "cookie",
    "api_key",
    "apikey",
    "bearer",
    "client_secret",
    "device_secret",
}

SECRET_PATTERNS = (
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE),
    re.compile(r"sk-[A-Za-z0-9][A-Za-z0-9._-]{12,}"),
    re.compile(r"sk-kimi-[A-Za-z0-9._-]{12,}"),
    re.compile(r"(access_token|refresh_token|id_token|api_key|client_secret|cookie|session)\s*[:=]\s*['\"]?[^'\"\s]+", re.IGNORECASE),
)


def redact_auth_text(value: object) -> str:
    text = str(value or "")
    text = redact_url_if_sensitive(text)
    for pattern in SECRET_PATTERNS:
        text = pattern.sub(lambda match: _redact_assignment(match.group(0)), text)
    return text


def redact_url_if_sensitive(value: object) -> str:
    text = str(value or "")
    try:
        split = urlsplit(text)
    except ValueError:
        return text
    if not split.scheme or not split.netloc:
        return text
    query = parse_qsl(split.query, keep_blank_values=True)
    if not query:
        return text
    redacted = []
    sensitive = False
    for key, val in query:
        if key.lower() in SECRET_KEYS:
            redacted.append((key, "[redacted]"))
            sensitive = True
        else:
            redacted.append((key, val))
    if not sensitive:
        return text
    return urlunsplit((split.scheme, split.netloc, split.path, urlencode(redacted), split.fragment))


def is_safe_login_url(value: str | None) -> bool:
    if not value:
        return False
    text = str(value)
    if redact_url_if_sensitive(text) != text:
        return False
    try:
        split = urlsplit(text)
    except ValueError:
        return False
    return split.scheme in {"http", "https"} and bool(split.netloc)


def _redact_assignment(value: str) -> str:
    if value.lower().startswith("bearer "):
        return "Bearer [redacted]"
    if "=" in value:
        return value.split("=", 1)[0] + "=[redacted]"
    if ":" in value:
        return value.split(":", 1)[0] + ":[redacted]"
    return "[redacted]"
