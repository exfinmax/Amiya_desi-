#!/bin/bash
set -euo pipefail

BASE_DIR="/mnt/d/scripts/daily_write/Amiya_desi-"
VENV_PY="$BASE_DIR/venv/bin/python"
HELPER="$BASE_DIR/scripts/daily_write/helper_fetch.py"
POSTER="$BASE_DIR/scripts/daily_write/post_resource_article.sh"

# Use env token if present
if [ -z "${GITHUB_TOKEN-}" ]; then
  if [ -f "/mnt/d/scripts/daily_write/.github_token" ]; then
    export GITHUB_TOKEN=$(cat /mnt/d/scripts/daily_write/.github_token)
  fi
fi

echo "[TEST] Running helper_fetch.py..."
$VENV_PY "$HELPER"

echo "[TEST] resources.json head:" 
python3 - <<PY
import json
p='$BASE_DIR/scripts/daily_write/resources.json'
try:
  data=json.load(open(p,'r',encoding='utf-8'))
  import itertools
  print(json.dumps(list(itertools.islice(data,6)),ensure_ascii=False,indent=2))
except Exception as e:
  print('Cannot read',p,e)
PY

echo "[TEST] Running poster in dry-run mode (IMMEDIATE=1)..."
export IMMEDIATE=1
export LOCKFILE_OVERRIDE="/tmp/post_resource_article_test.lock"
export FORCE_PUBLISH=1
bash "$POSTER" --dry-run

if [ -f "$BASE_DIR/scripts/daily_write/dry_run_payload.json" ]; then
  echo "[TEST] Dry-run payload saved to dry_run_payload.json (pretty):"
  python3 -m json.tool "$BASE_DIR/scripts/daily_write/dry_run_payload.json"
  echo "[TEST] Generating HTML preview..."
  python3 "$BASE_DIR/scripts/daily_write/generate_dry_preview.py"
  echo "[TEST] Preview generated at: $BASE_DIR/scripts/daily_write/dry_run_preview.html"
else
  echo "[WARN] dry_run_payload.json not found"
fi

echo "[TEST] Log tail:"
tail -n 80 "$BASE_DIR/scripts/daily_write/helper_fetch.log" || true

echo "[TEST] Done."