import json, sys, os

# modify this set with any URLs that should be considered already published
urls_to_mark = {
    'https://github.com/openclaw/openclaw',
    'https://github.com/Significant-Gravitas/AutoGPT',
    'https://github.com/n8n-io/n8n',
}

# compute path relative to this script so it works both locally and in CI
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
path = os.path.join(SCRIPT_DIR, 'resources.json')

try:
    data = json.load(open(path, encoding='utf-8'))
except Exception as e:
    print(f'failed to load {path}: {e}', file=sys.stderr)
    sys.exit(1)

changed = False
for item in data:
    if item.get('url') in urls_to_mark:
        if not item.get('used'):
            item['used'] = True
            changed = True

if changed:
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print('marked resources', urls_to_mark)
else:
    print('no changes (already marked or URLs not found)')
