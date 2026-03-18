#!/usr/bin/env python3
"""
generate_greeting.py
每日祝福语生成模块。

用法：
    python generate_greeting.py [--date 2026-03-18] [--keywords kw1,kw2] [--theme 主题]

输出：一行中文祝福语，写入 stdout，同时写入 state/greeting_today.txt。
"""

import os
import sys
import json
import argparse
import logging
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_DIR = os.path.join(SCRIPT_DIR, "state")
GREETING_PATH = os.path.join(STATE_DIR, "greeting_today.txt")

_WEEKDAY_ZH = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def build_context(date_str: str = "", keywords: list = None, theme: str = "") -> dict:
    if date_str:
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            dt = datetime.now()
    else:
        dt = datetime.now()

    weekday_num = dt.weekday()  # 0=Monday
    weekday = _WEEKDAY_ZH[weekday_num]
    is_workday = weekday_num < 5

    return {
        "date": dt.strftime("%Y-%m-%d"),
        "weekday": weekday,
        "weekday_num": weekday_num,
        "is_workday": is_workday,
        "theme": theme or "技术资源",
        "keywords": keywords or [],
    }


def generate(date_str: str = "", keywords: list = None, theme: str = "") -> str:
    """生成祝福语并缓存到文件，返回祝福语字符串。"""
    os.makedirs(STATE_DIR, exist_ok=True)

    # 当天已生成则直接复用
    today = (date_str or datetime.now().strftime("%Y-%m-%d"))
    if os.path.exists(GREETING_PATH):
        try:
            with open(GREETING_PATH, "r", encoding="utf-8") as f:
                cached = json.load(f)
            if cached.get("date") == today and cached.get("greeting"):
                logger.info("[Greeting] 复用今日已生成祝福语。")
                return cached["greeting"]
        except Exception:
            pass

    # 导入客户端（延迟导入，避免循环依赖）
    try:
        from modelscope_client import ModelScopeClient
        client = ModelScopeClient()
    except ImportError:
        logger.error("[Greeting] 无法导入 ModelScopeClient，使用本地模板。")
        client = None

    context = build_context(date_str, keywords, theme)

    if client:
        greeting = client.generate_greeting(context)
    else:
        from modelscope_client import _fallback_greeting
        greeting = _fallback_greeting(context)

    # 写入缓存
    try:
        tmp = GREETING_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"date": today, "greeting": greeting}, f, ensure_ascii=False)
        os.replace(tmp, GREETING_PATH)
    except Exception as e:
        logger.warning(f"[Greeting] 缓存写入失败: {e}")

    return greeting


def main():
    parser = argparse.ArgumentParser(description="生成每日祝福语")
    parser.add_argument("--date", default="", help="日期 YYYY-MM-DD，默认今天")
    parser.add_argument("--keywords", default="", help="关键词，逗号分隔")
    parser.add_argument("--theme", default="", help="今日主题")
    args = parser.parse_args()

    keywords = [k.strip() for k in args.keywords.split(",") if k.strip()]
    greeting = generate(args.date, keywords, args.theme)
    print(greeting)


if __name__ == "__main__":
    main()
