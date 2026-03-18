#!/usr/bin/env python3
"""
modelscope_client.py
ModelScope API-Inference 统一客户端，支持模型回退链、超时、重试、dry-run。

可配置候选模型（通过环境变量覆盖默认值）：
  通用大模型：
    Qwen/Qwen2.5-72B-Instruct  （默认摘要首选）
    Qwen/Qwen2.5-32B-Instruct  （默认祝福语首选）
    Qwen/Qwen2.5-14B-Instruct
    Qwen/Qwen2.5-7B-Instruct
    Qwen/Qwen2-7B-Instruct
  代码模型：
    Qwen/Qwen2.5-Coder-32B-Instruct
    Qwen/Qwen2.5-Coder-14B-Instruct
    Qwen/Qwen2.5-Coder-7B-Instruct
  推理模型：
    deepseek-ai/DeepSeek-R1
  可选扩展（以 ModelScope 当前是否支持 API-Inference 为准）：
    ZhipuAI/GLM-4 系列
    MiniMax 系列
    Moonshot/Kimi 系列

注意：以上模型并不保证在任意时刻都可通过免费 API-Inference 调用，
      是否可用以 ModelScope 模型页"支持体验/推理 API-Inference"标签为准。
"""

import os
import json
import time
import logging
from typing import Optional

try:
    import requests as _requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False

logger = logging.getLogger(__name__)

# ── 默认配置 ──────────────────────────────────────────────────────────────────
DEFAULT_BASE_URL = "https://api-inference.modelscope.cn/v1"

# 摘要回退链（从强到弱）
DEFAULT_SUMMARY_MODELS = [
    "Qwen/Qwen2.5-72B-Instruct",
    "Qwen/Qwen2.5-32B-Instruct",
    "Qwen/Qwen2.5-14B-Instruct",
    "Qwen/Qwen2.5-7B-Instruct",
]

# 祝福语回退链
DEFAULT_GREETING_MODELS = [
    "Qwen/Qwen2.5-32B-Instruct",
    "Qwen/Qwen2.5-14B-Instruct",
    "Qwen/Qwen2.5-7B-Instruct",
]

DEFAULT_TIMEOUT = 30
DEFAULT_MAX_RETRIES = 2


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, default))
    except (ValueError, TypeError):
        return default


def _env_list(key: str, default: list) -> list:
    """从环境变量读取逗号分隔的模型列表，若未设置则返回 default。"""
    val = os.environ.get(key, "").strip()
    if val:
        return [m.strip() for m in val.split(",") if m.strip()]
    return default


class ModelScopeClient:
    """
    ModelScope API-Inference 客户端。

    环境变量：
      MODELSCOPE_API_KEY       Bearer Token（缺失时 dry-run 模式）
      MODELSCOPE_BASE_URL      API 基础地址
      MODELSCOPE_MODEL_SUMMARY 摘要模型（逗号分隔回退链）
      MODELSCOPE_MODEL_GREETING 祝福语模型（逗号分隔回退链）
      ENABLE_AI_SUMMARY        1/0，默认 1
      ENABLE_AI_GREETING       1/0，默认 1
      AI_TIMEOUT_SECONDS       单次请求超时秒数
      AI_MAX_RETRIES           单模型最大重试次数
    """

    def __init__(self):
        self.api_key = os.environ.get("MODELSCOPE_API_KEY", "").strip()
        self.base_url = os.environ.get("MODELSCOPE_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
        self.timeout = _env_int("AI_TIMEOUT_SECONDS", DEFAULT_TIMEOUT)
        self.max_retries = _env_int("AI_MAX_RETRIES", DEFAULT_MAX_RETRIES)
        self.enable_summary = os.environ.get("ENABLE_AI_SUMMARY", "1") == "1"
        self.enable_greeting = os.environ.get("ENABLE_AI_GREETING", "1") == "1"
        self.dry_run = not bool(self.api_key)

        self.summary_models = _env_list("MODELSCOPE_MODEL_SUMMARY", DEFAULT_SUMMARY_MODELS)
        self.greeting_models = _env_list("MODELSCOPE_MODEL_GREETING", DEFAULT_GREETING_MODELS)

        if self.dry_run:
            logger.warning("[ModelScope] MODELSCOPE_API_KEY 未设置，进入 dry-run 模式，所有 AI 调用将返回占位结果。")

    # ── 底层 HTTP ─────────────────────────────────────────────────────────────

    def _post(self, model: str, messages: list, temperature: float = 0.4,
              max_tokens: int = 400) -> Optional[dict]:
        """向 /v1/chat/completions 发送请求，返回解析后的 JSON 或 None。"""
        if not _HAS_REQUESTS:
            logger.error("[ModelScope] requests 库未安装，无法调用 API。")
            return None

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        for attempt in range(1, self.max_retries + 2):
            try:
                resp = _requests.post(url, headers=headers, json=payload,
                                      timeout=self.timeout)
                if resp.status_code == 200:
                    try:
                        return resp.json()
                    except Exception as e:
                        logger.error(f"[ModelScope] JSON 解析失败 model={model}: {e} | 响应前500字: {resp.text[:500]}")
                        return None
                else:
                    logger.warning(
                        f"[ModelScope] model={model} attempt={attempt} "
                        f"HTTP {resp.status_code} | 响应前1000字: {resp.text[:1000]}"
                    )
                    # 429 限流 / 503 不可用 → 等待后重试
                    if resp.status_code in (429, 503) and attempt <= self.max_retries:
                        time.sleep(2 ** attempt)
                        continue
                    return None
            except Exception as e:
                logger.warning(f"[ModelScope] model={model} attempt={attempt} 请求异常: {e}")
                if attempt <= self.max_retries:
                    time.sleep(2 ** attempt)
                    continue
                return None
        return None

    def _extract_text(self, response: dict) -> Optional[str]:
        """从 chat completions 响应中提取文本内容。"""
        try:
            return response["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError):
            return None

    # ── 模型回退链 ────────────────────────────────────────────────────────────

    def try_models(self, messages: list, candidates: list,
                   temperature: float = 0.4, max_tokens: int = 400) -> Optional[str]:
        """
        依次尝试 candidates 中的模型，返回第一个成功的文本响应。
        所有模型失败时返回 None。
        """
        if self.dry_run:
            logger.info("[ModelScope] dry-run，跳过真实 API 调用。")
            return None

        for model in candidates:
            logger.info(f"[ModelScope] 尝试模型: {model}")
            resp = self._post(model, messages, temperature, max_tokens)
            if resp:
                text = self._extract_text(resp)
                if text:
                    logger.info(f"[ModelScope] 模型 {model} 调用成功。")
                    return text
            logger.warning(f"[ModelScope] 模型 {model} 失败，尝试下一档。")

        logger.error(f"[ModelScope] 所有候选模型均失败: {candidates}")
        return None

    # ── 摘要生成 ──────────────────────────────────────────────────────────────

    def generate_summary(self, resource: dict) -> dict:
        """
        为单条资源生成摘要。
        返回包含 summary / reason / audience / keywords 的 dict。
        失败时返回规则摘要。
        """
        if not self.enable_summary:
            return _rule_summary(resource)

        title = resource.get("title", "")
        description = resource.get("description", "")
        source = resource.get("source", "")
        url = resource.get("url", "")
        tags = ", ".join(resource.get("tags") or [])

        # 内容极短时直接规则摘要，不浪费 API 配额
        if len(description) < 10 and len(title) < 10:
            return _rule_summary(resource)

        prompt = _build_summary_prompt(title, description, source, url, tags)
        messages = [
            {"role": "system", "content": "你是一个专业的技术资源推荐编辑，擅长用简洁中文介绍开源项目和技术资源。"},
            {"role": "user", "content": prompt},
        ]

        raw = self.try_models(messages, self.summary_models, temperature=0.4, max_tokens=300)
        if raw:
            parsed = _parse_json_response(raw)
            if parsed and "summary" in parsed:
                return parsed

        logger.warning(f"[ModelScope] 摘要生成失败，使用规则摘要: {title}")
        return _rule_summary(resource)

    # ── 祝福语生成 ────────────────────────────────────────────────────────────

    def generate_greeting(self, context: dict) -> str:
        """
        生成每日祝福语。
        context 字段：date / weekday / theme / is_workday / keywords
        失败时返回本地模板。
        """
        if not self.enable_greeting:
            return _fallback_greeting(context)

        prompt = _build_greeting_prompt(context)
        messages = [
            {"role": "system", "content": "你是一个有技术社区气质的傲娇少女，说话温和克制，不鸡汤，不营销。"},
            {"role": "user", "content": prompt},
        ]

        raw = self.try_models(messages, self.greeting_models, temperature=0.7, max_tokens=80)
        if raw:
            # 清理多余引号和换行
            greeting = raw.strip().strip('"').strip("'").split("\n")[0].strip()
            if 10 <= len(greeting) <= 100:
                return greeting

        logger.warning("[ModelScope] 祝福语生成失败，使用本地模板。")
        return _fallback_greeting(context)

    # ── 通用 chat ─────────────────────────────────────────────────────────────

    def chat(self, messages: list, model: Optional[str] = None,
             temperature: float = 0.4, max_tokens: int = 400) -> Optional[str]:
        """通用 chat 接口，model 为 None 时使用摘要模型链首选。"""
        candidates = [model] if model else self.summary_models
        return self.try_models(messages, candidates, temperature, max_tokens)


# ── Prompt 构建 ───────────────────────────────────────────────────────────────

def _build_summary_prompt(title: str, description: str, source: str,
                           url: str, tags: str) -> str:
    return f"""请根据以下资源信息，生成一段简洁的中文推荐内容。

资源标题：{title}
资源描述：{description}
来源：{source}
链接：{url}
标签：{tags}

要求：
- 输出严格 JSON，不要有任何额外文字
- summary：一句话中文简介，18~45 字，精炼有信息量
- reason：一句中文推荐理由，12~30 字
- audience：目标受众，10 字以内
- keywords：2~4 个关键词数组
- 不要"本文介绍了""这篇文章主要讲了"
- 不要营销腔，不要空泛鸡汤
- 面向每日资源推荐场景

输出格式：
{{"summary": "...", "reason": "...", "audience": "...", "keywords": ["..."]}}"""


def _build_greeting_prompt(context: dict) -> str:
    date = context.get("date", "")
    weekday = context.get("weekday", "")
    theme = context.get("theme", "技术资源")
    is_workday = context.get("is_workday", True)
    keywords = context.get("keywords", [])
    kw_str = "、".join(keywords[:5]) if keywords else "开源、工具、学习"
    day_type = "工作日" if is_workday else "休息日"

    return f"""今天是 {date}（{weekday}，{day_type}），今日资源主题：{theme}，关键词：{kw_str}。

请生成一句每日开场白，要求：
- 中文，18~45 字
- 温和、清醒、克制
- 有技术社区气质的傲娇少女风格
- 不鸡汤过头，不像公号营销号
- 不要连续感叹号，不要过度抒情
- 只输出这一句话，不要任何解释

示例风格：
- 周三别急着追热点，先把今天真正值得看的几条内容收好。
- 今天也不必接收太多信息，挑几条有价值的慢慢看就很好。"""


# ── 规则摘要 / 本地回退 ───────────────────────────────────────────────────────

def _rule_summary(resource: dict) -> dict:
    """基于规则生成摘要，不调用 AI。"""
    title = resource.get("title", "未知资源")
    desc = resource.get("description", "")
    source = resource.get("source", "")
    stars = resource.get("stars")

    if stars and stars > 10000:
        summary = f"{title}，GitHub 上拥有 {stars:,} stars 的热门开源项目。"
    elif desc:
        summary = desc[:45].rstrip("。，,. ") + "。" if len(desc) > 45 else desc
    else:
        summary = f"{title}，值得关注的技术资源。"

    if "github" in source.lower():
        reason = "GitHub 高星项目，社区认可度高。"
    elif "scp" in source.lower():
        reason = "SCP 基金会收录条目，创意写作爱好者必看。"
    else:
        reason = "来自可靠来源，内容值得一读。"

    return {
        "summary": summary[:60],
        "reason": reason,
        "audience": "开发者",
        "keywords": _extract_keywords(title),
    }


def _extract_keywords(title: str) -> list:
    """从标题中简单提取关键词。"""
    stop = {"the", "a", "an", "of", "for", "and", "or", "in", "on", "to", "is"}
    words = [w.strip("/-") for w in title.replace("/", " ").split() if len(w) > 2]
    return [w for w in words if w.lower() not in stop][:3]


_GREETING_TEMPLATES = [
    "今天也不必接收太多信息，挑几条有价值的慢慢看就很好。",
    "别急着刷完所有内容，今天这几条值得你多停留一会儿。",
    "周{weekday}了，把今天真正值得看的几条内容收好，其余的可以先放一放。",
    "信息很多，但好内容不多。今天帮你筛了几条，慢慢看。",
    "不用每条都点开，先看标题，有感觉的再深入，这样效率更高。",
    "今天的资源不算多，但每条都经过筛选，应该不会让你失望。",
    "技术圈每天都有新东西，但真正值得花时间的并不多，今天这几条算是。",
    "周末也好，工作日也好，好内容随时都值得看一眼。",
]

_WEEKDAY_MAP = {0: "一", 1: "二", 2: "三", 3: "四", 4: "五", 5: "六", 6: "日"}


def _fallback_greeting(context: dict) -> str:
    import random
    weekday_num = context.get("weekday_num", 0)
    wday = _WEEKDAY_MAP.get(weekday_num, "")
    template = random.choice(_GREETING_TEMPLATES)
    return template.replace("{weekday}", wday)


def _parse_json_response(text: str) -> Optional[dict]:
    """从模型输出中提取 JSON，容忍 markdown 代码块包裹。"""
    if not text:
        return None
    # 去掉 ```json ... ``` 包裹
    import re
    text = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`").strip()
    # 找第一个 { ... }
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None
