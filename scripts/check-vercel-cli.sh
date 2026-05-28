#!/usr/bin/env bash
set -euo pipefail

vercel_bin="${TSF_VERCEL_PROJECT_PATH:-apps/control-room}/node_modules/.bin/vercel"
if [[ -x "$vercel_bin" ]]; then
  :
elif command -v vercel >/dev/null 2>&1; then
  vercel_bin="$(command -v vercel)"
else
  printf '{"provider":"vercel","cli_available":false,"summary":"Vercel CLI is unavailable."}\n'
  exit 1
fi

version="$("$vercel_bin" --version 2>/dev/null | head -n 1 | sed -E 's/(token|secret|password|api[_-]?key)[^[:space:]]*/[redacted]/Ig')"
printf '{"provider":"vercel","cli_available":true,"version":"%s","summary":"Vercel CLI is available."}\n' "$version"
