#!/usr/bin/env python3
import re
import json
import os
from datetime import datetime, timezone

BASE = os.path.dirname(os.path.abspath(__file__))
MC_FILE = os.path.join(BASE, 'mcporter_out.txt')
RES_FILE = os.path.join(BASE, 'resources.json')

if not os.path.exists(MC_FILE):
    print('mcporter_out.txt not found')
    raise SystemExit(1)

with open(MC_FILE, 'r', encoding='utf-8') as f:
    data = f.read()

# Find Title: ... and URL: ... pairs
titles = re.findall(r'^Title:\s*(.+)$', data, flags=re.MULTILINE)
urls = re.findall(r'^URL:\s*(.+)$', data, flags=re.MULTILINE)

pairs = list(zip(titles, urls))
now = datetime.now(timezone.utc).isoformat()

existing = []
if os.path.exists(RES_FILE):
    with open(RES_FILE, 'r', encoding='utf-8') as f:
        existing = json.load(f)

existing_urls = {item.get('url') for item in existing}
added = 0
for t,u in pairs:
    if u in existing_urls:
        continue
    entry = {
        'title': t.strip(),
        'description': '',
        'url': u.strip(),
        'source': 'websearch:exa',
        'fetched_at': now,
        'score': 25
    }
    existing.append(entry)
    existing_urls.add(u)
    added += 1

# limit to 50 items keep newest first
existing = existing[:50]
with open(RES_FILE, 'w', encoding='utf-8') as f:
    json.dump(existing, f, ensure_ascii=False, indent=2)
print(f'Added {added} items from mcporter output to {RES_FILE}')
