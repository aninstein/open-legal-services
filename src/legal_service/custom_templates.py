"""Administrator supplied conversational Word templates."""

from __future__ import annotations

import json
import re
import uuid

from fastapi import HTTPException
from pydantic import BaseModel, Field

from .db import audit, connection, utcnow

KEY = re.compile(r"^[a-z][a-z0-9_]{1,39}$")
PLACEHOLDER = re.compile(r"\{([a-z][a-z0-9_]*)\}")


class TemplateField(BaseModel):
    key: str
    label: str = Field(min_length=2, max_length=60)
    level: str


class TemplateInput(BaseModel):
    category: str = Field(min_length=2, max_length=40)
    title: str = Field(min_length=3, max_length=80)
    purpose: str = Field(min_length=5, max_length=300)
    fields: list[TemplateField] = Field(min_length=1, max_length=30)
    paragraphs: list[str] = Field(min_length=1, max_length=30)
    source_url: str | None = Field(default=None, max_length=500)


def validate(body: TemplateInput) -> tuple[list[dict], list[str]]:
    fields = [field.model_dump() for field in body.fields]
    keys = [field["key"] for field in fields]
    if len(set(keys)) != len(keys) or not all(KEY.fullmatch(key) for key in keys):
        raise HTTPException(422, "字段键须唯一，使用小写英文字母、数字和下划线")
    if not any(field["level"] == "required" for field in fields):
        raise HTTPException(422, "至少设置一项必填信息")
    if any(field["level"] not in {"required", "recommended", "optional"} for field in fields):
        raise HTTPException(422, "字段级别无效")
    paragraphs = [part.strip() for part in body.paragraphs]
    if any(not 10 <= len(part) <= 3000 for part in paragraphs):
        raise HTTPException(422, "每段草稿正文须为 10–3000 字")
    used = set(PLACEHOLDER.findall("\n".join(paragraphs)))
    if not used.issubset(keys):
        raise HTTPException(422, "草稿中含未定义的占位符：" + "、".join(sorted(used - set(keys))))
    for part in paragraphs:
        remaining = PLACEHOLDER.sub("", part)
        if "{" in remaining or "}" in remaining:
            raise HTTPException(422, "占位符格式应为 {field_key}")
    if body.source_url and not body.source_url.startswith("https://"):
        raise HTTPException(422, "参考来源须使用 HTTPS 地址")
    return fields, paragraphs


def make_prompt(body: TemplateInput, fields: list[dict]) -> str:
    labels = lambda level: "、".join(field["label"] for field in fields if field["level"] == level) or "无"
    return (f"你正在协助起草《{body.title}》。用途：{body.purpose}。用自然对话询问用户，不呈现表单。"
            f"必填：{labels('required')}；缺少时继续追问。"
            f"非常建议：{labels('recommended')}；缺少时保留【待确认】。"
            f"选填：{labels('optional')}；仅相关时询问。"
            "只采纳用户明确给出的事实，不编造姓名、日期、金额或法律结论；不要索取无关敏感资料。"
            "生成可编辑 Word 后提醒核对事实、证据及现行规则。")


def create(body: TemplateInput, actor_id: str) -> str:
    fields, paragraphs = validate(body)
    template_id, now = "custom-" + uuid.uuid4().hex, utcnow()
    with connection() as con:
        con.execute("""INSERT INTO custom_document_templates
            (id,category,title,purpose,fields_json,paragraphs_json,intake_prompt,source_url,created_by,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (template_id, body.category.strip(), body.title.strip(), body.purpose.strip(),
             json.dumps(fields, ensure_ascii=False), json.dumps(paragraphs, ensure_ascii=False),
             make_prompt(body, fields), body.source_url, actor_id, now, now))
        audit(con, actor_id, "create", "custom_document_template", template_id)
    return template_id


def list_items(q: str = "", category: str = "", *, include_inactive: bool = False) -> list[dict]:
    with connection() as con:
        sql = "SELECT * FROM custom_document_templates WHERE 1=1" if include_inactive else "SELECT * FROM custom_document_templates WHERE active=1"
        params: list[str] = []
        if category:
            sql += " AND category=?"; params.append(category)
        if q:
            sql += " AND (title LIKE ? OR purpose LIKE ? OR category LIKE ?)"
            params.extend([f"%{q}%"] * 3)
        sql += " ORDER BY created_at DESC LIMIT 100"
        rows = con.execute(sql, params).fetchall()
    return [_decode(row) for row in rows]


def _decode(row) -> dict:
    return {"id": row["id"], "category": row["category"], "title": row["title"],
            "purpose": row["purpose"], "fields": json.loads(row["fields_json"]),
            "paragraphs": json.loads(row["paragraphs_json"]), "intake_prompt": row["intake_prompt"],
            "source_url": row["source_url"], "kind": "word", "active": bool(row["active"])}


def get(template_id: str) -> dict:
    with connection() as con:
        row = con.execute("SELECT * FROM custom_document_templates WHERE id=?", (template_id,)).fetchone()
    if not row:
        raise HTTPException(404, "文书场景不存在")
    return _decode(row)
