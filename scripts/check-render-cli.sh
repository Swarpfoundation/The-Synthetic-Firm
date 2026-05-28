#!/usr/bin/env bash
set -euo pipefail

if ! command -v render >/dev/null 2>&1; then
  printf '{"provider":"render","cli_available":false,"summary":"Render CLI is unavailable."}\n'
  exit 1
fi

version="$(render --version 2>/dev/null | head -n 1 | sed -E 's/(token|secret|password|api[_-]?key)[^[:space:]]*/[redacted]/Ig')"
printf '{"provider":"render","cli_available":true,"version":"%s","summary":"Render CLI is available."}\n' "$version"
