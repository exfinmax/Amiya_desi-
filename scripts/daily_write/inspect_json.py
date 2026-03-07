import json
with open('scripts/daily_write/resources.json','r',encoding='utf-8') as f:
    data=json.load(f)
for item in data[:20]:
    t=item.get('title','')
    d=item.get('description','')
    if '\n' in t or '\n' in d:
        print('FOUND', repr(t), repr(d))
