#!/usr/bin/env python3
"""
render_daily_post.py
将 daily_selected.json + 祝福语 → 组装 GitHub Issue 正文。

用法：
    python render_daily_post.py [--date 2026-03-18] [--dry-run]

输出：
    stdout：Issue 正文（HTML/Markdown 混合）
    state/rendered_body.txt：同内容缓存
"""

import os
import sys
import json
import argparse
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                    handlers=[logging.StreamHandler(sys.stderr)])
logger = logging.getLogger(__name__)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_DIR = os.path.join(SCRIPT_DIR, "state")
SELECTED_PATH = os.path.join(SCRIPT_DIR, "daily_selected.json")
RENDERED_PATH = os.path.join(STATE_DIR, "rendered_body.txt")


def _load_selected() -> list:
    if os.path.exists(SELECTED_PATH) and os.path.getsize(SELECTED_PATH) > 0:
        try:
            with open(SELECTED_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"[Render] 加载 daily_selected.json 失败: {e}")
    return []


def _get_title(date_str: str, selected: list) -> str:
    try:
        from title_generator import generate_title
        return generate_title(date_str, selected)
    except Exception as e:
        logger.warning(f"[Render] 标题生成失败: {e}")
        return f"今日免费资源推荐 - {date_str}"


def _get_greeting(date_str: str, selected: list) -> str:
    try:
        keywords = []
        for it in selected:
            keywords.extend(it.get("keywords") or [])
        keywords = list(dict.fromkeys(keywords))[:5]  # 去重取前5

        # 提取今日主题
        all_tags = []
        for it in selected:
            all_tags.extend(it.get("tags") or [])
        theme = all_tags[0] if all_tags else "技术资源"

        from generate_greeting import generate
        return generate(date_str=date_str, keywords=keywords, theme=theme)
    except Exception as e:
        logger.warning(f"[Render] 祝福语生成失败: {e}")
        return "今天也不必接收太多信息，挑几条有价值的慢慢看就很好。"


def render(date_str: str = "", dry_run: bool = False) -> str:
    """组装正文，返回字符串。"""
    os.makedirs(STATE_DIR, exist_ok=True)
    today = date_str or datetime.now().strftime("%Y-%m-%d")
    selected = _load_selected()

    title = _get_title(today, selected)
    greeting = _get_greeting(today, selected)

    lines = []

    # 开场白
    lines.append(f"> {greeting}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 分离 SCP 和普通资源
    normal = [it for it in selected if "scp" not in (it.get("tags") or [])
              and "scp" not in (it.get("source") or "").lower()]
    scp = [it for it in selected if it not in normal]
    is_easter = any("easter" in (it.get("tags") or []) for it in scp)

    if is_easter and scp:
        lines.append("[点击此处前往彩蛋](#easter)")
        lines.append("")
        lines.append('<a name="easter"></a>')
        lines.append("")
        lines.append("**彩蛋专场：本篇只包含 SCP 文章，祝你好运！**")
        lines.append("")
        for it in scp:
            lines.extend(_render_item(it))
    else:
        # 普通资源
        if normal:
            lines.append("#### 今日资源推荐")
            lines.append("")
            for it in normal:
                lines.extend(_render_item(it))

        # SCP 区块
        if scp:
            lines.append("")
            lines.append("#### SCP 资源")
            lines.append("")
            for it in scp:
                lines.extend(_render_item(it))

    # 无资源降级
    if not selected:
        lines.append("#### 今日资源推荐")
        lines.append("")
        lines.append("- **资源名称：** 待填充")
        lines.append("  - 简介：占位内容")
        lines.append("  - 获取：https://example.com")
        lines.append("")

    lines.append("")
    lines.append("> 更多实用资源，敬请关注！")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("Trigger: 自动构建")

    body = "\n".join(lines)

    # 缓存
    try:
        tmp = RENDERED_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(body)
        os.replace(tmp, RENDERED_PATH)
    except Exception as e:
        logger.warning(f"[Render] 缓存写入失败: {e}")

    return body


def _render_item(it: dict) -> list:
    """渲染单条资源为 Markdown 行列表。"""
    title = (it.get("title") or "未知资源").strip()
    summary = (it.get("summary") or it.get("description") or "无简介").strip()
    reason = (it.get("reason") or "").strip()
    url = (it.get("url") or "#").strip()
    stars = it.get("stars")
    keywords = it.get("keywords", [])

    # 构建链接
    if not url or url == "#":
        if "/" in title and not title.startswith("http"):
            url = f"https://github.com/{title}"
        elif title.upper().startswith("SCP-"):
            scp_id = title.split()[0].lower()
            url = f"https://scp-wiki.wikidot.com/{scp_id}"

    lines = []
    star_str = f" ⭐{stars:,}" if stars and stars > 0 else ""
    lines.append(f"- **{title}**{star_str}")
    lines.append(f"  - 简介：{summary}")
    if reason:
        lines.append(f"  - 推荐理由：{reason}")
    
    # 只显示AI生成的关键词
    if keywords and len(keywords) > 0:
        # 过滤掉通用标签，只保留有意义的关键词
        filtered_keywords = [kw for kw in keywords if kw.lower() not in ['ai', 'tech', 'tool', 'app', 'github'] and len(kw) > 1]
        if filtered_keywords:
            lines.append(f"  - 标签：{', '.join(filtered_keywords[:3])}")
    
    lines.append(f"  - 获取：<{url}>")
    lines.append("")
    return lines


def main():
    parser = argparse.ArgumentParser(description="渲染每日资源推荐正文")
    parser.add_argument("--date", default="", help="日期 YYYY-MM-DD")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    body = render(date_str=args.date, dry_run=args.dry_run)
    
    # 输出标题和正文
    today = args.date or datetime.now().strftime("%Y-%m-%d")
    selected = _load_selected()
    title = _get_title(today, selected)
    
    print(f"# {title}")
    print(body)


if __name__ == "__main__":
    main()
