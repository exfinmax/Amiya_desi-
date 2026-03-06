#!/usr/bin/env python3
import json,sys,html
from pathlib import Path
p=Path(__file__).parent
payload_file=p/'dry_run_payload.json'
out_file=p/'dry_run_preview.html'
if not payload_file.exists():
    print('dry_run_payload.json not found at', payload_file)
    sys.exit(1)
obj=json.load(open(payload_file,encoding='utf-8'))
title=html.escape(obj.get('title','(no title)'))
body=html.escape(obj.get('body','')).replace('\n','<br>')
labels=obj.get('labels',[])
labels_html=' '.join(f'<span style="background:#eee;border-radius:4px;padding:2px 6px;margin-right:6px">{html.escape(str(l))}</span>' for l in labels)
html_doc=f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>{title}</title></head>
<body style="font-family:Arial,Helvetica,sans-serif;line-height:1.6;max-width:800px;margin:40px;">
<h1>{title}</h1>
<div>{labels_html}</div>
<hr>
<div>{body}</div>
</body></html>'''
open(out_file,'w',encoding='utf-8').write(html_doc)
print('Wrote',out_file)
