#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

paths=(
  README.md
  agents
  synthetic_firm
  tests/synthetic_firm
  docs/the-synthetic-firm-foundation.md
  docs/the-synthetic-firm-workday-os.md
  docs/the-synthetic-firm-runtime.md
  docs/the-synthetic-firm-approval-runtime.md
  docs/the-synthetic-firm-audit-boundary.md
  docs/the-synthetic-firm-telegram-control-room.md
  docs/the-synthetic-firm-execution-queue.md
  docs/the-synthetic-firm-operator-runbook.md
  docs/the-synthetic-firm-provider-auth.md
  docs/the-synthetic-firm-model-routes.md
  docs/the-synthetic-firm-provider-runtime.md
  docs/the-synthetic-firm-control-room-frontend.md
  apps/control-room/src
  apps/control-room/docs
  apps/control-room/public
  apps/control-room/package.json
  apps/control-room/README.md
  package.json
  package-lock.json
)

tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT

echo "Brand identity guard scanning TSF product surfaces."
echo "Allowlisted legal attribution paths skipped:"
echo "- LICENSE"
echo "- LICENSE.*"
echo "- THIRD_PARTY_NOTICES.md"
echo "- NOTICE.md"
echo "- docs/legal/**"
echo "- pyproject.toml compatibility entry points"
echo "- scripts/check-brand-identity.sh internal pattern definition"
echo "Retained upstream compatibility/source archive paths are outside this product-surface guard."

for path in "${paths[@]}"; do
  if [ -e "$path" ]; then
    find "$path" \
      -path '*/__pycache__' -prune -o \
      -name '*.pyc' -prune -o \
      -type f -print
  fi
done > "$tmp"

if [ ! -s "$tmp" ]; then
  echo "No product identity files found to scan." >&2
  exit 1
fi

pattern='Hermes Agent|Hermes-style|on top of Hermes|Hermes|hermes|HERMES_'
if xargs grep -nE "$pattern" < "$tmp"; then
  echo "Brand identity check failed: upstream product branding appears in TSF product surfaces." >&2
  exit 1
fi

echo "Brand identity check passed."
