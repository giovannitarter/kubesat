#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 || ! "$1" =~ ^[0-9a-f]{40}$ ]]; then
  echo "Usage: $0 <40-character-lowercase-git-commit-sha>" >&2
  exit 2
fi

SHA="$1"
URL="https://hooklet.ksat.pupillo.org/webhook"

SECRET="$(kubectl -n hooklet get secret hooklet \
  -o jsonpath='{.data.GITHUB_WEBHOOK_SECRET}' | base64 -d)"

PAYLOAD="$(jq -cn \
  --arg sha "$SHA" \
  '{repository:{full_name:"giovannitarter/sat_sentieri"},
    ref:"refs/heads/main",
    after:$sha,
    deleted:false}')"

SIGNATURE="sha256=$(printf '%s' "$PAYLOAD" |
  openssl dgst -sha256 -hmac "$SECRET" -hex |
  awk '{print $NF}')"

curl --fail-with-body \
  -X POST "$URL" \
  -H 'Content-Type: application/json' \
  -H 'X-GitHub-Event: push' \
  -H "X-Hub-Signature-256: $SIGNATURE" \
  --data-binary "$PAYLOAD"

echo
