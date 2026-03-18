#!/usr/bin/env python3
"""
resource_registry.py
结构化资源注册表，替代 posted_urls.txt，支持去重、状态追踪、原子写入。

注册表文件：scripts/daily_write/state/resource_registry.json
"""

import os
import json
import logging
import shutil
from datetime import datetime, timezone
from typing import Optional

from normalize_utils import normalize_url, title_hash, content_hash, url_hash, is_duplicate_title

logger = logging.getLogger(__name__)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_DIR = os.path.join(SCRIPT_DIR, "state")
REGISTRY_PATH = os.path.join(STATE_DIR, "resource_registry.json")

# 资源状态枚举
STATUS_NEW = "new"
STATUS_SELECTED = "selected"
STATUS_SENT = "sent"
STATUS_DUPLICATE = "duplicate"
STATUS_SKIPPED = "skipped"

_EMPTY_REGISTRY = {"version": 1, "resources": {}}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_raw() -> dict:
    """加载注册表，损坏时自动恢复为空结构并备份旧文件。"""
    os.makedirs(STATE_DIR, exist_ok=True)
    if not os.path.exists(REGISTRY_PATH):
        return dict(_EMPTY_REGISTRY)
    try:
        with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict) or "resources" not in data:
            raise ValueError("格式不合法")
        return data
    except Exception as e:
        logger.error(f"[Registry] 注册表损坏，自动恢复: {e}")
        backup = REGISTRY_PATH + f".bak.{int(datetime.now().timestamp())}"
        try:
            shutil.copy2(REGISTRY_PATH, backup)
            logger.info(f"[Registry] 旧文件已备份至 {backup}")
        except Exception:
            pass
        return dict(_EMPTY_REGISTRY)


def _save_raw(data: dict):
    """原子写入注册表。"""
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = REGISTRY_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, REGISTRY_PATH)


class ResourceRegistry:
    """
    资源注册表操作类。

    每条记录的 key 为 url_hash（标准化 URL 的 sha256）。
    字段：
      id, title, raw_url, normalized_url, source,
      published, fetched_at, title_hash, content_hash,
      summary, reason, tags, score, status,
      first_seen_date, sent_date, duplicate_of
    """

    def __init__(self):
        self._data = _load_raw()

    @property
    def resources(self) -> dict:
        return self._data.setdefault("resources", {})

    def save(self):
        _save_raw(self._data)

    # ── 查询 ──────────────────────────────────────────────────────────────────

    def get_by_url(self, url: str) -> Optional[dict]:
        key = url_hash(url)
        return self.resources.get(key)

    def get_sent_urls(self) -> set:
        return {r["normalized_url"] for r in self.resources.values()
                if r.get("status") == STATUS_SENT}

    def get_sent_titles(self) -> list:
        return [r["title"] for r in self.resources.values()
                if r.get("status") == STATUS_SENT and r.get("title")]

    def get_all_title_hashes(self) -> set:
        return {r["title_hash"] for r in self.resources.values() if r.get("title_hash")}

    def get_all_content_hashes(self) -> set:
        return {r["content_hash"] for r in self.resources.values() if r.get("content_hash")}

    def has_summary(self, url: str) -> bool:
        rec = self.get_by_url(url)
        return bool(rec and rec.get("summary"))

    def get_summary(self, url: str) -> Optional[dict]:
        rec = self.get_by_url(url)
        if rec and rec.get("summary"):
            return {"summary": rec["summary"], "reason": rec.get("reason", ""),
                    "audience": rec.get("audience", ""), "keywords": rec.get("keywords", [])}
        return None

    # ── 写入 ──────────────────────────────────────────────────────────────────

    def upsert(self, item: dict) -> str:
        """
        插入或更新一条资源记录。
        返回该记录的 key（url_hash）。
        """
        raw_url = item.get("url", "")
        norm_url = normalize_url(raw_url)
        key = url_hash(raw_url)
        th = title_hash(item.get("title", ""))
        ch = content_hash(item.get("title", ""), item.get("description", ""))

        existing = self.resources.get(key, {})
        now = _now_iso()

        record = {
            "id": key,
            "title": item.get("title", existing.get("title", "")),
            "raw_url": raw_url,
            "normalized_url": norm_url,
            "source": item.get("source", existing.get("source", "")),
            "published": item.get("published", existing.get("published", "")),
            "fetched_at": item.get("fetched_at", existing.get("fetched_at", now)),
            "title_hash": th,
            "content_hash": ch,
            "summary": item.get("summary", existing.get("summary", "")),
            "reason": item.get("reason", existing.get("reason", "")),
            "audience": item.get("audience", existing.get("audience", "")),
            "keywords": item.get("keywords", existing.get("keywords", [])),
            "tags": item.get("tags", existing.get("tags", [])),
            "score": item.get("score", existing.get("score", 0)),
            "status": existing.get("status", STATUS_NEW),
            "first_seen_date": existing.get("first_seen_date", now[:10]),
            "sent_date": existing.get("sent_date", ""),
            "duplicate_of": existing.get("duplicate_of", ""),
        }
        self.resources[key] = record
        return key

    def mark_sent(self, url: str, sent_date: str = ""):
        key = url_hash(url)
        if key in self.resources:
            self.resources[key]["status"] = STATUS_SENT
            self.resources[key]["sent_date"] = sent_date or _now_iso()[:10]

    def mark_duplicate(self, url: str, duplicate_of: str = ""):
        key = url_hash(url)
        if key in self.resources:
            self.resources[key]["status"] = STATUS_DUPLICATE
            self.resources[key]["duplicate_of"] = duplicate_of

    def update_summary(self, url: str, summary_dict: dict):
        key = url_hash(url)
        if key in self.resources:
            self.resources[key].update({
                "summary": summary_dict.get("summary", ""),
                "reason": summary_dict.get("reason", ""),
                "audience": summary_dict.get("audience", ""),
                "keywords": summary_dict.get("keywords", []),
            })

    # ── 去重检查 ──────────────────────────────────────────────────────────────

    def is_duplicate(self, item: dict, similarity_threshold: float = 0.6) -> tuple:
        """
        三层去重：
        1. URL 标准化去重
        2. title_hash / content_hash 去重
        3. 轻量标题相似度去重

        返回 (is_dup: bool, reason: str)
        """
        raw_url = item.get("url", "")
        norm_url = normalize_url(raw_url)
        th = title_hash(item.get("title", ""))
        ch = content_hash(item.get("title", ""), item.get("description", ""))

        # 层 1：URL 去重
        for rec in self.resources.values():
            if rec.get("normalized_url") == norm_url and rec.get("status") == STATUS_SENT:
                return True, f"URL 重复: {norm_url}"

        # 层 2：hash 去重
        if th in self.get_all_title_hashes():
            # 只有已发送的才算重复
            for rec in self.resources.values():
                if rec.get("title_hash") == th and rec.get("status") == STATUS_SENT:
                    return True, f"标题 hash 重复: {th[:8]}"
        if ch in self.get_all_content_hashes():
            for rec in self.resources.values():
                if rec.get("content_hash") == ch and rec.get("status") == STATUS_SENT:
                    return True, f"内容 hash 重复: {ch[:8]}"

        # 层 3：标题相似度
        sent_titles = self.get_sent_titles()
        if is_duplicate_title(item.get("title", ""), sent_titles, similarity_threshold):
            return True, f"标题相似度过高: {item.get('title', '')[:30]}"

        return False, ""
