#!/bin/bash
set -euo pipefail

# Windows-friendly local test script; runs entirely within current shell
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="${PYTHON:-python3}"
HELPER="$SCRIPT_DIR/helper_fetch.py"
POSTER="$SCRIPT_DIR/post_resource_article.sh"

# optionally load token from repository root
if [ -z "${GITHUB_TOKEN-}" ] && [ -f "$SCRIPT_DIR/../.github_token" ]; then
  export GITHUB_TOKEN=$(cat "$SCRIPT_DIR/../.github_token")
fi

echo "[TEST] Running helper_fetch.py..."
$PYTHON "$HELPER"

echo "[TEST] resources.json head:"
$PYTHON - <<'PY'
import json, itertools
p='$SCRIPT_DIR/resources.json'
try:
    data=json.load(open(p,'r',encoding='utf-8'))
    print(json.dumps(list(itertools.islice(data,6)),ensure_ascii=False,indent=2))
except Exception as e:
    print('Cannot read',p,e)
PY

echo "[TEST] Running poster in dry-run mode (IMMEDIATE=1)..."
export IMMEDIATE=1
export LOCKFILE_OVERRIDE="/tmp/post_resource_article_test.lock"
export FORCE_PUBLISH=1
# ensure history file exists for tests
HISTORY_FILE="$SCRIPT_DIR/posted_urls.txt"
[ -f "$HISTORY_FILE" ] || touch "$HISTORY_FILE"
bash "$POSTER" --dry-run

if [ -f "$SCRIPT_DIR/dry_run_payload.json" ]; then
  echo "[TEST] Dry-run payload saved to dry_run_payload.json (pretty):"
  $PYTHON -m json.tool "$SCRIPT_DIR/dry_run_payload.json"
  echo "[TEST] Generating HTML preview..."
  $PYTHON "$SCRIPT_DIR/generate_dry_preview.py"
  echo "[TEST] Preview generated at: $SCRIPT_DIR/dry_run_preview.html"
else
  echo "[WARN] dry_run_payload.json not found"
fi

echo "[TEST] Log tail:"
tail -n 80 "$SCRIPT_DIR/helper_fetch.log" || true

echo "[TEST] Done."
