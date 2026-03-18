#!/bin/bash
# post_resource_article.sh
# Orchestration only: select → render → post to GitHub Issues
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="$SCRIPT_DIR/article_post_log.txt"
RESOURCES_JSON="$SCRIPT_DIR/resources.json"
FALLBACK_JSON="$SCRIPT_DIR/fallback_resources.json"
SELECTED_JSON="$SCRIPT_DIR/daily_selected.json"

mkdir -p "$SCRIPT_DIR/state"
: > "$LOG_FILE"

# ── 锁 ────────────────────────────────────────────────────────────────────────
LOCKFILE="${LOCKFILE_OVERRIDE:-/tmp/post_resource_article.lock}"
exec 200>"$LOCKFILE"
flock -n 200 || { echo "[ERROR] 锁已存在，退出。" | tee -a "$LOG_FILE"; exit 1; }
trap 'flock -u 200' EXIT

current_date=$(date +"%Y-%m-%d")

# ── 防重复发布 ────────────────────────────────────────────────────────────────
if [ -z "${FORCE_PUBLISH-}" ] && grep -q "$current_date" "$LOG_FILE" 2>/dev/null; then
  echo "[INFO] 今日已发布，退出。" | tee -a "$LOG_FILE"
  exit 0
fi

echo "[INFO] 开始 $(date)" | tee -a "$LOG_FILE"

# ── 等待 resources.json ───────────────────────────────────────────────────────
if [ "${IMMEDIATE-0}" != "1" ]; then
  for i in $(seq 1 12); do
    [ -s "$RESOURCES_JSON" ] && break
    echo "[INFO] 等待 resources.json... ($i/12)" | tee -a "$LOG_FILE"
    sleep 5
  done
fi

# ── Python 命令 ───────────────────────────────────────────────────────────────
PY=python3
command -v python3 >/dev/null 2>&1 || PY=python

# ── 选择资源 ──────────────────────────────────────────────────────────────────
DRY_FLAG=""
[ "${DRY_RUN-0}" = "1" ] || [ "${1-}" = "--dry-run" ] && DRY_FLAG="--dry-run"

echo "[INFO] 运行 select_resources.py" | tee -a "$LOG_FILE"
$PY "$SCRIPT_DIR/select_resources.py" \
  --resources "$RESOURCES_JSON" \
  --fallback "$FALLBACK_JSON" \
  --output "$SELECTED_JSON" \
  --top-n 5 \
  $DRY_FLAG >> "$LOG_FILE" 2>&1 || true

# ── 渲染正文 ──────────────────────────────────────────────────────────────────
echo "[INFO] 运行 render_daily_post.py" | tee -a "$LOG_FILE"
ARTICLE_CONTENT=$($PY "$SCRIPT_DIR/render_daily_post.py" --date "$current_date" $DRY_FLAG 2>>"$LOG_FILE" || echo "今日资源推荐内容生成失败，请稍后查看。")

ARTICLE_TITLE="[Update] 今日免费资源推荐 - $current_date"
TAG_LABEL="免费资源"

# ── 构建 payload ──────────────────────────────────────────────────────────────
if command -v jq >/dev/null 2>&1; then
  payload=$(jq -n \
    --arg t "$ARTICLE_TITLE" \
    --arg b "$ARTICLE_CONTENT" \
    --arg tag "$TAG_LABEL" \
    '{title: $t, body: $b, labels: [$tag, "构建成功", "made by ai"]}')
else
  payload=$($PY -c "
import json, sys
obj = {'title': sys.argv[1], 'body': sys.argv[2], 'labels': [sys.argv[3], '构建成功', 'made by ai']}
print(json.dumps(obj, ensure_ascii=False))
" "$ARTICLE_TITLE" "$ARTICLE_CONTENT" "$TAG_LABEL")
fi

printf '%s' "$payload" > "$SCRIPT_DIR/dry_run_payload.json" || true

# ── 发布 ──────────────────────────────────────────────────────────────────────
if [ -n "${GITHUB_REPOSITORY-}" ]; then
  POST_URL="https://api.github.com/repos/${GITHUB_REPOSITORY}/issues"
else
  POST_URL="https://api.github.com/repos/exfinmax/Amiya_desi-/issues"
fi

IS_DRY=0
{ [ "${DRY_RUN-0}" = "1" ] || [ "${1-}" = "--dry-run" ]; } && IS_DRY=1

if [ "$IS_DRY" -eq 1 ]; then
  echo "[DRY RUN] payload 已写入 dry_run_payload.json" | tee -a "$LOG_FILE"
  echo "$current_date - DRYRUN" >> "$LOG_FILE"
else
  http_status=$(curl -s -o /tmp/gh_response.txt -w "%{http_code}" \
    -X POST \
    -H "Authorization: token ${GITHUB_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "$payload" \
    "$POST_URL" || echo "000")

  [ -f /tmp/gh_response.txt ] && head -c 4000 /tmp/gh_response.txt >> "$LOG_FILE"

  if [ "$http_status" -ge 200 ] && [ "$http_status" -lt 300 ]; then
    echo "[INFO] 发布成功 HTTP $http_status" | tee -a "$LOG_FILE"
    echo "$current_date - SUCCESS" >> "$LOG_FILE"

    # 标记 registry 为已发送
    $PY - <<'PYEOF' 2>>"$LOG_FILE" || true
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath('.')))
script_dir = os.path.dirname(os.path.abspath(__file__)) if '__file__' in dir() else '.'
import json
from datetime import datetime

selected_path = os.path.join(script_dir, 'daily_selected.json')
if not os.path.exists(selected_path):
    sys.exit(0)
with open(selected_path) as f:
    selected = json.load(f)

try:
    sys.path.insert(0, script_dir)
    from resource_registry import ResourceRegistry, STATUS_SENT
    reg = ResourceRegistry()
    today = datetime.now().strftime('%Y-%m-%d')
    for it in selected:
        url = it.get('url', '')
        if url:
            reg.mark_sent(url, today)
    reg.save()
    print('[Registry] 已标记为 sent')
except Exception as e:
    print(f'[Registry] 标记失败（非致命）: {e}')
PYEOF

  else
    echo "[ERROR] 发布失败 HTTP $http_status" | tee -a "$LOG_FILE"
    exit 1
  fi
fi

echo "[INFO] 完成 $(date)" | tee -a "$LOG_FILE"
exit 0
