#!/usr/bin/env python3
"""
helper_fetch.py
采集 RSS / GitHub Search / SCP，清洗标准化，写入 resources.json。
"""

import os
import sys
import json
import time
import hashlib
import random
import re
import logging
from datetime import datetime, timezone

try:
    import requests
except ImportError:
    print("[ERROR] 缺少 requests，请运行: pip install requests", file=sys.stderr)
    sys.exit(2)

try:
    import feedparser
except ImportError:
    print("[ERROR] 缺少 feedparser，请运行: pip install feedparser", file=sys.stderr)
    sys.exit(2)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RESOURCES_PATH = os.path.join(SCRIPT_DIR, "resources.json")
LOG_PATH = os.path.join(SCRIPT_DIR, "helper_fetch.log")
HISTORY_PATH = os.path.join(SCRIPT_DIR, "posted_urls.txt")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

# ── 来源配置 ──────────────────────────────────────────────────────────────────

RSS_FEEDS = [
    ("https://hnrss.org/frontpage", ["tech", "programming"], 12),
    ("https://dev.to/feed/tag/ai", ["ai", "dev"], 10),
    ("https://lobste.rs/rss", ["tech", "programming"], 10),
    ("https://www.producthunt.com/feed", ["product", "tool"], 8),
    ("https://techcrunch.com/feed/", ["tech", "news"], 8),
    ("https://www.reddit.com/r/programming/.rss", ["programming"], 8),
    ("https://www.reddit.com/r/python/.rss", ["python"], 8),
    ("https://www.reddit.com/r/SCP/.rss", ["scp"], 6),
    ("https://scp-wiki.wikidot.com/rss", ["scp"], 6),
    ("https://scp-wiki-cn.wikidot.com/rss", ["scp", "chinese"], 6),
]

GITHUB_SEARCH_QUERIES = [
    ("topic:ai stars:>50000", ["ai"], 10),
    ("stars:>50000 machine learning", ["ai", "ml"], 10),
    ("stars:>50000", [], 10),
    ("stars:>50000 topic:javascript", ["javascript"], 8),
    ("stars:>40000 topic:cli", ["cli"], 8),
    ("stars:>40000 topic:devops", ["devops"], 8),
    ("stars:>30000 topic:python", ["python"], 8),
    ("stars:>30000 topic:go", ["go"], 8),
    ("stars:>20000 topic:rust", ["rust"], 8),
]

MAX_RESULTS = 60

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
_GH_HEADERS = {"Authorization": f"token {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}


# ── URL 规范化（轻量版，不依赖 normalize_utils）────────────────────────────────

_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "ref", "fbclid", "gclid", "_ga",
}


def _normalize_url(url: str) -> str:
    if not url:
        return ""
    try:
        from urllib.parse import urlparse, urlunparse, urlencode, parse_qsl
        p = urlparse(url.strip())
        qs = [(k, v) for k, v in parse_qsl(p.query) if k.lower() not in _TRACKING_PARAMS]
        path = p.path.rstrip("/") or "/"
        return urlunparse((p.scheme.lower(), p.netloc.lower(), path, "", urlencode(qs), ""))
    except Exception:
        return url


def _url_key(url: str) -> str:
    return hashlib.sha256(_normalize_url(url).encode()).hexdigest()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── 采集函数 ──────────────────────────────────────────────────────────────────

def fetch_rss() -> list:
    items = []
    for feed_url, tags, limit in RSS_FEEDS:
        try:
            d = feedparser.parse(feed_url, request_headers={"User-Agent": "Mozilla/5.0"})
            entries = d.entries[:limit]
            for e in entries:
                link = e.get("link") or e.get("id") or ""
                title = (e.get("title") or "").strip()
                desc = (e.get("summary") or e.get("description") or "").strip()
                # 清理 HTML 标签
                desc = re.sub(r"<[^>]+>", "", desc)[:300]
                published = e.get("published", "")
                entry_tags = list(tags)
                low = (title + " " + desc).lower()
                if "scp" in feed_url.lower() or "scp-" in low:
                    if "scp" not in entry_tags:
                        entry_tags.append("scp")
                items.append({
                    "title": title,
                    "description": desc,
                    "url": link,
                    "source": f"rss:{feed_url}",
                    "fetched_at": _now_iso(),
                    "published": published,
                    "score": 10,
                    "tags": entry_tags,
                })
            logger.info(f"[RSS] {feed_url} → {len(entries)} 条")
        except Exception as e:
            logger.warning(f"[RSS] 采集失败 {feed_url}: {e}")
    return items


def fetch_scp() -> list:
    """从 SCP 官网抓取随机条目。"""
    items = []
    try:
        r = requests.get(
            "https://scp-wiki.wikidot.com/scp-series",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15,
            verify=False,
        )
        if r.status_code == 200:
            paths = list(set(re.findall(r'href="(/scp-\d{3,})"', r.text)))
            sample = random.sample(paths, min(len(paths), 5))
            for path in sample:
                url = "https://scp-wiki.wikidot.com" + path
                title = path.lstrip("/").upper()
                desc = ""
                try:
                    pr = requests.get(url, headers={"User-Agent": "Mozilla/5.0"},
                                      timeout=10, verify=False)
                    if pr.status_code == 200:
                        m = re.search(r"<title>([^<]+)</title>", pr.text)
                        if m:
                            title = m.group(1).strip()
                        p = re.search(r"<p>([^<]{20,200})</p>", pr.text)
                        if p:
                            desc = p.group(1).strip()
                except Exception:
                    pass
                items.append({
                    "title": title,
                    "description": desc,
                    "url": url,
                    "source": "scp-scrape",
                    "fetched_at": _now_iso(),
                    "score": 100,
                    "tags": ["scp"],
                })
        else:
            logger.warning(f"[SCP] series 页面返回 {r.status_code}")
    except Exception as e:
        logger.warning(f"[SCP] 抓取失败: {e}")
    logger.info(f"[SCP] 获取 {len(items)} 条")
    return items


def fetch_github() -> list:
    items = []
    for query, tags, per_page in GITHUB_SEARCH_QUERIES:
        try:
            params = {"q": query, "sort": "stars", "order": "desc", "per_page": per_page}
            resp = requests.get(
                "https://api.github.com/search/repositories",
                params=params,
                headers=_GH_HEADERS,
                timeout=15,
            )
            if resp.status_code != 200:
                logger.warning(f"[GitHub] '{query}' → HTTP {resp.status_code}")
                continue
            for repo in resp.json().get("items", []):
                desc = (repo.get("description") or "").strip()
                # 补充 topics 作为 tags
                repo_tags = list(tags) + (repo.get("topics") or [])[:3]
                items.append({
                    "title": repo.get("full_name", ""),
                    "description": desc,
                    "url": repo.get("html_url", ""),
                    "source": "github:search",
                    "fetched_at": _now_iso(),
                    "published": repo.get("pushed_at", ""),
                    "stars": repo.get("stargazers_count", 0),
                    "score": 20,
                    "tags": repo_tags,
                })
            logger.info(f"[GitHub] '{query}' → {len(resp.json().get('items', []))} 条")
            time.sleep(1)
        except Exception as e:
            logger.warning(f"[GitHub] 查询失败 '{query}': {e}")
    return items


# ── 合并去重 ──────────────────────────────────────────────────────────────────

def merge_items(all_items: list) -> list:
    seen = {}
    for it in all_items:
        url = it.get("url") or ""
        key = _url_key(url) if url else hashlib.sha256((it.get("title") or "").encode()).hexdigest()
        if key not in seen:
            seen[key] = it
        else:
            # 保留 score 更高的
            if it.get("score", 0) > seen[key].get("score", 0):
                seen[key] = it
    merged = list(seen.values())
    merged.sort(key=lambda x: -x.get("score", 0))
    return merged[:MAX_RESULTS]


def load_history() -> set:
    if os.path.exists(HISTORY_PATH):
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            return {l.strip() for l in f if l.strip()}
    return set()


def main():
    logger.info("[START] helper_fetch 开始运行")
    history = load_history()

    all_items = []

    rss = fetch_rss()
    all_items.extend(rss)

    scp = fetch_scp()
    all_items.extend(scp)

    gh = fetch_github()
    all_items.extend(gh)

    # 过滤已发送
    before = len(all_items)
    all_items = [i for i in all_items if i.get("url") not in history]
    logger.info(f"[Filter] 过滤已发送后: {before} → {len(all_items)} 条")

    merged = merge_items(all_items)

    if not merged:
        logger.warning("[WARN] 采集结果为空，保留现有 resources.json")
        if os.path.exists(RESOURCES_PATH) and os.path.getsize(RESOURCES_PATH) > 0:
            return

    tmp = RESOURCES_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    os.replace(tmp, RESOURCES_PATH)
    logger.info(f"[DONE] 写入 {len(merged)} 条到 {RESOURCES_PATH}")


if __name__ == "__main__":
    main()
