"""Database credential redaction helpers for TSF persistence setup."""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


SECRET_QUERY_KEYS = frozenset({"password", "pass", "token", "secret", "sslcert", "sslkey"})


def redact_database_url(value: str | None) -> str:
    """Return a safe database URL summary without username/password/host details."""

    text = str(value or "").strip()
    if not text:
        return ""
    try:
        parsed = urlsplit(text)
    except ValueError:
        return "[redacted-database-url]"
    if not parsed.scheme:
        return "[redacted-database-url]"
    redacted_netloc = ""
    if parsed.hostname:
        redacted_netloc = "[redacted-host]"
        if parsed.port:
            redacted_netloc += f":{parsed.port}"
    query_items = []
    for key, item_value in parse_qsl(parsed.query, keep_blank_values=True):
        if key.lower() in SECRET_QUERY_KEYS:
            query_items.append((key, "[redacted]"))
        else:
            query_items.append((key, item_value))
    safe_query = urlencode(query_items)
    return urlunsplit((parsed.scheme, redacted_netloc, parsed.path or "/[redacted-db]", safe_query, ""))


def redact_db_text(value: str | None) -> str:
    """Redact database URLs and common credential fragments in text."""

    text = str(value or "")
    text = re.sub(r"postgres(?:ql)?://\S+", "[redacted-database-url]", text, flags=re.IGNORECASE)
    text = re.sub(r"(DATABASE_URL|TSF_DATABASE_URL)\s*=\s*\S+", r"\1=[redacted]", text, flags=re.IGNORECASE)
    text = re.sub(r"(password|passwd|pwd)\s*=\s*[^,\s]+", r"\1=[redacted]", text, flags=re.IGNORECASE)
    return text
