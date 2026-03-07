#!/usr/bin/env python3
"""
helper_fetch.py
Fetch resources from RSS feeds and GitHub Search API, merge results and write resources.json
"""
import os
import sys
import json
import time
import hashlib
import random
import re
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
HISTORY_PATH = os.path.join(SCRIPT_DIR, 'posted_urls.txt')

# feeding a wider variety of feeds reduces repetition
RSS_FEEDS = [
    'https://hnrss.org/frontpage',
    'https://dev.to/feed/tag/ai',
    'https://lobste.rs/rss',
    'https://www.producthunt.com/feed',
    # Additional technology sources
    'https://techcrunch.com/feed/',
    'https://www.reddit.com/r/technology/.rss',
    'https://www.reddit.com/r/programming/.rss',
    'https://www.reddit.com/r/python/.rss',
    'https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml',
    # SCP Foundation feeds (community stories)
    'https://scp-wiki.wikidot.com/rss',
    'https://www.scp-wiki.net/rss.php',
    # additional SCP mirrors and community feeds
    'https://scp-wiki-cn.wikidot.mer.run/most-recently-created',
    'https://www.reddit.com/r/SCP/.rss',
    'https://www.reddit.com/r/SCPChinese/.rss',
    'https://scp-jp.wikidot.com/rss',
    'https://scp-wiki-cn.wikidot.com/rss',
    # miscellaneous SCP-related aggregators
    'https://scp.eldritch-horror.com/rss',
]

# queries broadened to include other popular open source projects
GITHUB_SEARCH_QUERIES = [
    # AI / ML oriented
    'topic:ai stars:>50000',
    'stars:>50000 machine learning',
    'stars:>30000 artificial intelligence',
    # general high-star projects across languages and domains
    'stars:>50000',
    'stars:>50000 topic:javascript',
    'stars:>50000 topic:web',
    'stars:>40000 topic:cli',
    'stars:>40000 topic:devops',
    'stars:>30000 topic:python',
    'stars:>30000 topic:go',
    'stars:>20000 topic:open-source',
    'stars:>20000 topic:rust',
    'stars:>15000 data science',
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


def load_history():
    """Return a set of URLs that have already been posted."""
    if os.path.exists(HISTORY_PATH):
        with open(HISTORY_PATH, 'r', encoding='utf-8') as f:
            return {line.strip() for line in f if line.strip()}
    return set()


def hash_url(u):
    return hashlib.sha256(u.encode('utf-8')).hexdigest()


def fetch_rss():
    items = []
    for url in RSS_FEEDS:
        try:
            # some RSS endpoints (especially SCP mirrors) reject default Python UA;
            # pretend to be a browser so we get a response.
            d = feedparser.parse(url, request_headers={'User-Agent': 'Mozilla/5.0'})
            entries = d.entries[:20]  # grab more items from each feed
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
                # Tag SCP-related items
                low = (title or '').lower() + ' ' + (desc or '').lower()
                if 'scp' in url.lower() or 'scp' in low or 'scp-' in low:
                    entry['tags'].append('scp')
                    entry['source'] = 'rss:scp'
                items.append(entry)
            log(f"[RSS] Fetched {len(entries)} from {url}")
        except Exception as e:
            log(f"[RSS] Error fetching {url}: {e}")
    return items


def fetch_scp():
    """Scrape SCP Foundation website for random article links.

    The official site doesn't expose a usable RSS feed, so we fetch the
    "scp-series" page and extract /scp-### links.  A few random articles are
    then fetched to obtain titles/short descriptions.  This helps ensure the
    workflow occasionally includes SCP stories even when the RSS feeds are
    unavailable.
    """
    items = []
    try:
        r = requests.get('https://scp-wiki.wikidot.com/scp-series',
                         headers={'User-Agent': 'Mozilla/5.0'},
                         timeout=15,
                         verify=False)
        if r.status_code == 200:
            paths = set(re.findall(r'href="(/scp-\d{3,})"', r.text))
            if paths:
                sample = random.sample(list(paths), min(len(paths), 5))
                for path in sample:
                    url = 'https://scp-wiki.wikidot.com' + path
                    title = path.lstrip('/')
                    desc = ''
                    try:
                        pr = requests.get(url,
                                          headers={'User-Agent': 'Mozilla/5.0'},
                                          timeout=10,
                                          verify=False)
                        if pr.status_code == 200:
                            m = re.search(r'<title>([^<]+)</title>', pr.text)
                            if m:
                                title = m.group(1).strip()
                            p = re.search(r'<p>([^<]{20,200})</p>', pr.text)
                            if p:
                                desc = p.group(1).strip()
                    except Exception:
                        pass
                    items.append({
                        'title': title,
                        'description': desc,
                        'url': url,
                        'source': 'scp-scrape',
                        'fetched_at': now_iso(),
                        # give SCP entries a generous score so they
                        # aren't trimmed out when MAX_RESULTS is reached
                        'score': 100,
                        'tags': ['scp'],
                    })
        else:
            log(f"[SCP] series page returned {r.status_code}")
    except Exception as e:
        log(f"[SCP] scrape error: {e}")
    log(f"[SCP] gathered {len(items)} articles")
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
    # sort by score if present, else by fetched_at
    def score_key(x):
        return -(x.get('score', 0))
    merged.sort(key=score_key)
    return merged[:MAX_RESULTS]


def main():
    all_items = []
    log('[START] helper_fetch running')
    history = load_history()

    rss_items = fetch_rss()
    # drop anything that has already been posted
    rss_items = [i for i in rss_items if i.get('url') not in history]
    all_items.extend(rss_items)

    sc_items = fetch_scp()
    sc_items = [i for i in sc_items if i.get('url') not in history]
    all_items.extend(sc_items)

    gh_items = fetch_github()
    gh_items = [i for i in gh_items if i.get('url') not in history]
    all_items.extend(gh_items)

    merged = merge_items(all_items)
    # if we fetched nothing, don't overwrite an existing file – leave
    # previous results in place so the poster still has something to work
    # with.  this prevents the workflow from generating a template article
    # every time the network or APIs are temporarily unavailable.
    if not merged:
        log("[WARN] fetched 0 items; keeping existing resources.json if present")
        if os.path.exists(RESOURCES_PATH) and os.path.getsize(RESOURCES_PATH) > 0:
            return
    # Write atomically to avoid race conditions (write temp then rename)
    tmp_path = RESOURCES_PATH + '.tmp'
    with open(tmp_path, 'w', encoding='utf-8') as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    try:
        os.replace(tmp_path, RESOURCES_PATH)
    except Exception:
        # fallback to rename
        os.remove(RESOURCES_PATH) if os.path.exists(RESOURCES_PATH) else None
        os.rename(tmp_path, RESOURCES_PATH)
    log(f"[DONE] Wrote {len(merged)} items to {RESOURCES_PATH}")


if __name__ == '__main__':
    main()
