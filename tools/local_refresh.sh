#!/bin/bash
# 本地定时刷新：抓取官方信源 + 社区数据，重建看板，提交并推送 docs/。
#
# 背景：GitHub Actions 托管 runner 在海外，区教委与多数学校站拒境外流量
# （实测区在线 0/18），CI 上的定时全量抓取产出的看板大面积空缺。抓取
# 因此只在本地跑，CI（frontend-build.yml）只负责部署已提交的 docs/。
#
# 由 launchd 调度（com.k12-dashboard.local-refresh，见 tools/com.k12-dashboard.local-refresh.plist），
# 也可手动执行：tools/local_refresh.sh [--skip-forum]
#
# 质量护栏：区在线 <14/18 或学校 <100 时中止推送（大概率是本地网络或
# 站点侧故障），变更保留在工作区供人工检查。

set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
PY="$REPO/.venv/bin/python"
cd "$REPO"

SKIP_FORUM=0
[ "${1:-}" = "--skip-forum" ] && SKIP_FORUM=1

echo "=== $(date '+%F %T') local refresh start (skip_forum=$SKIP_FORUM) ==="

# --- 社区链路（等价于 CI 原来的 Community refresh 步骤，写入 community/data/）---
"$PY" community/tools/community_crawler.py \
  --output community/data/community_beijing.json
"$PY" community/tools/community_pipeline.py \
  --cap-input community/data/community_beijing.json \
  --cap-output community/data/community_beijing_capped.json
"$PY" community/tools/community_content_crawler.py \
  --input community/data/community_beijing_capped.json \
  --output community/data/community_beijing_content.jsonl
"$PY" community/tools/community_content_cleaner.py \
  --input community/data/community_beijing_content.jsonl \
  --output community/data/community_beijing_clean.jsonl \
  --json-output community/data/community_beijing_clean.json
"$PY" community/tools/community_content_enricher.py \
  --input community/data/community_beijing_clean.jsonl \
  --output community/data/community_beijing_enriched.jsonl \
  --json-output community/data/community_beijing_enriched.json

# --- 论坛增量采集（断点续采，仅新增帖子会抓详情；--retry-failed 补上被限流的）---
if [ "$SKIP_FORUM" = "0" ]; then
  "$PY" community/tools/community_forum_crawler.py \
    --retry-failed --max-pages 5 --max-threads 100 --delay 2.5 \
    --output community/data/community_forum_posts.jsonl
  "$PY" community/tools/community_forum_adapter.py
  "$PY" - <<'PYEOF'
import json
base = json.load(open("community/data/community_beijing_enriched.json", encoding="utf-8"))
forum = json.load(open("community/data/community_forum_enriched.json", encoding="utf-8"))
merged = base + forum
json.dump(merged, open("community/data/community_merged_enriched.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
print(f"merged: {len(base)} + {len(forum)} = {len(merged)}")
PYEOF
  MERGED_INPUT="community/data/community_merged_enriched.json"
else
  MERGED_INPUT="community/data/community_beijing_enriched.json"
fi

DETAIL_PAGES=$("$PY" -c 'import json; print(len(json.load(open("community/data/community_beijing_capped.json"))))')
"$PY" community/tools/community_pipeline.py \
  --input "$MERGED_INPUT" \
  --output docs/community-data.json \
  --status-output docs/community-status.json \
  --entry-pages 6 \
  --detail-pages-attempted "$DETAIL_PAGES"

# --- 官方信源全量抓取 + 页面渲染 ---
"$PY" tools/build.py

# --- 质量护栏：抓取大面积失败时不推送 ---
SUMMARY=$("$PY" - <<'PYEOF'
import re, json
data = json.load(open("docs/data.json", encoding="utf-8"))["data"]
districts_online = sum(1 for d in data["区级"].values() if d["政策"] or d["动态"])
schools = sum(len(d["学校"]) for d in data["区级"].values())
print(f"{districts_online} {schools}")
PYEOF
)
read -r DISTRICTS_ONLINE SCHOOLS <<< "$SUMMARY"
echo "guard: 区在线 ${DISTRICTS_ONLINE}/18, 学校 ${SCHOOLS} 所"
if [ "$DISTRICTS_ONLINE" -lt 14 ] || [ "$SCHOOLS" -lt 100 ]; then
  echo "guard FAILED: 抓取质量低于阈值，保留变更但不提交推送，请人工检查" >&2
  exit 1
fi

# --- 提交并推送（有变更才提交；docs 变更触发 frontend-build.yml 部署）---
if git diff --quiet -- docs community/data && \
   [ -z "$(git ls-files --others --exclude-standard docs community/data)" ]; then
  echo "no changes since last refresh"
else
  git add docs community/data
  git commit -m "chore: scheduled local refresh $(date '+%F %H:%M')

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
  git push origin main
  echo "pushed; frontend-build.yml will deploy to Pages"
fi

echo "=== $(date '+%F %T') local refresh done ==="
