#!/usr/bin/env python3
"""
content_enricher.py
对 Top N 候选资源批量调用 AI 摘要，优先复用 registry 中已有摘要。
"""

import logging
from typing import List

logger = logging.getLogger(__name__)


def enrich_resources(resources: List[dict], registry=None, dry_run: bool = False) -> List[dict]:
    """
    对资源列表批量生成摘要。
    - 优先复用 registry 中已有摘要
    - dry_run=True 时跳过 AI 调用，使用规则摘要

    返回带 summary/reason/audience/keywords 字段的资源列表。
    """
    try:
        from modelscope_client import ModelScopeClient, _rule_summary
        client = ModelScopeClient()
    except ImportError:
        logger.error("[Enricher] 无法导入 ModelScopeClient，全部使用规则摘要。")
        from modelscope_client import _rule_summary
        client = None

    enriched = []
    for res in resources:
        url = res.get("url", "")

        # 优先复用 registry 已有摘要
        if registry and registry.has_summary(url):
            cached = registry.get_summary(url)
            res = {**res, **cached}
            logger.info(f"[Enricher] 复用已有摘要: {res.get('title', '')[:30]}")
            enriched.append(res)
            continue

        # dry_run 或无客户端 → 规则摘要
        if dry_run or client is None:
            from modelscope_client import _rule_summary
            summary_dict = _rule_summary(res)
        else:
            summary_dict = client.generate_summary(res)

        res = {**res, **summary_dict}

        # 写回 registry
        if registry:
            registry.update_summary(url, summary_dict)

        enriched.append(res)

    return enriched
