"""Bounded, structured Office drafting with the configured online model."""

from __future__ import annotations

import json
import os
import re
from typing import Any

import httpx

from agent_foundation.config import selected_model


class OfficeGenerationError(Exception):
    pass


SCHEMAS = {
    "word": '返回 {"title":"标题","sections":[{"heading":"小标题","paragraphs":["正文段落"]}]}。写 2-8 节，每节 1-3 段；缺失的事实用【待确认】标记。',
    "excel": '返回 {"title":"标题","columns":["列名1","列名2"],"rows":[["单元格1","单元格2"]]}。写 3-8 列和 1-20 行，逐行列数一致；不要生成公式。',
    "ppt": '返回 {"title":"标题","slides":[{"title":"页标题","bullets":["要点"]}]}。总标题和页标题均不超过 35 字；写 3-6 页，每页 2-5 条简短要点。',
}


def _text(value: Any, *, minimum: int = 1, maximum: int = 1000) -> str:
    if not isinstance(value, str) or not minimum <= len(value.strip()) <= maximum:
        raise OfficeGenerationError("AI 返回的内容不完整")
    return value.strip()


def validate_payload(kind: str, data: Any) -> dict[str, Any]:
    if kind not in SCHEMAS or not isinstance(data, dict):
        raise OfficeGenerationError("AI 返回的文件格式无效")
    title = _text(data.get("title"), maximum=40 if kind == "ppt" else 100)
    if kind == "word":
        sections = data.get("sections")
        if not isinstance(sections, list) or not 1 <= len(sections) <= 12:
            raise OfficeGenerationError("Word 章节格式无效")
        cleaned = []
        for section in sections:
            if not isinstance(section, dict) or not isinstance(section.get("paragraphs"), list) or not 1 <= len(section["paragraphs"]) <= 5:
                raise OfficeGenerationError("Word 段落格式无效")
            cleaned.append({"heading": _text(section.get("heading", ""), minimum=0, maximum=80),
                            "paragraphs": [_text(text, maximum=1000) for text in section["paragraphs"]]})
        return {"title": title, "sections": cleaned}
    if kind == "excel":
        columns, rows = data.get("columns"), data.get("rows")
        if not isinstance(columns, list) or not 2 <= len(columns) <= 8 or not isinstance(rows, list) or not 1 <= len(rows) <= 40:
            raise OfficeGenerationError("Excel 表格结构无效")
        cols = [_text(col, maximum=40) for col in columns]
        if len(set(cols)) != len(cols):
            raise OfficeGenerationError("Excel 列名重复")
        cleaned_rows = []
        for row in rows:
            if not isinstance(row, list) or len(row) != len(cols):
                raise OfficeGenerationError("Excel 行列数不一致")
            cleaned_rows.append([_text(str(cell), minimum=0, maximum=200) if isinstance(cell, (str, int, float)) and not isinstance(cell, bool) else _text(cell, minimum=0, maximum=200) for cell in row])
        return {"title": title, "columns": cols, "rows": cleaned_rows}
    slides = data.get("slides")
    if not isinstance(slides, list) or not 1 <= len(slides) <= 8:
        raise OfficeGenerationError("PPT 页数无效")
    cleaned_slides = []
    for slide in slides:
        if not isinstance(slide, dict) or not isinstance(slide.get("bullets"), list) or not 1 <= len(slide["bullets"]) <= 6:
            raise OfficeGenerationError("PPT 页面内容无效")
        cleaned_slides.append({"title": _text(slide.get("title"), maximum=40),
                               "bullets": [_text(item, maximum=90) for item in slide["bullets"]]})
    return {"title": title, "slides": cleaned_slides}


async def generate(kind: str, prompt: str) -> dict[str, Any]:
    if kind not in SCHEMAS:
        raise OfficeGenerationError("不支持的文件类型")
    model = selected_model()
    if model.provider != "openai":
        raise OfficeGenerationError("请配置在线模型后再使用 AI 生成")
    system = (
        "你是中国大陆法律服务工作台的文件起草助手。根据用户提供的事实制作可编辑的文件草稿。"
        "不要编造当事人、金额、日期、法条编号、案例或权威来源；缺失事实标为【待确认】。"
        "法律结论保持审慎，合同条款应公平清晰；所有内容都需用户核对。只返回 JSON，不要 Markdown。"
    )
    user = f"文件类型：{kind}。用户需求：{prompt}\n{SCHEMAS[kind]}"
    last_error: Exception | None = None
    async with httpx.AsyncClient(timeout=httpx.Timeout(90.0, connect=10.0)) as client:
        for _ in range(2):
            try:
                response = await client.post(f"{model.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {model.secret(os.environ)}"},
                    json={"model": model.model, "temperature": 0.3,
                          "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]})
                response.raise_for_status()
                raw = response.json()["choices"][0]["message"]["content"]
                if not isinstance(raw, str) or len(raw) > 30000:
                    raise OfficeGenerationError("AI 返回内容过长")
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    match = re.search(r"\{.*\}", raw, re.S)
                    if not match:
                        raise OfficeGenerationError("AI 未返回可读取的文件内容") from None
                    data = json.loads(match.group())
                return validate_payload(kind, data)
            except (httpx.HTTPError, KeyError, TypeError, ValueError, OfficeGenerationError) as exc:
                last_error = exc
    raise OfficeGenerationError("AI 暂时无法生成合格文件，请缩短或明确需求后重试") from last_error
