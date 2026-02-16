#!/usr/bin/env bash
# Minimal Claude CLI wrapper using Anthropic Messages API.
set -euo pipefail

MODEL="${GATEWAY_CLAUDE_MODEL:-claude-3-haiku}"
TEMP="0.2"
MAXTOK="256"

while [[ $# -gt 0 ]]; do
  case "$1" in
    -m) MODEL="$2"; shift 2;;
    -t) TEMP="$2"; shift 2;;
    -M) MAXTOK="$2"; shift 2;;
    *) shift;;
  esac
done

if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
  echo "Missing ANTHROPIC_API_KEY" >&2
  exit 1
fi

PROMPT="$(cat)"

PAYLOAD=$(cat <<JSON
{
  "model": "${MODEL}",
  "max_tokens": ${MAXTOK},
  "temperature": ${TEMP},
  "messages": [
    {"role": "user", "content": ${PROMPT@Q}}
  ]
}
JSON
)

RESP=$(curl -sS -X POST \
  -H "x-api-key: ${ANTHROPIC_API_KEY}" \
  -H "content-type: application/json" \
  -H "anthropic-version: 2023-06-01" \
  https://api.anthropic.com/v1/messages \
  -d "${PAYLOAD}")

echo "$RESP" | python3 - <<'PY'
import sys, json
data = json.loads(sys.stdin.read())
content = data.get('content') or []
out = ''
if isinstance(content, list) and content:
    for block in content:
        if isinstance(block, dict) and block.get('type') == 'text':
            out += block.get('text','')
            break
print(out.strip())
PY
