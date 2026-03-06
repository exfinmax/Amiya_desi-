#!/bin/bash
set -euo pipefail

# 文件位置说明
# 脚本路径: /mnt/d/scripts/daily_write/post_resource_article.sh
# 资源文件(可选): /mnt/d/scripts/daily_write/resources.json
# 日志文件: /mnt/d/scripts/daily_write/article_post_log.txt

# Determine script directory (works in CI and local)
SCRIPT_DIR="${SCRIPT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)}"
LOG_FILE="$SCRIPT_DIR/article_post_log.txt"
RESOURCES_JSON="$SCRIPT_DIR/resources.json"

# Ensure script directory and log file exist
mkdir -p "$SCRIPT_DIR"
: > "$LOG_FILE"

# 支持通过环境变量覆盖锁文件（便于测试）
LOCKFILE="${LOCKFILE_OVERRIDE:-/tmp/post_resource_article.lock}"
exec 200>"$LOCKFILE"
flock -n 200 || {
  echo "[ERROR] 另一个实例正在运行，退出。" | tee -a "$LOG_FILE"
  exit 1
}

# 触发时间范围（9:00-18:00）
random_hour=$(shuf -i 9-18 -n 1)
random_minute=$(shuf -i 0-59 -n 1)
trigger_time=$(printf "%02d:%02d" "$random_hour" "$random_minute")

current_date=$(date +"%Y-%m-%d")

# 检查当天是否已发布（可通过环境变量 FORCE_PUBLISH=1 强制跳过）
if [ -z "${FORCE_PUBLISH-}" ]; then
  if [ -f "$LOG_FILE" ] && grep -q "$current_date" "$LOG_FILE"; then
    echo "[INFO] $current_date 已发布，退出。" | tee -a "$LOG_FILE"
    exit 0
  fi
else
  echo "[INFO] FORCE_PUBLISH=1，跳过当天已发布检查。" | tee -a "$LOG_FILE"
fi

echo "[INFO] 脚本启动：$(date '+%Y-%m-%d %H:%M:%S')，计划触发时间：$trigger_time" | tee -a "$LOG_FILE"

# 等待触发时间（可通过环境变量 IMMEDIATE=1 跳过，用于测试）
if [ "${IMMEDIATE-0}" = "1" ]; then
  echo "[INFO] IMMEDIATE=1，跳过等待，立即执行。" | tee -a "$LOG_FILE"
else
  while true; do
    now=$(date +"%H:%M")
    if [ "$now" = "$trigger_time" ]; then
      break
    fi
    sleep 15
  done
fi

# 选择资源并生成文章内容
ARTICLE_TITLE="[Update] 今日免费资源推荐 - $current_date"
ARTICLE_CONTENT="#### 资源推荐\n\n"

# 使用 python 选择 3-5 条资源，scp 项目 0-2 条；等待 resources.json 可用（最多 60s）
WAIT_SECONDS=60
SLEEPT=5
elapsed=0
while [ $elapsed -lt $WAIT_SECONDS ]; do
  if [ -f "$RESOURCES_JSON" ] && [ -s "$RESOURCES_JSON" ]; then
    break
  fi
  echo "[INFO] waiting for resources.json to be written... ($elapsed/$WAIT_SECONDS)" | tee -a "$LOG_FILE"
  sleep $SLEEPT
  elapsed=$((elapsed+SLEEPT))
done

if [ ! -f "$RESOURCES_JSON" ] || [ ! -s "$RESOURCES_JSON" ]; then
  echo "[WARN] resources.json not available after wait, will use placeholder." | tee -a "$LOG_FILE"
  ARTICLE_CONTENT+="- **资源名称：** 待填充\n- **资源简介：** 这是一段自动生成的文章，你可以替换为真实内容。\n- **获取：** https://example.com\n\n"
else
  if ! command -v python3 >/dev/null 2>&1; then
    echo "[ERROR] 需要 python3 来选择资源，请安装后重试。" | tee -a "$LOG_FILE"
    exit 1
  fi
  mapfile -t picks < <(python3 "$RESOURCES_JSON" <<'PY'
import json,random,sys
path=sys.argv[1]
with open(path,'r',encoding='utf-8') as f:
    items=json.load(f)
if not items:
    sys.exit(0)
scp=[i for i in items if ('tags' in i and 'scp' in i.get('tags',[])) or ('scp' in (i.get('source') or ''))]
other=[i for i in items if i not in scp]
# total 3-5
total=random.randint(3,5)
# scp count 0-2
scp_count=min(len(scp), random.randint(0,2))
scp_selected=random.sample(scp, scp_count) if scp_count>0 else []
other_count=total - len(scp_selected)
other_selected=random.sample(other, min(other_count, len(other))) if other_count>0 and other else []
selected = scp_selected + other_selected
remaining=[i for i in items if i not in selected]
with open(path,'w',encoding='utf-8') as f:
    json.dump(remaining, f, ensure_ascii=False, indent=2)
for it in selected:
    title=it.get('title','')
    desc=it.get('description','')
    url=it.get('url','')
    tags=','.join(it.get('tags',[])) if it.get('tags') else ''
    print('@@'.join([title.replace('@@',' '), desc.replace('@@',' '), url, tags]))
PY
)
  if [ ${#picks[@]} -eq 0 ]; then
    echo "[WARN] resources.json 没有可用条目，使用占位内容。" | tee -a "$LOG_FILE"
    ARTICLE_CONTENT+="- **资源名称：** 待填充\n- **资源简介：** 这是一段自动生成的文章，你可以替换为真实内容。\n- **获取：** https://example.com\n\n"
  else
    echo "[INFO] 选中 ${#picks[@]} 条资源发布：" | tee -a "$LOG_FILE"
    for line in "${picks[@]}"; do
      IFS='@@' read -r title desc url tags <<< "$line"
      ARTICLE_CONTENT+="- **资源名称：** ${title:-未命名资源}\n"
      ARTICLE_CONTENT+="  - 简介： ${desc:-无简介}\n"
      ARTICLE_CONTENT+="  - 获取： ${url:-#}\n\n"
      if [ -n "$tags" ] && echo "$tags" | grep -q "scp"; then
        ARTICLE_CONTENT+="  - 标签：SCP 基金会  \n\n"
      fi
    done
  fi
fi

ARTICLE_CONTENT+="> 更多实用资源，敬请关注！\n\n---\n\nTrigger: 自动构建"
TAG_LABEL="免费资源"

# 准备提交到 GitHub Issues
GITHUB_API_URL="https://api.github.com/repos/exfinmax/Amiya_desi-/issues"
if [ -z "${GITHUB_TOKEN-}" ]; then
  echo "[ERROR] 环境变量 GITHUB_TOKEN 未设置，无法提交。" | tee -a "$LOG_FILE"
  exit 1
fi

# 处理 dry-run 参数（或环境变量 DRY_RUN=1）
if [ "${1-}" = "--dry-run" ]; then
  DRY_RUN=1
else
  DRY_RUN=${DRY_RUN-0}
fi

# 执行提交
if command -v jq >/dev/null 2>&1; then
  payload=$(jq -n --arg t "$ARTICLE_TITLE" --arg b "$ARTICLE_CONTENT" --argjson labels "[\"$TAG_LABEL\", \"构建成功\", \"made by ai\"]" '{title: $t, body: $b, labels: $labels}')
else
  # fallback to python to build JSON payload
  if command -v python3 >/dev/null 2>&1; then
    payload=$(python3 - <<PY
import json,sys
obj={'title': '''$ARTICLE_TITLE''', 'body': '''$ARTICLE_CONTENT''', 'labels': ["$TAG_LABEL", "构建成功", "made by ai"]}
print(json.dumps(obj))
PY
)
  else
    echo "[ERROR] 既没有 jq 也没有 python3，无法构建 payload。" | tee -a "$LOG_FILE"
    exit 1
  fi
fi

if [ "$DRY_RUN" -eq 1 ] 2>/dev/null; then
  echo "[DRY RUN] Payload to be submitted:" | tee -a "$LOG_FILE"
  if command -v jq >/dev/null 2>&1; then
    echo "$payload" | jq . | tee "$SCRIPT_DIR/dry_run_payload.json" | tee -a "$LOG_FILE"
  else
    # fallback: write raw payload
    echo "$payload" > "$SCRIPT_DIR/dry_run_payload.json"
    echo "[WARN] jq 未安装，已将原始 payload 写入 $SCRIPT_DIR/dry_run_payload.json" | tee -a "$LOG_FILE"
  fi
  echo "[DRY RUN] Skipping actual GitHub API call." | tee -a "$LOG_FILE"
  echo "$current_date - DRYRUN" >> "$LOG_FILE"
else
  echo "[INFO] 正在提交到 GitHub..." | tee -a "$LOG_FILE"
  http_status=$(curl -s -o /tmp/gh_response.txt -w "%{http_code}" -X POST -H "Authorization: token ${GITHUB_TOKEN}" -H "Content-Type: application/json" -d "$payload" "$GITHUB_API_URL")

  if [ "$http_status" -ge 200 ] && [ "$http_status" -lt 300 ]; then
    echo "[INFO] 提交成功，HTTP $http_status" | tee -a "$LOG_FILE"
    echo "$current_date - SUCCESS - HTTP $http_status" >> "$LOG_FILE"
  else
    echo "[ERROR] 提交失败，HTTP $http_status" | tee -a "$LOG_FILE"
    echo "$current_date - FAIL - HTTP $http_status" >> "$LOG_FILE"
    echo "Response:" >> "$LOG_FILE"
    cat /tmp/gh_response.txt >> "$LOG_FILE"
    exit 1
  fi
fi

# 释放锁并退出
flock -u 200
exit 0
