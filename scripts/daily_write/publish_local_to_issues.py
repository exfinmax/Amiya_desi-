#!/usr/bin/env python3
"""
publish_local_to_issues.py
将本地修改后的MD文件批量发布到GitHub Issues
"""

import os
import re
import json
import requests
from datetime import datetime

def get_github_token():
    """获取GitHub Token"""
    token = os.environ.get('GITHUB_TOKEN') or os.environ.get('TOKEN_PUBLISH')
    if not token:
        raise ValueError("请设置 GITHUB_TOKEN 或 TOKEN_PUBLISH 环境变量")
    return token

def get_repo():
    """获取仓库名"""
    return os.environ.get('GITHUB_REPOSITORY', 'exfinmax/Amiya_desi-')

def extract_date_from_filename(filename):
    """从文件名提取日期"""
    match = re.search(r'(\d{4}-\d{2}-\d{2})', filename)
    return match.group(1) if match else None

def parse_markdown_content(content, filename):
    """解析markdown内容，提取标题和正文"""
    lines = content.split('\n')
    
    # 提取标题（第一行 # 开头）
    title = None
    body_lines = []
    
    for line in lines:
        if line.startswith('# ') and not title:
            title = line[2:].strip()
        else:
            body_lines.append(line)
    
    # 如果没有找到标题，使用文件名
    if not title:
        date = extract_date_from_filename(filename)
        if date:
            title = f"[Update] 今日免费资源推荐 - {date}"
        else:
            title = os.path.splitext(filename)[0]
    
    body = '\n'.join(body_lines).strip()
    
    return title, body

def create_github_issue(title, body, labels, token, repo):
    """创建GitHub Issue"""
    url = f"https://api.github.com/repos/{repo}/issues"
    
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json"
    }
    
    payload = {
        "title": title,
        "body": body,
        "labels": labels
    }
    
    response = requests.post(url, headers=headers, json=payload)
    
    if response.status_code == 201:
        issue_number = response.json().get('number')
        issue_url = response.json().get('html_url')
        print(f"✅ 创建成功: {title} (#{issue_number})")
        print(f"   链接: {issue_url}")
        return True
    else:
        print(f"❌ 创建失败: {title}")
        print(f"   状态码: {response.status_code}")
        print(f"   错误: {response.text}")
        return False

def main():
    # 配置
    token = get_github_token()
    repo = get_repo()
    backup_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'backup')
    
    # 从3月7号开始的文件
    files_to_publish = [
        '[Test] 今日免费资源推荐 - SCP 测试.md',
        '[Update] 今日免费资源推荐 - 2026-03-08.md',
        '[Update] 今日免费资源推荐 - 2026-03-09.md',
        '[Update] 今日免费资源推荐 - 2026-03-10.md',
        '[Update] 今日免费资源推荐 - 2026-03-11.md',
        '[Update] 今日免费资源推荐 - 2026-03-12.md',
        '[Update] 今日免费资源推荐 - 2026-03-13.md',
        '[Update] 今日免费资源推荐 - 2026-03-14.md',
        '[Update] 今日免费资源推荐 - 2026-03-15.md',
        '[Update] 今日免费资源推荐 - 2026-03-16.md',
        '[Update] 今日免费资源推荐 - 2026-03-17.md',
        '[Update] 今日免费资源推荐 - 2026-03-18.md',
        '[Update] 今日免费资源推荐 - 2026-03-19.md',
        '[Update] 今日免费资源推荐 - 2026-03-20.md',
        '[Update] 今日免费资源推荐 - 2026-03-21.md',
        '[Update] 今日免费资源推荐 - 2026-03-22.md',
        '[Update] 今日免费资源推荐 - 2026-03-23.md',
        '[Update] 今日免费资源推荐 - 2026-03-24.md',
        '[Update] 今日免费资源推荐 - 2026-03-25.md',
        '[Update] 今日免费资源推荐 - 2026-03-26.md',
        '[Update] 今日免费资源推荐 - 2026-03-27.md',
        '[Update] 今日免费资源推荐 - 2026-03-28.md',
    ]
    
    print(f"🚀 开始批量发布到 {repo}")
    print(f"📁 备份目录: {backup_dir}")
    print(f"📊 共 {len(files_to_publish)} 篇文章")
    print()
    
    success_count = 0
    fail_count = 0
    skipped_count = 0
    
    for i, filename in enumerate(files_to_publish, 1):
        print(f"[{i}/{len(files_to_publish)}] 处理: {filename}")
        
        filepath = os.path.join(backup_dir, filename)
        
        if not os.path.exists(filepath):
            print(f"  ⚠️ 文件不存在，跳过")
            skipped_count += 1
            continue
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 解析内容
            title, body = parse_markdown_content(content, filename)
            
            # 如果没有body，使用默认内容
            if not body or len(body) < 50:
                print(f"  ⚠️ 内容太少，跳过")
                skipped_count += 1
                continue
            
            # 设置标签
            labels = ["免费资源", "构建成功", "made by ai"]
            if 'SCP' in filename:
                labels.append("SCP彩蛋")
            
            # 创建Issue
            if create_github_issue(title, body, labels, token, repo):
                success_count += 1
            else:
                fail_count += 1
                
        except Exception as e:
            print(f"  ❌ 异常: {e}")
            fail_count += 1
        
        print()
    
    print("=" * 50)
    print(f"📊 发布完成!")
    print(f"✅ 成功: {success_count}")
    print(f"❌ 失败: {fail_count}")
    print(f"⚠️ 跳过: {skipped_count}")

if __name__ == '__main__':
    main()
