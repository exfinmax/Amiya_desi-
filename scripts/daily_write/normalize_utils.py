#!/usr/bin/env python3
"""
normalize_utils.py
URL 标准化、title hash、content hash、轻量标题相似度去重工具。
"""

import re
import hashlib
from urllib.parse import urlparse, urlunparse, urlencode, parse_qsl


# 需要剥离的追踪参数前缀
_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "ref", "referrer", "fbclid", "gclid", "mc_cid", "mc_eid",
    "_ga", "yclid", "zanpid", "dclid",
}


def normalize_url(url: str) -> str:
    """
    标准化 URL：
    1. 去除追踪参数（utm_* 等）
    2. 去除 fragment（#...）
    3. 规范尾部斜杠（路径为空时保留 /，否则去掉末尾 /）
    4. 小写 scheme 和 host
    """
    if not url:
        return ""
    try:
        parsed = urlparse(url.strip())
        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()
        path = parsed.path.rstrip("/") or "/"
        # 过滤追踪参数
        qs = [(k, v) for k, v in parse_qsl(parsed.query)
              if k.lower() not in _TRACKING_PARAMS]
        query = urlencode(qs)
        # 去掉 fragment
        normalized = urlunparse((scheme, netloc, path, "", query, ""))
        return normalized
    except Exception:
        return url


def title_hash(title: str) -> str:
    """对标题做 sha256，用于快速去重。"""
    cleaned = re.sub(r"\s+", " ", (title or "").strip().lower())
    return hashlib.sha256(cleaned.encode("utf-8")).hexdigest()


def content_hash(title: str, description: str) -> str:
    """对 title+description 联合做 sha256。"""
    combined = (title or "").strip().lower() + "|" + (description or "").strip().lower()
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()


def url_hash(url: str) -> str:
    return hashlib.sha256(normalize_url(url).encode("utf-8")).hexdigest()


# ── 轻量标题相似度 ────────────────────────────────────────────────────────────

def _tokenize(text: str) -> set:
    """简单分词：按非字母数字汉字切分，过滤短词。"""
    tokens = re.findall(r"[\u4e00-\u9fff]+|[a-zA-Z0-9]+", text.lower())
    return {t for t in tokens if len(t) > 1}


def title_similarity(a: str, b: str) -> float:
    """
    Jaccard 相似度，范围 [0, 1]。
    > 0.6 认为是重复。
    """
    ta = _tokenize(a)
    tb = _tokenize(b)
    if not ta and not tb:
        return 1.0
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    union = len(ta | tb)
    return inter / union


def is_duplicate_title(new_title: str, existing_titles: list, threshold: float = 0.6) -> bool:
    """判断 new_title 是否与 existing_titles 中任意一条过于相似。"""
    for t in existing_titles:
        if title_similarity(new_title, t) >= threshold:
            return True
    return False
