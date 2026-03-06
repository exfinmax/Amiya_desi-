#!/bin/bash
set -euo pipefail

BASE_DIR="/mnt/d/scripts/daily_write"
VENV_PY="$BASE_DIR/venv/bin/python"
HELPER="$BASE_DIR/helper_fetch.py"
POSTER="$BASE_DIR/post_resource_article.sh"
TOKEN_FILE="$BASE_DIR/.github_token"

if [ ! -f "$TOKEN_FILE" ]; then
  echo "[ERROR] token file not found: $TOKEN_FILE" >&2
  exit 1
fi

export GITHUB_TOKEN=$(cat "$TOKEN_FILE")

echo "[TEST] Running helper_fetch.py..."
$VENV_PY "$HELPER"

echo "[TEST] resources.json head:" 
jq '.[0:6]' "$BASE_DIR/resources.json" || head -n 40 "$BASE_DIR/resources.json"

echo "[TEST] Running poster in dry-run mode (IMMEDIATE=1)..."
export IMMEDIATE=1
export LOCKFILE_OVERRIDE="/tmp/post_resource_article_test.lock"
export FORCE_PUBLISH=1
bash "$POSTER" --dry-run

if [ -f "$BASE_DIR/dry_run_payload.json" ]; then
  echo "[TEST] Dry-run payload saved to dry_run_payload.json (pretty):"
  jq . "$BASE_DIR/dry_run_payload.json" || cat "$BASE_DIR/dry_run_payload.json"
else
  echo "[WARN] dry_run_payload.json not found"
fi

echo "[TEST] Log tail:"
tail -n 80 "$BASE_DIR/helper_fetch.log" || true

echo "[TEST] Done."