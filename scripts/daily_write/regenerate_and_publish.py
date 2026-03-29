#!/usr/bin/env python3
"""
regenerate_and_publish.py
重新生成所有文章内容并发布到GitHub Issues
"""

import os
import re
import json
import requests
import random
from datetime import datetime, timedelta

def get_github_token():
    """获取GitHub Token"""
    token = os.environ.get('GITHUB_TOKEN') or os.environ.get('TOKEN_PUBLISH')
    if not token:
        raise ValueError("请设置 GITHUB_TOKEN 或 TOKEN_PUBLISH 环境变量")
    return token

def get_repo():
    """获取仓库名"""
    return os.environ.get('GITHUB_REPOSITORY', 'exfinmax/Amiya_desi-')

def generate_akuma_title(date_str, resource_count=3):
    """生成Akuma风格的标题（活泼风格，适度颜文字）"""
    templates = [
        f"今日份技术干货，本站娘帮你整理好啦~",
        f"哼，{resource_count}个资源也就一般般啦，不过值得一看~",
        f"本站娘精心挑选的{resource_count}个宝藏，不看是你的损失~",
        f"今日技术速递，本站娘为你打包好了~",
        f"{resource_count}个开源神器，本站娘认证推荐~",
        f"周五技术特辑！本站娘精选的宝藏资源~ (｡•̀ᴗ-)✧" if datetime.strptime(date_str, '%Y-%m-%d').weekday() == 4 else f"今日份技术精选，速来围观~",
    ]
    return random.choice(templates)

def generate_akuma_greeting(date_str):
    """生成Akuma风格的祝福语（活泼风格，适度颜文字）"""
    weekday = datetime.strptime(date_str, '%Y-%m-%d').weekday()
    
    if weekday == 4:  # 周五
        return "周五了！这些资源够你周末研究用了，快收好~ (๑•̀ㅂ•́)و✧"
    elif weekday == 5:  # 周六
        return "周末也别闲着，这些技术资源本站娘觉得还不错~"
    elif weekday == 6:  # 周日
        return "周日晚上了，提前准备下周的学习资源吧~"
    else:
        templates = [
            "哼，今天的资源也就一般般啦，不过看看也无妨~ (｡•̀ᴗ-)✧",
            "本站娘精心挑选的资源，不看可是你的损失哦~",
            "今天的这些技术嘛...还算凑合吧，随便看看~",
            "工作日也要学习，这些资源本站娘帮你筛选好了~",
        ]
        return random.choice(templates)

def generate_formal_summary(repo_name, stars):
    """生成正式风格的摘要和推荐理由"""
    
    # 根据项目名称特征生成描述
    if 'pathway' in repo_name.lower():
        return {
            'summary': '高性能数据处理框架，支持实时流处理和复杂事件处理',
            'reason': '适合需要处理大规模实时数据的企业级应用场景',
            'keywords': ['data-processing', 'real-time', 'framework']
        }
    elif 'affine' in repo_name.lower():
        return {
            'summary': '下一代知识管理工具，集笔记、白板、数据库于一体',
            'reason': '为团队协作和个人知识管理提供统一的解决方案',
            'keywords': ['knowledge-management', 'collaboration', 'workspace']
        }
    elif 'sherlock' in repo_name.lower():
        return {
            'summary': '跨平台用户名搜索工具，支持数百个社交媒体网站',
            'reason': '帮助安全研究人员和记者进行在线身份调查',
            'keywords': ['osint', 'social-search', 'investigation']
        }
    elif 'react' in repo_name.lower():
        return {
            'summary': '流行的前端JavaScript库，用于构建用户界面',
            'reason': '组件化开发模式提高代码复用性和维护性',
            'keywords': ['frontend', 'javascript', 'ui']
        }
    elif 'system-prompt' in repo_name.lower() or 'prompt' in repo_name.lower():
        return {
            'summary': 'AI系统提示词集合，包含多种模型的优化提示',
            'reason': '帮助开发者快速构建高质量的AI应用交互',
            'keywords': ['ai', 'prompts', 'llm']
        }
    elif 'ml' in repo_name.lower() or 'machine-learning' in repo_name.lower():
        return {
            'summary': '微软机器学习入门教程，包含理论知识和实践项目',
            'reason': '为零基础学习者提供系统化的机器学习入门路径',
            'keywords': ['machine-learning', 'tutorial', 'beginners']
        }
    elif 'scikit' in repo_name.lower():
        return {
            'summary': 'Python机器学习库，提供简单且高效的数据分析工具',
            'reason': '适合机器学习初学者和专业人士使用',
            'keywords': ['machine-learning', 'python', 'data-science']
        }
    elif 'yt-dlp' in repo_name.lower():
        return {
            'summary': '强大的视频下载工具，支持YouTube等数百个网站',
            'reason': '提供高质量视频下载和格式转换功能',
            'keywords': ['video-download', 'youtube', 'media']
        }
    elif 'angular' in repo_name.lower():
        return {
            'summary': 'Google开发的前端框架，用于构建复杂的Web应用',
            'reason': '提供完整的开发工具链和企业级支持',
            'keywords': ['frontend', 'framework', 'google']
        }
    else:
        # 通用描述
        if stars > 100000:
            return {
                'summary': f'GitHub高星开源项目，拥有{stars:,}个star，社区活跃',
                'reason': '经过大量开发者验证，具有良好的稳定性和丰富的功能',
                'keywords': ['open-source', 'popular', 'reliable']
            }
        elif stars > 50000:
            return {
                'summary': f'GitHub热门开源项目，拥有{stars:,}个star',
                'reason': '社区认可度高，文档完善，适合生产环境使用',
                'keywords': ['open-source', 'community', 'production-ready']
            }
        else:
            return {
                'summary': '优质开源项目，提供实用的技术解决方案',
                'reason': '在特定领域具有创新性和实用价值',
                'keywords': ['open-source', 'innovative', 'useful']
            }

def render_article(title, greeting, resources, date_str):
    """渲染完整文章"""
    lines = []
    
    # 标题
    lines.append(f"# {title}")
    lines.append("")
    
    # 开场白
    lines.append(f"> {greeting}")
    lines.append("")
    lines.append("---")
    lines.append("")
    
    # 资源推荐
    lines.append("#### 今日资源推荐")
    lines.append("")
    
    for resource in resources:
        name = resource.get('name', '未知资源')
        stars = resource.get('stars', 0)
        url = resource.get('url', '#')
        ai_content = resource.get('ai_content', {})
        
        summary = ai_content.get('summary', '优质开源项目')
        reason = ai_content.get('reason', '社区认可度高')
        keywords = ai_content.get('keywords', [])
        
        star_str = f" ⭐{stars:,}" if stars > 0 else ""
        lines.append(f"- **{name}**{star_str}")
        lines.append(f"  - 简介：{summary}")
        lines.append(f"  - 推荐理由：{reason}")
        
        # 添加标签
        if keywords:
            filtered = [kw for kw in keywords if len(kw) > 1]
            if filtered:
                lines.append(f"  - 标签：{', '.join(filtered[:3])}")
        
        lines.append(f"  - 获取：<{url}>")
        lines.append("")
    
    # 结束语
    lines.append("> 更多实用资源，敬请关注！")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("Trigger: 自动构建")
    
    return "\n".join(lines)

def get_resources_for_date(date_str):
    """获取指定日期的资源列表（模拟）"""
    # 这里可以从resources.json读取，或者使用预定义的高质量资源
    all_resources = [
        {'name': 'pathwaycom/pathway', 'stars': 62720, 'url': 'https://github.com/pathwaycom/pathway'},
        {'name': 'toeverything/AFFiNE', 'stars': 66632, 'url': 'https://github.com/toeverything/AFFiNE'},
        {'name': 'sherlock-project/sherlock', 'stars': 74104, 'url': 'https://github.com/sherlock-project/sherlock'},
        {'name': 'facebook/react', 'stars': 244227, 'url': 'https://github.com/facebook/react'},
        {'name': 'microsoft/ML-For-Beginners', 'stars': 84783, 'url': 'https://github.com/microsoft/ML-For-Beginners'},
        {'name': 'scikit-learn/scikit-learn', 'stars': 60000, 'url': 'https://github.com/scikit-learn/scikit-learn'},
        {'name': 'yt-dlp/yt-dlp', 'stars': 90000, 'url': 'https://github.com/yt-dlp/yt-dlp'},
        {'name': 'angular/angular', 'stars': 96000, 'url': 'https://github.com/angular/angular'},
        {'name': 'Significant-Gravitas/AutoGPT', 'stars': 168000, 'url': 'https://github.com/Significant-Gravitas/AutoGPT'},
        {'name': 'n8n-io/n8n', 'stars': 52000, 'url': 'https://github.com/n8n-io/n8n'},
        {'name': 'x1xhlol/system-prompts-and-models-of-ai-tools', 'stars': 133473, 'url': 'https://github.com/x1xhlol/system-prompts-and-models-of-ai-tools'},
    ]
    
    # 根据日期选择3个资源（固定种子保证可重复性）
    import hashlib
    seed = int(hashlib.md5(date_str.encode()).hexdigest(), 16)
    random.seed(seed)
    selected = random.sample(all_resources, min(3, len(all_resources)))
    random.seed()  # 重置随机种子
    
    # 为每个资源生成AI内容
    for resource in selected:
        resource['ai_content'] = generate_formal_summary(resource['name'], resource['stars'])
    
    return selected

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
        print(f"   错误: {response.text[:200]}")
        return False

def main():
    # 配置
    token = get_github_token()
    repo = get_repo()
    
    # 生成从3月7日到3月28日的日期列表
    start_date = datetime(2026, 3, 7)
    end_date = datetime(2026, 3, 28)
    
    dates = []
    current = start_date
    while current <= end_date:
        dates.append(current.strftime('%Y-%m-%d'))
        current += timedelta(days=1)
    
    print(f"🚀 开始批量发布到 {repo}")
    print(f"📊 共 {len(dates)} 篇文章 (2026-03-07 到 2026-03-28)")
    print()
    
    success_count = 0
    fail_count = 0
    
    for i, date_str in enumerate(dates, 1):
        print(f"[{i}/{len(dates)}] 处理: {date_str}")
        
        try:
            # 获取资源
            resources = get_resources_for_date(date_str)
            
            # 生成标题和祝福语
            title = generate_akuma_title(date_str, len(resources))
            greeting = generate_akuma_greeting(date_str)
            
            # 渲染文章
            body = render_article(title, greeting, resources, date_str)
            
            # Issue标题
            issue_title = f"[Update] 今日免费资源推荐 - {date_str}"
            
            # 设置标签
            labels = ["免费资源", "构建成功", "made by ai"]
            
            # 创建Issue
            if create_github_issue(issue_title, body, labels, token, repo):
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
    
    if fail_count == 0:
        print("\n🎉 所有文章已成功发布到GitHub Issues!")
        print("网站将在几分钟后自动更新。")

if __name__ == '__main__':
    main()
