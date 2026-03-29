#!/usr/bin/env python3
"""
title_generator.py
AI生成每日文章标题模块

用法：
    python title_generator.py [--date 2026-03-18] [--resources json_file]

输出：一行中文标题，写入 stdout，同时写入 state/title_today.txt。
"""

import os
import sys
import json
import argparse
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_DIR = os.path.join(SCRIPT_DIR, "state")
TITLE_PATH = os.path.join(STATE_DIR, "title_today.txt")

def generate_title(date_str: str = "", resources: list = None) -> str:
    """生成文章标题并缓存到文件，返回标题字符串。"""
    os.makedirs(STATE_DIR, exist_ok=True)

    # 当天已生成则直接复用
    today = (date_str or datetime.now().strftime("%Y-%m-%d"))
    if os.path.exists(TITLE_PATH):
        try:
            with open(TITLE_PATH, "r", encoding="utf-8") as f:
                cached = json.load(f)
            if cached.get("date") == today and cached.get("title"):
                logger.info("[Title] 复用今日已生成标题。")
                return cached["title"]
        except Exception:
            pass

    # 导入客户端（延迟导入，避免循环依赖）
    try:
        from modelscope_client import ModelScopeClient
        client = ModelScopeClient()
    except ImportError:
        logger.error("[Title] 无法导入 ModelScopeClient，使用本地模板。")
        client = None

    # 构建上下文
    context = {
        "date": today,
        "resources": resources or [],
        "resource_count": len(resources or []),
    }

    if client and not client.dry_run:
        title = _generate_ai_title(client, context)
    else:
        title = _fallback_title(context)

    # 写入缓存
    try:
        tmp = TITLE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"date": today, "title": title}, f, ensure_ascii=False)
        os.replace(tmp, TITLE_PATH)
    except Exception as e:
        logger.warning(f"[Title] 缓存写入失败: {e}")

    return title

def _generate_ai_title(client: ModelScopeClient, context: dict) -> str:
    """使用AI生成标题"""
    resources = context.get("resources", [])
    resource_count = context.get("resource_count", 0)
    date = context.get("date", "")
    
    # 提取关键词
    keywords = []
    for resource in resources[:3]:  # 只取前3个资源的关键词
        keywords.extend(resource.get("keywords", []))
    keywords = list(dict.fromkeys(keywords))[:5]  # 去重取前5
    
    # 提取主题
    themes = []
    for resource in resources:
        themes.extend(resource.get("tags", []))
    theme = themes[0] if themes else "技术资源"
    
    kw_str = "、".join(keywords) if keywords else "开源、工具、AI"
    
    prompt = f"""我是Akuma站娘，一个傲娇的技术少女~ (｡•̀ᴗ-)✧

请为今日的资源推荐文章生成一个活泼的标题。

信息：
- 日期：{date}
- 资源数量：{resource_count}个
- 主要主题：{theme}
- 关键词：{kw_str}

要求：
- 中文，15~25字
- 傲娇技术少女风格，带点小恶魔气质
- 偶尔使用颜文字，如 (｡•̀ᴗ-)✧、(๑•̀ㅂ•́)و✧、(¬‿¬)
- 不要太正式，要活泼可爱
- 体现"每日推荐"的感觉
- 只输出标题，不要任何解释

示例风格：
- 今日份技术干货，本站娘帮你整理好啦~ (｡•̀ᴗ-)✧
- 哼，这些资源也就一般般啦，不过值得一看~ (๑•̀ㅂ•́)و✧"""

    messages = [
        {"role": "system", "content": "你是Akuma站娘，一个傲娇的技术少女，擅长生成活泼可爱的文章标题。"},
        {"role": "user", "content": prompt},
    ]

    raw = client.try_models(messages, client.greeting_models, temperature=0.8, max_tokens=50)
    if raw:
        # 清理多余引号和换行
        title = raw.strip().strip('"').strip("'").split("\n")[0].strip()
        if 10 <= len(title) <= 30:
            return title

    logger.warning("[Title] AI标题生成失败，使用本地模板。")
    return _fallback_title(context)

def _fallback_title(context: dict) -> str:
    """本地模板标题"""
    import random
    
    resource_count = context.get("resource_count", 3)
    date = context.get("date", "")
    
    templates = [
        f"今日份技术干货，本站娘帮你整理好啦~",
        f"哼，{resource_count}个资源也就一般般啦，不过值得一看~",
        f"本站娘精心挑选的{resource_count}个宝藏，不看是你的损失~",
        f"今日技术速递，本站娘为你打包好了~",
        f"{resource_count}个开源神器，本站娘认证推荐~",
    ]
    
    return random.choice(templates)

def main():
    parser = argparse.ArgumentParser(description="生成每日文章标题")
    parser.add_argument("--date", default="", help="日期 YYYY-MM-DD，默认今天")
    parser.add_argument("--resources", default="", help="资源JSON文件路径")
    args = parser.parse_args()

    # 加载资源
    resources = []
    if args.resources and os.path.exists(args.resources):
        try:
            with open(args.resources, "r", encoding="utf-8") as f:
                resources = json.load(f)
        except Exception as e:
            logger.warning(f"[Title] 加载资源文件失败: {e}")

    title = generate_title(args.date, resources)
    print(title)

if __name__ == "__main__":
    main()
