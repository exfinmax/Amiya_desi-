#!/usr/bin/env python3
"""
select_resources.py
资源过滤 → 去重 → 评分 → Top N 选择 → AI 摘要 → 输出 daily_selected.json

用法：
    python select_resources.py [--resources resources.json]
                               [--fallback fallback_resources.json]
                               [--output daily_selected.json]
                               [--top-n 5]
                               [--dry-run]

输出：
    daily_selected.json  结构化 JSON，字段：
        title, url, source, tags, score, summary, reason, audience, keywords
    同时向 stdout 打印 @@ 格式兼容行（供 shell 脚本读取）
"""

import os
import sys
import json
import random
import logging
import argparse
from datetime import datetime, timezone

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(sys.stderr),
    ],
)
logger = logging.getLogger(__name__)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_RESOURCES = os.path.join(SCRIPT_DIR, "resources.json")
DEFAULT_FALLBACK = os.path.join(SCRIPT_DIR, "fallback_resources.json")
DEFAULT_OUTPUT = os.path.join(SCRIPT_DIR, "daily_selected.json")
HISTORY_PATH = os.path.join(SCRIPT_DIR, "posted_urls.txt")

# 优先主题标签（这些来源的资源在同等分数下优先）
PRIORITY_TAGS = {"ai", "python", "rust", "go", "devops", "cli", "open-source"}
# SCP 彩蛋概率
SCP_EASTER_PROB = 0.001


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: str) -> list:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_json(path: str, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _load_history() -> set:
    """兼容旧 posted_urls.txt。"""
    if os.path.exists(HISTORY_PATH):
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            return {l.strip() for l in f if l.strip()}
    return set()


def _append_history(urls: list):
    with open(HISTORY_PATH, "a", encoding="utf-8") as f:
        for u in urls:
            f.write(u + "\n")


# ── 评分 ──────────────────────────────────────────────────────────────────────

def _score(item: dict) -> float:
    """
    综合评分，维度：
    - 来源质量（github > rss > fallback）
    - GitHub stars
    - description 完整度
    - 标题信息量
    - 是否优先主题
    - 发布时间新鲜度（近 7 天加分）
    - 少量随机扰动（避免榜单固化）
    """
    base = float(item.get("score", 0))
    source = (item.get("source") or "").lower()

    # 来源权重
    if "github" in source:
        base += 15
    elif "rss" in source:
        base += 8
    elif source == "fallback":
        base -= 5

    # GitHub stars
    stars = item.get("stars", 0) or 0
    if stars > 100000:
        base += 20
    elif stars > 50000:
        base += 15
    elif stars > 10000:
        base += 8
    elif stars > 1000:
        base += 3

    # description 完整度
    desc = item.get("description") or ""
    if len(desc) > 80:
        base += 5
    elif len(desc) > 30:
        base += 2

    # 标题信息量（长度适中加分）
    title = item.get("title") or ""
    if 10 <= len(title) <= 60:
        base += 3

    # 优先主题
    tags = set(item.get("tags") or [])
    if tags & PRIORITY_TAGS:
        base += 5

    # 发布时间新鲜度
    published = item.get("published") or item.get("fetched_at") or ""
    if published:
        try:
            from datetime import timedelta
            pub_dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
            age_days = (datetime.now(timezone.utc) - pub_dt).days
            if age_days <= 1:
                base += 10
            elif age_days <= 3:
                base += 6
            elif age_days <= 7:
                base += 3
        except Exception:
            pass

    # 随机扰动 ±3，避免每天完全固定榜单
    base += random.uniform(-3, 3)

    return round(base, 2)


# ── 去重 ──────────────────────────────────────────────────────────────────────

def _deduplicate(items: list, registry=None) -> list:
    """
    三层去重：
    1. 本次批次内 URL 去重
    2. 对比 registry 已发送记录
    3. 标题相似度去重（批次内）
    """
    try:
        from normalize_utils import normalize_url, title_similarity
    except ImportError:
        logger.warning("[Select] normalize_utils 不可用，跳过高级去重。")
        seen_urls = set()
        result = []
        for it in items:
            u = it.get("url", "")
            if u and u not in seen_urls:
                seen_urls.add(u)
                result.append(it)
        return result

    seen_norm_urls = set()
    seen_titles = []
    result = []

    for it in items:
        url = it.get("url", "")
        norm = normalize_url(url)
        title = it.get("title", "")

        # 层 1：批次内 URL 去重
        if norm and norm in seen_norm_urls:
            logger.debug(f"[Dedup] 批次内 URL 重复跳过: {url[:60]}")
            continue

        # 层 2：registry 已发送
        if registry:
            is_dup, reason = registry.is_duplicate(it)
            if is_dup:
                logger.info(f"[Dedup] registry 去重: {reason}")
                continue

        # 层 3：批次内标题相似度
        if title and any(title_similarity(title, t) >= 0.6 for t in seen_titles):
            logger.debug(f"[Dedup] 批次内标题相似跳过: {title[:40]}")
            continue

        seen_norm_urls.add(norm)
        if title:
            seen_titles.append(title)
        result.append(it)

    return result


# ── 主题多样性控制 ────────────────────────────────────────────────────────────

def _diversify(items: list, top_n: int) -> list:
    """
    在 Top N 中保证主题多样性：
    - 同一 source 类型最多占 60%
    - SCP 条目按概率控制
    """
    scp = [i for i in items if "scp" in (i.get("tags") or []) or "scp" in (i.get("source") or "").lower()]
    normal = [i for i in items if i not in scp]

    # SCP 彩蛋
    if random.random() < SCP_EASTER_PROB and scp:
        selected = random.sample(scp, min(len(scp), top_n))
        for it in selected:
            it.setdefault("tags", [])
            if "easter" not in it["tags"]:
                it["tags"].append("easter")
        return selected

    # 正常选择：SCP 0~1 条
    r = random.random()
    scp_count = 1 if r > 0.6 and scp else 0
    scp_selected = random.sample(scp, scp_count) if scp_count else []
    normal_count = top_n - len(scp_selected)

    # 来源多样性：同 source 最多 ceil(top_n * 0.6) 条
    max_per_source = max(1, int(top_n * 0.6))
    source_counts: dict = {}
    normal_selected = []
    for it in normal:
        src = (it.get("source") or "unknown").split(":")[0]
        if source_counts.get(src, 0) >= max_per_source:
            continue
        source_counts[src] = source_counts.get(src, 0) + 1
        normal_selected.append(it)
        if len(normal_selected) >= normal_count:
            break

    return scp_selected + normal_selected


# ── 主流程 ────────────────────────────────────────────────────────────────────

def select(resources_path: str = DEFAULT_RESOURCES,
           fallback_path: str = DEFAULT_FALLBACK,
           output_path: str = DEFAULT_OUTPUT,
           top_n: int = 5,
           dry_run: bool = False) -> list:
    """
    完整选择流程，返回最终选中的资源列表。
    """
    # 加载 registry
    registry = None
    try:
        from resource_registry import ResourceRegistry
        registry = ResourceRegistry()
    except Exception as e:
        logger.warning(f"[Select] registry 加载失败，降级为 posted_urls.txt: {e}")

    history = _load_history()

    # 加载资源
    items = []
    for path in [resources_path, fallback_path]:
        if path and os.path.exists(path) and os.path.getsize(path) > 0:
            try:
                loaded = _load_json(path)
                items.extend(loaded)
                logger.info(f"[Select] 加载 {len(loaded)} 条资源: {path}")
            except Exception as e:
                logger.warning(f"[Select] 加载失败 {path}: {e}")

    if not items:
        logger.error("[Select] 无可用资源，输出空列表。")
        _save_json(output_path, [])
        return []

    # 注册到 registry
    if registry:
        for it in items:
            registry.upsert(it)

    # 过滤已发送（兼容旧 history）
    items = [i for i in items if i.get("url") not in history]

    # 去重
    items = _deduplicate(items, registry)
    logger.info(f"[Select] 去重后剩余 {len(items)} 条")

    if not items:
        logger.warning("[Select] 去重后无可用资源。")
        _save_json(output_path, [])
        return []

    # 评分
    for it in items:
        it["score"] = _score(it)
    items.sort(key=lambda x: -x["score"])

    # 取候选池（Top N * 3，再做多样性筛选）
    pool_size = min(len(items), top_n * 3)
    pool = items[:pool_size]

    # 多样性控制，选出最终 top_n
    selected = _diversify(pool, top_n)

    # AI 摘要（仅对最终候选）
    try:
        from content_enricher import enrich_resources
        selected = enrich_resources(selected, registry=registry, dry_run=dry_run)
    except Exception as e:
        logger.warning(f"[Select] 摘要生成失败，使用规则摘要: {e}")
        try:
            from modelscope_client import _rule_summary
            for it in selected:
                if not it.get("summary"):
                    it.update(_rule_summary(it))
        except Exception:
            pass

    # 保存 registry
    if registry:
        for it in selected:
            registry.upsert(it)
        registry.save()

    # 写入 daily_selected.json
    output_fields = ["title", "url", "source", "tags", "score",
                     "summary", "reason", "audience", "keywords", "stars"]
    output = [{k: it.get(k) for k in output_fields} for it in selected]
    _save_json(output_path, output)
    logger.info(f"[Select] 写入 {len(output)} 条到 {output_path}")

    # 更新 posted_urls.txt（兼容旧 shell 脚本）
    urls_used = [it.get("url", "") for it in selected if it.get("url")]
    _append_history(urls_used)

    # 标记 registry 为 selected
    if registry:
        for it in selected:
            from resource_registry import STATUS_SELECTED
            key_url = it.get("url", "")
            if key_url:
                rec = registry.get_by_url(key_url)
                if rec:
                    rec["status"] = STATUS_SELECTED
        registry.save()

    return selected


def _print_compat(selected: list):
    """向 stdout 打印 @@ 格式兼容行，供旧 shell 脚本读取。"""
    for it in selected:
        title = (it.get("title") or "").replace("@@", " ").replace("\n", " ").strip()
        desc = (it.get("summary") or it.get("description") or "无简介").replace("@@", " ").replace("\n", " ").strip()
        url = it.get("url") or ""
        tags = ",".join(it.get("tags") or [])
        print("@@".join([title, desc, url, tags]))


def main():
    parser = argparse.ArgumentParser(description="资源选择与摘要生成")
    parser.add_argument("--resources", default=DEFAULT_RESOURCES)
    parser.add_argument("--fallback", default=DEFAULT_FALLBACK)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--top-n", type=int, default=5)
    parser.add_argument("--dry-run", action="store_true")
    # 兼容旧位置参数：select_resources.py <resources> <history> [fallback]
    parser.add_argument("positional", nargs="*")
    args = parser.parse_args()

    # 兼容旧调用方式
    if args.positional:
        if len(args.positional) >= 1:
            args.resources = args.positional[0]
        if len(args.positional) >= 3:
            args.fallback = args.positional[2]

    selected = select(
        resources_path=args.resources,
        fallback_path=args.fallback,
        output_path=args.output,
        top_n=args.top_n,
        dry_run=args.dry_run,
    )
    _print_compat(selected)


if __name__ == "__main__":
    main()
