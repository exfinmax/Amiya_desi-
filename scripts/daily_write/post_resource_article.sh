#!/bin/bash
set -euo pipefail

# Simplified poster script

# determine script location
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
LOG_FILE="$SCRIPT_DIR/article_post_log.txt"
RESOURCES_JSON="$SCRIPT_DIR/resources.json"
FALLBACK_JSON="$SCRIPT_DIR/fallback_resources.json"

mkdir -p "$SCRIPT_DIR"
: > "$LOG_FILE"

# locking
LOCKFILE="${LOCKFILE_OVERRIDE:-/tmp/post_resource_article.lock}"
exec 200>"$LOCKFILE"
flock -n 200 || { echo "[ERROR] Lock exists, exiting." | tee -a "$LOG_FILE"; exit 1; }
trap 'flock -u 200' EXIT

# random trigger (not critical for local test)
random_hour=$(shuf -i 9-18 -n 1)
random_minute=$(shuf -i 0-59 -n 1)
trigger_time=$(printf "%02d:%02d" "$random_hour" "$random_minute")
current_date=$(date +"%Y-%m-%d")

if [ -z "${FORCE_PUBLISH-}" ] && [ -f "$LOG_FILE" ] && grep -q "$current_date" "$LOG_FILE"; then
  echo "[INFO] Already posted today, exiting." | tee -a "$LOG_FILE"
  exit 0
fi

echo "[INFO] Started at $(date), trigger time $trigger_time" | tee -a "$LOG_FILE"

if [ "${IMMEDIATE-0}" != "1" ]; then
  while true; do
    now=$(date +"%H:%M")
    [ "$now" = "$trigger_time" ] && break
    sleep 15
  done
else
  echo "[INFO] IMMEDIATE mode, skipping wait" | tee -a "$LOG_FILE"
fi

ARTICLE_TITLE="[Update] 今日免费资源推荐 - $current_date"
# start with actual newlines via $'...'
ARTICLE_CONTENT=$'#### 资源推荐\n\n'

# wait for resources.json
WAIT_SECONDS=60
SLEEPT=5
elapsed=0
while [ $elapsed -lt $WAIT_SECONDS ]; do
  if [ -f "$RESOURCES_JSON" ] && [ -s "$RESOURCES_JSON" ]; then break; fi
  sleep $SLEEPT
  elapsed=$((elapsed+SLEEPT))
done

HISTORY_FILE="$SCRIPT_DIR/posted_urls.txt"
[ -f "$HISTORY_FILE" ] || touch "$HISTORY_FILE"

# select resources
PICK_TEMP=$(mktemp)
if command -v python3 >/dev/null 2>&1; then
  python3 "$SCRIPT_DIR/select_resources.py" "$RESOURCES_JSON" "$HISTORY_FILE" "$FALLBACK_JSON" > "$PICK_TEMP" 2>/dev/null || true
fi
mapfile -t picks < "$PICK_TEMP" || picks=()
rm -f "$PICK_TEMP"

if [ ${#picks[@]} -eq 0 ]; then
  ARTICLE_CONTENT+=$'- **资源名称：** 待填充\n  - **资源简介：** 占位内容\n  - **获取：** https://example.com\n\n'
else
  for line in "${picks[@]}"; do
    IFS='@@' read -r title desc url tags <<< "$line"
    ARTICLE_CONTENT+=$"- **资源名称：** ${title:-未命名资源}\n"
    ARTICLE_CONTENT+=$"  - 简介： ${desc:-无简介}\n"
    ARTICLE_CONTENT+=$"  - 获取： ${url:-#}\n\n"
    if echo "$tags" | grep -q "scp"; then
      ARTICLE_CONTENT+=$"  - 标签：SCP 基金会\n\n"
    fi
  done
fi
ARTICLE_CONTENT+="> 更多实用资源，敬请关注！\n\n---\n\nTrigger: 自动构建"
TAG_LABEL="免费资源"

# determine issue-posting URL (avoid using GITHUB_API_URL which is just the base)
if [ -n "${GITHUB_REPOSITORY-}" ]; then
  POST_URL="https://api.github.com/repos/${GITHUB_REPOSITORY}/issues"
else
  # fallback hardcoded repo
  POST_URL="https://api.github.com/repos/exfinmax/Amiya_desi-/issues"
fi

echo "[DEBUG] POST_URL=$POST_URL" | tee -a "$LOG_FILE"

DRY_RUN=0
[ "${1-}" = "--dry-run" ] && DRY_RUN=1

# build payload
if command -v jq >/dev/null 2>&1; then
  payload=$(jq -n --arg t "$ARTICLE_TITLE" --arg b "$ARTICLE_CONTENT" --arg tag "$TAG_LABEL" '{title: $t, body: $b, labels: [$tag, "构建成功", "made by ai"]}')
elif command -v python3 >/dev/null 2>&1; then
  payload=$(python3 -c "import json,sys; obj={'title':sys.argv[1],'body':sys.argv[2],'labels':[sys.argv[3],'构建成功','made by ai']}; print(json.dumps(obj))" "$ARTICLE_TITLE" "$ARTICLE_CONTENT" "$TAG_LABEL")
else
  echo "[ERROR] Need jq or python3" | tee -a "$LOG_FILE"
  exit 1
fi

printf '%s' "$payload" > "$SCRIPT_DIR/dry_run_payload.json" || true

echo "[DEBUG] GITHUB_REPOSITORY=$GITHUB_REPOSITORY" | tee -a "$LOG_FILE"
echo "[DEBUG] POST_URL=$POST_URL" | tee -a "$LOG_FILE"
echo "[DEBUG] payload preview:" | tee -a "$LOG_FILE"
echo "$payload" | head -c 4000 | tee -a "$LOG_FILE"

if [ "$DRY_RUN" -eq 1 ]; then
  echo "[DRY RUN]" | tee -a "$LOG_FILE"
  echo "$current_date - DRYRUN" >> "$LOG_FILE"
else
  http_status=$(curl -s -o /tmp/gh_response.txt -w "%{http_code}" -X POST -H "Authorization: token ${GITHUB_TOKEN}" -H "Content-Type: application/json" -d "$payload" "$POST_URL" || true)
  if [ -f /tmp/gh_response.txt ]; then
    head -c 4000 /tmp/gh_response.txt >> "$LOG_FILE"
  fi
  if [ "$http_status" -ge 200 ] && [ "$http_status" -lt 300 ]; then
    echo "[INFO] success (HTTP $http_status)" | tee -a "$LOG_FILE"
    echo "$current_date - SUCCESS" >> "$LOG_FILE"
  else
    echo "[ERROR] post failed (HTTP $http_status)" | tee -a "$LOG_FILE"
    if [ -f /tmp/gh_response.txt ]; then
      echo "[ERROR] response body:" | tee -a "$LOG_FILE"
      head -n 50 /tmp/gh_response.txt | tee -a "$LOG_FILE"
    fi
    exit 1
  fi
fi

echo "[INFO] done" | tee -a "$LOG_FILE"
exit 0
