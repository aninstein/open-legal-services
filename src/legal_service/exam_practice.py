"""Original AI practice questions. Answers remain on the server until submission."""

from __future__ import annotations

import json
import os
import random
import re
from typing import Any

import httpx

from agent_foundation.config import selected_model

SUBJECTS = ("民法", "刑法", "行政法", "民事诉讼法", "刑事诉讼法", "商法", "宪法", "劳动与社会保障法")


class GenerationError(Exception):
    """The model failed to return a usable practice question."""


def _parse_question(raw: str, subject: str, kind: str, model_name: str) -> dict[str, Any]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.S)
        if not match:
            raise GenerationError("模型未返回可读取的题目") from None
        try:
            data = json.loads(match.group())
        except json.JSONDecodeError as exc:
            raise GenerationError("模型题目格式无效") from exc
    if not isinstance(data, dict):
        raise GenerationError("模型题目格式无效")
    stem = data.get("stem")
    options = data.get("options")
    answer = data.get("answer_keys")
    explanation = data.get("explanation")
    knowledge = data.get("knowledge_point")
    if not isinstance(stem, str) or not 15 <= len(stem.strip()) <= 800:
        raise GenerationError("题干不完整")
    if isinstance(options, list) and len(options) == 4:
        options = dict(zip("ABCD", options))
    if not isinstance(options, dict) or set(options) != {"A", "B", "C", "D"}:
        raise GenerationError("选项格式无效")
    if any(not isinstance(value, str) or not 2 <= len(value.strip()) <= 300 for value in options.values()):
        raise GenerationError("选项不完整")
    if len(set(value.strip() for value in options.values())) != 4:
        raise GenerationError("选项重复")
    if not isinstance(answer, list) or not all(key in {"A", "B", "C", "D"} for key in answer):
        raise GenerationError("答案格式无效")
    keys = sorted(set(answer))
    if len(keys) != len(answer) or (kind == "single" and len(keys) != 1) or (kind == "multiple" and len(keys) not in {2, 3}):
        raise GenerationError("答案数量与题型不符")
    if not isinstance(explanation, str) or not 15 <= len(explanation.strip()) <= 1000:
        raise GenerationError("解析不完整")
    if not isinstance(knowledge, str) or not 2 <= len(knowledge.strip()) <= 80:
        raise GenerationError("考点不完整")
    return {"subject": subject, "kind": kind, "stem": stem.strip(),
            "options": {key: options[key].strip() for key in "ABCD"},
            "answer_keys": keys, "explanation": explanation.strip(),
            "knowledge_point": knowledge.strip(), "model_name": model_name}


async def generate_question(subject: str) -> dict[str, Any]:
    """Generate one original question using the configured foundation model."""
    model = selected_model()
    if model.provider != "openai":
        raise GenerationError("模拟法考请配置在线模型")
    chosen_subject = random.choice(SUBJECTS) if subject == "随机" else subject
    kind = random.choice(("single", "multiple"))
    kind_label = "单选，正确选项恰好一个" if kind == "single" else "多选，正确选项恰好两个或三个"
    system = (
        "你是中国国家统一法律职业资格考试的练习题命题助手。只生成原创的中国大陆法律客观题，"
        "不要复述或冒充历年真题。题意、选项和答案必须自洽，避免争议或依赖刚变动的具体法条。"
        "不要捏造法条编号、判例编号或官方来源。仅返回一个 JSON 对象，不要 Markdown。"
    )
    prompt = (
        f"科目：{chosen_subject}；题型：{kind_label}。编写一道有简短事实情境的练习题。"
        "JSON 键为 stem（题干不少于15字）、options（A/B/C/D 四个互不重复的选项文本，不含字母前缀）、"
        "answer_keys（正确选项字母数组）、explanation（说明正确理由及主要干扰项为何错误，至少15字）、"
        "knowledge_point（简短考点）。不要在题干或选项中透露答案。"
    )
    timeout = httpx.Timeout(90.0, connect=10.0)
    last_error: Exception | None = None
    async with httpx.AsyncClient(timeout=timeout) as client:
        for _ in range(2):
            try:
                response = await client.post(f"{model.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {model.secret(os.environ)}"},
                    json={"model": model.model, "temperature": max(0.45, model.temperature),
                          "messages": [{"role": "system", "content": system},
                                       {"role": "user", "content": prompt}]})
                response.raise_for_status()
                raw = response.json()["choices"][0]["message"]["content"]
                return _parse_question(raw, chosen_subject, kind, model.model)
            except (httpx.HTTPError, KeyError, TypeError, ValueError, GenerationError) as exc:
                last_error = exc
                continue
    raise GenerationError("AI 暂时无法生成合格题目，请稍后重试") from last_error
