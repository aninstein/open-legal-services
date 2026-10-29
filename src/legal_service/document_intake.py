"""Extract only explicitly supplied facts from freeform document conversations."""
from __future__ import annotations

import json
import os
import re

import httpx
from agent_foundation.config import selected_model


class IntakeError(Exception):
    pass


async def extract(item: dict, messages: list[dict], existing: dict[str, str]) -> dict[str, str]:
    model = selected_model()
    if model.provider != "openai":
        raise IntakeError("请在环境变量中配置在线模型")
    allowed = {field["key"]: field["label"] for field in item["fields"]}
    system = ("你是文书事实提取助手。只从用户消息明确陈述的内容中提取事实；不得猜测、补充或根据问题文本虚构答案。"
              "用户明确纠正旧信息时以新信息为准。不要提取身份证号、银行卡号等与文书无关的敏感信息。"
              "只能输出一个 JSON 对象，键只能是提供的英文 key，值必须是用户给出的简短原文或忠实归纳。"
              "对于未说到的信息不要输出键。用户否认、说不确定或说跳过时不要输出对应键。")
    conversation = [{"role": message["role"], "content": message["content"]}
                    for message in messages[-12:] if message.get("role") in {"user", "assistant"}]
    task = (f"场景：{item['title']}。允许字段：{json.dumps(allowed, ensure_ascii=False)}。"
            f"已有事实：{json.dumps(existing, ensure_ascii=False)}。请从对话中的用户回答提取新增或纠正的信息，"
            "助手提问和字段说明不是事实；不得把已有事实或字段标签当作用户的新回答。输出仅为 JSON。")
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60, connect=10)) as client:
            response = await client.post(f"{model.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {model.secret(os.environ)}"},
                json={"model": model.model, "temperature": 0,
                      "messages": [{"role": "system", "content": system + task}, *conversation]})
            response.raise_for_status()
            raw = response.json()["choices"][0]["message"]["content"]
            if not isinstance(raw, str) or len(raw) > 10000:
                raise IntakeError("模型返回内容无效")
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                found = re.search(r"\{.*\}", raw, re.S)
                if not found:
                    raise IntakeError("模型未返回可读取的信息") from None
                data = json.loads(found.group())
    except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
        raise IntakeError("暂时无法提取文书信息，请稍后重试") from exc
    if not isinstance(data, dict):
        raise IntakeError("模型返回的文书信息无效")
    return {key: value.strip()[:300] for key, value in data.items()
            if key in allowed and isinstance(value, str) and value.strip() and "\n" not in value}
