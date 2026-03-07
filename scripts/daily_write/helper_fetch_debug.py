#!/usr/bin/env python3
"""
helper_fetch_debug.py - copy of helper_fetch.py with extra debug logging
Writes resources.json and logs debug info to helper_fetch.log
"""
import os
import sys
import json
import time
import hashlib
from datetime import datetime, timezone

try:
    import requests
except Exception:
    print("[ERROR] Python package 'requests' not found. Please run: pip3 install requests", file=sys.stderr)
    sys.exit(2)

try:
    import feedparser
except Exception:
    print("[ERROR] Python package 'feedparser' not found. Please run: pip3 install feedparser", file=sys.stderr)
    sys.exit(2)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RESOURCES_PATH = os.path.join(SCRIPT_DIR, 'resources.json')
LOG_PATH = os.path.join(SCRIPT_DIR, 'helper_fetch.log')

RSS_FEEDS = [
    'https://hnrss.org/frontpage',
    'https://dev.to/feed/tag/ai',
    'https://lobste.rs/rss',
    'https://www.producthunt.com/feed',
    'https://techcrunch.com/feed/',
    'https://www.reddit.com/r/technology/.rss',
    'https://scp-wiki.wikidot.com/rss',
    'https://www.scp-wiki.net/rss.php',
    'https://scp-wiki-cn.wikidot.mer.run/most-recently-created',
]

GITHUB_SEARCH_QUERIES = [
    'topic:ai stars:>50000',
    'stars:>50000 machine learning',
    'stars:>30000 artificial intelligence',
]

MAX_RESULTS = 50

headers = {}
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')
if GITHUB_TOKEN:
    headers['Authorization'] = f'token {GITHUB_TOKEN}'


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def log(msg):
    ts = datetime.now().isoformat()
    with open(LOG_PATH, 'a', encoding='utf-8') as f:
        f.write(f"{ts} {msg}\n")
    print(msg)


def hash_url(u):
    return hashlib.sha256(u.encode('utf-8')).hexdigest()


def fetch_rss():
    items = []
    for url in RSS_FEEDS:
        try:
            d = feedparser.parse(url)
            entries = d.entries[:10]
            for e in entries:
                link = e.get('link') or e.get('id') or ''
                title = e.get('title', '').strip()
                desc = e.get('summary', '') or e.get('description', '') or ''
                published = e.get('published', '')
                entry = {
                    'title': title,
                    'description': desc,
                    'url': link,
                    'source': f'rss:{url}',
                    'fetched_at': now_iso(),
                    'published': published,
                    'score': 10,
                    'tags': []
                }
                low = (title or '').lower() + ' ' + (desc or '').lower()
                if 'scp' in url.lower() or 'scp' in low or 'scp-' in low:
                    entry['tags'].append('scp')
                    entry['source'] = 'rss:scp'
                items.append(entry)
            log(f"[RSS] Fetched {len(entries)} from {url}")
        except Exception as e:
            log(f"[RSS] Error fetching {url}: {e}")
    return items


def fetch_github():
    items = []
    for q in GITHUB_SEARCH_QUERIES:
        try:
            params = {'q': q, 'sort': 'stars', 'order': 'desc', 'per_page': 10}
            resp = requests.get('https://api.github.com/search/repositories', params=params, headers=headers, timeout=15)
            if resp.status_code != 200:
                log(f"[GITHUB] Search '{q}' returned status {resp.status_code}")
                continue
            data = resp.json()
            for repo in data.get('items', [])[:10]:
                title = repo.get('full_name')
                desc = repo.get('description') or ''
                html_url = repo.get('html_url')
                stars = repo.get('stargazers_count', 0)
                items.append({
                    'title': title,
                    'description': desc,
                    'url': html_url,
                    'source': 'github:search',
                    'fetched_at': now_iso(),
                    'stars': stars,
                    'score': 20 + min(stars, 1000) / 100.0,
                })
            log(f"[GITHUB] Query '{q}' fetched {len(data.get('items', []))} items")
            time.sleep(1)
        except Exception as e:
            log(f"[GITHUB] Error searching '{q}': {e}")
    return items


def merge_items(list_of_items):
    seen = set()
    merged = []
    for it in list_of_items:
        url = it.get('url') or ''
        key = url or (it.get('title') or '')
        fingerprint = hash_url(key)
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        merged.append(it)
    def score_key(x):
        return -(x.get('score', 0))
    merged.sort(key=score_key)
    return merged[:MAX_RESULTS]


def main():
    all_items = []
    log('[START] helper_fetch running (debug)')
    rss_items = fetch_rss()
    all_items.extend(rss_items)
    gh_items = fetch_github()
    all_items.extend(gh_items)

    merged = merge_items(all_items)
    log(f"[DEBUG] Merged count: {len(merged)}")
    if len(merged) > 0:
        try:
            log(f"[DEBUG] Example item: {json.dumps(merged[0], ensure_ascii=False)[:1000]}")
        except Exception:
            log('[DEBUG] Could not stringify example item')

    # Write atomically to avoid race conditions (write temp then rename)
    tmp_path = RESOURCES_PATH + '.tmp'
    with open(tmp_path, 'w', encoding='utf-8') as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    try:
        os.replace(tmp_path, RESOURCES_PATH)
    except Exception:
        # fallback to rename
        if os.path.exists(RESOURCES_PATH):
            os.remove(RESOURCES_PATH)
        os.rename(tmp_path, RESOURCES_PATH)
    log(f"[DONE] Wrote {len(merged)} items to {RESOURCES_PATH}")


if __name__ == '__main__':
    main()
