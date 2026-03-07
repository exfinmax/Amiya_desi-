#!/usr/bin/env python3
"""Select a few random resources from a JSON file, remove them from the pool
and append their URLs to a history file to avoid repeating later.

Usage:
    select_resources.py <resources.json> <history.txt> [fallback.json]

The script prints lines with the format:
    title@@translated_description@@url@@tags

Translation is done via a simple HTTP call to MyMemory translate API. If
translation fails we fall back to the original text.

The script also updates the supplied JSON (either resources or fallback) by
removing the selected items so they won't be picked again immediately.
"""
import json
import random
import sys
import os
import requests

# small cache of translations in-memory to avoid duplicate network calls
_translation_cache = {}


def translate_to_zh(text: str) -> str:
    if not text:
        return ''
    if text in _translation_cache:
        return _translation_cache[text]
    try:
        # use MyMemory free API; it has fairly generous limits for a few items
        r = requests.get(
            'https://api.mymemory.translated.net/get',
            params={'q': text, 'langpair': 'en|zh-CN'},
            timeout=5,
        )
        data = r.json()
        tr = data.get('responseData', {}).get('translatedText', text)
    except Exception:
        tr = text
    _translation_cache[text] = tr
    return tr


def load_history(path: str) -> set:
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return {l.strip() for l in f if l.strip()}
    return set()


def append_history(path: str, urls):
    if not urls:
        return
    with open(path, 'a', encoding='utf-8') as f:
        for u in urls:
            f.write(u + "\n")


def load_items(path: str) -> list:
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_items(path: str, items: list):
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def pick_items(items: list, history: set) -> (list, list):
    # filter out previously used URLs or those manually marked
    def is_used(item):
        if item.get('url') in history:
            return True
        if item.get('used') or item.get('posted'):
            return True
        return False
    items = [i for i in items if not is_used(i)]
    if not items:
        return [], []
    scp = [i for i in items if ('tags' in i and 'scp' in i.get('tags', []))
           or ('scp' in (i.get('source') or ''))]
    other = [i for i in items if i not in scp]

    total = random.randint(3, 5)
    # determine how many SCP items to include based on probability
    # 60% → 0, 30% → 1, 10% → 2. ~0.1% chance of "easter egg" all-SCP.
    easter = random.random() < 0.001
    if easter:
        scp_selected = random.sample(scp, min(len(scp), total)) if scp else []
        # mark all selections as easter
        for it in scp_selected:
            it.setdefault('tags', []).append('easter')
        other_selected = []
    else:
        r = random.random()
        if r < 0.6:
            scp_count = 0
        elif r < 0.9:
            scp_count = 1
        else:
            scp_count = 2
        scp_count = min(scp_count, len(scp))
        scp_selected = random.sample(scp, scp_count) if scp_count > 0 else []
        other_count = total - len(scp_selected)
        other_selected = (random.sample(other, min(other_count, len(other)))
                          if other_count > 0 and other else [])
    selected = scp_selected + other_selected
    remaining = [i for i in items if i not in selected]
    return selected, remaining


def main():
    if len(sys.argv) < 3:
        sys.stderr.write("Usage: select_resources.py <resources.json> <history.txt> [fallback.json]\n")
        sys.exit(1)

    resources_path = sys.argv[1]
    history_path = sys.argv[2]
    fallback_path = sys.argv[3] if len(sys.argv) >= 4 else None

    history = load_history(history_path)
    selected = []

    def try_path(path):
        nonlocal selected
        if path and os.path.exists(path) and os.path.getsize(path) > 0:
            try:
                items = load_items(path)
            except Exception:
                return []
            sel, remaining = pick_items(items, history)
            if sel:
                # update the file with leftovers
                save_items(path, remaining)
            return sel
        return []

    # first try normal resources file
    selected = try_path(resources_path)
    if not selected:
        # fall back if available
        selected = try_path(fallback_path)

    # print output lines and append history
    urls_used = []
    for it in selected:
        title = it.get('title', '')
        desc = translate_to_zh(it.get('description', ''))
        # sanitize stray newline characters, escape sequences and @@ markers
        title = title.replace('\\n', ' ').replace('\\r', ' ').replace('\n', ' ').replace('@@', ' ').strip()
        desc = desc.replace('\\n', ' ').replace('\\r', ' ').replace('\n', ' ').replace('@@', ' ').strip()
        url = it.get('url', '')
        tags = ','.join(it.get('tags', [])) if it.get('tags') else ''
        print('@@'.join([title, desc, url, tags]))
        urls_used.append(url)

    append_history(history_path, urls_used)


if __name__ == '__main__':
    main()
