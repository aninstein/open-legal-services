"""Product API. Public reads are separated from owner and moderator writes."""

from __future__ import annotations

import json
import hashlib
from io import BytesIO
import os
import re
import sqlite3
import uuid
import asyncio
from contextlib import suppress
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, UploadFile, File
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from PIL import Image, ImageOps, UnidentifiedImageError
from dotenv import load_dotenv

from . import agent, custom_templates, documents, document_intake, document_scenarios, exam_practice, office_ai, office_files, source_sync
from .auth import (COOKIE_NAME, SESSION_DAYS, check_origin, create_session,
                   delete_session, get_session, normalize_email, register,
                   require_admin, require_user, verify_password)
from .db import audit, connection, initialize, rows, utcnow

WEB_DIR = Path(os.environ["LEGAL_WEB_DIR"]).resolve() if os.getenv("LEGAL_WEB_DIR") else Path(__file__).resolve().parents[2] / "web"
CATEGORIES = {"劳动", "企业", "行政", "民事", "其他"}
PRIVATE_MARKERS = ("身份证号", "身份证号码", "手机号", "住址", "行踪", "开房记录", "未公开案卷", "商业秘密")


class RegisterInput(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    display_name: str = Field(min_length=2, max_length=40)
    password: str = Field(min_length=12, max_length=256)


class LoginInput(BaseModel):
    email: str
    password: str


class RequestInput(BaseModel):
    title: str = Field(min_length=5, max_length=80)
    category: str
    region: str = Field(min_length=2, max_length=60)
    description: str = Field(min_length=20, max_length=2000)
    purpose: str = Field(min_length=10, max_length=500)
    reward_yuan: int = Field(ge=0, le=100000)
    deadline: str | None = None


class ReviewInput(BaseModel):
    status: str
    platform_verified: bool = False
    verification_basis: str = Field(default="", max_length=500)
    note: str = Field(default="", max_length=500)


class MessageInput(BaseModel):
    body: str = Field(min_length=10, max_length=4000)


class LawyerInput(BaseModel):
    license_no: str = Field(min_length=5, max_length=80)
    firm: str = Field(min_length=2, max_length=120)
    years: int = Field(ge=0, le=70)
    region: str = Field(min_length=2, max_length=60)
    specialties: list[str] = Field(min_length=1, max_length=5)
    social_url: str | None = Field(default=None, max_length=500)
    bio: str = Field(min_length=10, max_length=1000)
    case_summary: str = Field(default="", max_length=1000)
    legal_name: str = Field(min_length=2, max_length=40)
    gender: str = Field(default="", max_length=10)
    id_number: str = Field(min_length=15, max_length=18)
    practice_start: str = Field(min_length=10, max_length=10)
    honors: str = Field(default="", max_length=500)
    contact_phone: str = Field(min_length=7, max_length=20)


class ProfileInput(BaseModel):
    display_name: str = Field(min_length=2, max_length=40)
    email: str = Field(min_length=3, max_length=254)
    phone: str = Field(default="", max_length=20)


class PasswordInput(BaseModel):
    current_password: str
    new_password: str = Field(min_length=12, max_length=256)


class RoleInput(BaseModel):
    role: str


class LawyerReviewInput(BaseModel):
    status: str
    verification_source: str = Field(default="", max_length=500)
    note: str = Field(default="", max_length=500)


class ConversationStartInput(BaseModel):
    scenario_id: str = Field(min_length=2, max_length=80)


class ConversationMessageInput(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class DraftInput(BaseModel):
    template_id: str
    fields: dict[str, str]


class DraftUpdateInput(BaseModel):
    content: str = Field(min_length=20, max_length=30000)


class AskInput(BaseModel):
    question: str = Field(min_length=6, max_length=4000)


class MockStartInput(BaseModel):
    subject: str = "随机"
    count: int = 5


class MockAnswerInput(BaseModel):
    selected_keys: list[str] = Field(min_length=1, max_length=4)


class OfficeGenerateInput(BaseModel):
    kind: str
    prompt: str = Field(min_length=20, max_length=2000)


def mock_session_data(con: sqlite3.Connection, session_id: str, owner_id: str) -> dict:
    session = con.execute("SELECT * FROM mock_exam_sessions WHERE id=? AND owner_id=?",
                          (session_id, owner_id)).fetchone()
    if not session:
        raise HTTPException(404, "练习不存在")
    questions = con.execute("SELECT * FROM mock_exam_questions WHERE session_id=? ORDER BY position",
                            (session_id,)).fetchall()
    answered = [item for item in questions if item["answered_at"]]
    points = sum((1 if item["kind"] == "single" else 2) for item in answered if item["is_correct"])
    max_points = sum(1 if item["kind"] == "single" else 2 for item in answered)
    current = next((item for item in questions if item["position"] == session["current_position"]), None)
    question = None
    if current:
        question = {key: current[key] for key in ("id", "position", "subject", "kind", "stem", "knowledge_point")}
        question["options"] = json.loads(current["options_json"])
        question["answered"] = bool(current["answered_at"])
        if current["answered_at"]:
            question.update({"selected_keys": json.loads(current["selected_keys_json"]),
                             "answer_keys": json.loads(current["answer_keys_json"]),
                             "is_correct": bool(current["is_correct"]),
                             "explanation": current["explanation"]})
    return {"id": session["id"], "subject": session["subject"],
            "total_questions": session["total_questions"], "current_position": session["current_position"],
            "status": session["status"], "answered_count": len(answered),
            "correct_count": sum(bool(item["is_correct"]) for item in answered),
            "points": points, "graded_max_points": max_points,
            "created_at": session["created_at"], "question": question}


def public_user(session: dict) -> dict:
    return {key: session[key] for key in ("id", "email", "display_name", "role")}


def request_public(row: sqlite3.Row | dict) -> dict:
    item = dict(row)
    return {key: item[key] for key in ("id", "title", "category", "region", "description",
                                    "reward_cents", "deadline", "status", "platform_verified", "created_at")}


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(COOKIE_NAME, token, max_age=SESSION_DAYS * 86400,
                        httponly=True, secure=os.getenv("APP_COOKIE_SECURE", "false").lower() == "true",
                        samesite="lax", path="/")
    response.headers["Cache-Control"] = "no-store"


@asynccontextmanager
async def lifespan(_: FastAPI):
    load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
    initialize()
    task = asyncio.create_task(source_sync.daily_loop()) if os.getenv("APP_SYNC_ENABLED", "true").lower() == "true" else None
    try:
        yield
    finally:
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


def create_app() -> FastAPI:
    app = FastAPI(title="法寻 API", version="0.1.0", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(WEB_DIR / "index.html", headers={"Cache-Control": "no-store"})

    @app.get("/healthz")
    def health():
        return {"ok": True}

    @app.get("/api/v1/auth/me")
    def me(request: Request):
        session = get_session(request)
        return {"user": public_user(session) if session else None,
                "csrf_token": session["csrf_token"] if session else None}

    @app.post("/api/v1/auth/register", status_code=201)
    def register_route(body: RegisterInput, request: Request, response: Response):
        check_origin(request)
        user = register(body.email, body.display_name, body.password)
        token, csrf = create_session(user["id"])
        set_session_cookie(response, token)
        return {"user": user, "csrf_token": csrf}

    @app.post("/api/v1/auth/login")
    def login(body: LoginInput, request: Request, response: Response):
        check_origin(request)
        email = normalize_email(body.email)
        with connection() as con:
            row = con.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if not row or not verify_password(body.password, row["password_hash"]):
            raise HTTPException(401, "邮箱或密码错误")
        token, csrf = create_session(row["id"])
        set_session_cookie(response, token)
        return {"user": {key: row[key] for key in ("id", "email", "display_name", "role")},
                "csrf_token": csrf}

    @app.post("/api/v1/auth/logout")
    def logout(request: Request, response: Response, user: dict = Depends(require_user)):
        delete_session(request)
        response.delete_cookie(COOKIE_NAME, path="/")
        return {"ok": True}

    @app.get("/api/v1/profile")
    def profile(user: dict = Depends(require_user)):
        with connection() as con:
            row = con.execute("SELECT id,email,display_name,phone,role,created_at FROM users WHERE id=?", (user["id"],)).fetchone()
        return dict(row)

    @app.put("/api/v1/profile")
    def update_profile(body: ProfileInput, user: dict = Depends(require_user)):
        email = normalize_email(body.email)
        phone = re.sub(r"[\s-]", "", body.phone)
        if phone and not re.fullmatch(r"\+?\d{7,15}", phone):
            raise HTTPException(422, "请输入有效电话号码")
        with connection() as con:
            try:
                con.execute("UPDATE users SET email=?,display_name=?,phone=? WHERE id=?",
                            (email, body.display_name.strip(), phone, user["id"]))
            except sqlite3.IntegrityError as exc:
                raise HTTPException(409, "邮箱已被其他账户使用") from exc
            audit(con, user["id"], "update", "profile", user["id"])
        return {"id": user["id"], "email": email, "display_name": body.display_name.strip(), "phone": phone, "role": user["role"]}

    @app.put("/api/v1/profile/password")
    def change_password(body: PasswordInput, request: Request, user: dict = Depends(require_user)):
        from .auth import hash_password
        with connection() as con:
            row = con.execute("SELECT password_hash FROM users WHERE id=?", (user["id"],)).fetchone()
            if not row or not verify_password(body.current_password, row["password_hash"]):
                raise HTTPException(403, "当前密码不正确")
            con.execute("UPDATE users SET password_hash=? WHERE id=?", (hash_password(body.new_password), user["id"]))
            con.execute("DELETE FROM sessions WHERE user_id=? AND token_hash!=?", (user["id"],
                        hashlib.sha256(request.cookies.get(COOKIE_NAME, "").encode()).hexdigest()))
            audit(con, user["id"], "change_password", "user", user["id"])
        return {"ok": True}

    @app.get("/api/v1/sources")
    def sources(q: str = Query(default="", max_length=100), kind: str = Query(default="", max_length=30)):
        sql = "SELECT id,kind,title,authority,url,summary,jurisdiction,verified_at,access_policy FROM sources WHERE 1=1"
        params: list[str] = []
        if kind:
            sql += " AND kind=?"; params.append(kind)
        if q.strip():
            sql += " AND (title LIKE ? OR summary LIKE ? OR authority LIKE ?)"
            pattern = f"%{q.strip()}%"; params.extend([pattern] * 3)
        sql += " ORDER BY kind,title LIMIT 60"
        with connection() as con:
            return {"items": rows(con.execute(sql, params).fetchall())}

    @app.get("/api/v1/official-updates")
    def official_updates(q: str = Query(default="", max_length=100), kind: str = Query(default="", max_length=20)):
        if kind and kind not in source_sync.FEEDS:
            raise HTTPException(422, "来源类型无效")
        sql = "SELECT kind,title,source_url,authority,published_at,discovered_at,summary FROM official_updates WHERE 1=1"
        params: list[str] = []
        if kind:
            sql += " AND kind=?"; params.append(kind)
        if q.strip():
            sql += " AND title LIKE ?"; params.append(f"%{q.strip()}%")
        sql += " ORDER BY COALESCE(published_at,discovered_at) DESC,discovered_at DESC LIMIT 100"
        with connection() as con:
            return {"items": rows(con.execute(sql, params).fetchall())}

    @app.get("/api/v1/official-updates/status")
    def official_sync_status():
        with connection() as con:
            return {"items": rows(con.execute("""SELECT s.* FROM sync_runs s JOIN
                      (SELECT source_key,MAX(run_day) AS day FROM sync_runs GROUP BY source_key) x
                      ON x.source_key=s.source_key AND x.day=s.run_day ORDER BY s.source_key""").fetchall())}

    @app.post("/api/v1/admin/official-updates/sync")
    async def admin_sync_sources(user: dict = Depends(require_admin)):
        results = await asyncio.to_thread(source_sync.sync_all, force=True)
        with connection() as con:
            audit(con, user["id"], "manual_sync", "official_updates", utcnow()[:10])
        return {"items": results}

    @app.get("/api/v1/companies/search")
    def company_search(q: str = Query(min_length=2, max_length=100)):
        # The national register requires a human-authenticated lookup. Never invent a result.
        return {"query": q.strip(), "status": "official_login_required", "items": [],
                "source_title": "国家企业信用信息公示系统", "source_url": "https://www.gsxt.gov.cn/",
                "message": "当前未接入获授权的企业登记数据接口。请在官方公示系统实名查询企业名称或统一社会信用代码，核对登记、股东与出资信息。"}

    @app.post("/api/v1/agent/ask")
    async def ask(body: AskInput, user: dict = Depends(require_user)):
        try:
            return await agent.answer(body.question.strip(), user["id"])
        except Exception as exc:
            raise HTTPException(502, f"Agent 暂时不可用（{type(exc).__name__}）") from exc

    @app.get("/api/v1/documents/scenarios")
    def list_document_scenarios(q: str = "", category: str = ""):
        return {"items": document_scenarios.list_scenarios(q[:100], category[:60])}

    @app.get("/api/v1/documents/scenarios/{scenario_id}")
    def get_document_scenario(scenario_id: str):
        item = document_scenarios.get_scenario(scenario_id)
        return {key: value for key, value in item.items() if key != "paragraphs"}

    @app.get("/api/v1/admin/document-templates")
    def admin_templates(user: dict = Depends(require_admin)):
        return {"items": custom_templates.list_items(include_inactive=True)}

    @app.post("/api/v1/admin/document-templates", status_code=201)
    def admin_create_template(body: custom_templates.TemplateInput, user: dict = Depends(require_admin)):
        return {"id": custom_templates.create(body, user["id"])}

    @app.patch("/api/v1/admin/document-templates/{template_id}/archive")
    def admin_archive_template(template_id: str, user: dict = Depends(require_admin)):
        with connection() as con:
            updated = con.execute("UPDATE custom_document_templates SET active=0,updated_at=? WHERE id=? AND active=1",
                                  (utcnow(), template_id))
            if not updated.rowcount:
                raise HTTPException(404, "模板不存在")
            audit(con, user["id"], "archive", "custom_document_template", template_id)
        return {"ok": True}

    @app.post("/api/v1/documents/conversations", status_code=201)
    def start_document_conversation(body: ConversationStartInput, user: dict = Depends(require_user)):
        item = document_scenarios.get_scenario(body.scenario_id)
        if not item.get("active", True):
            raise HTTPException(404, "文书场景已归档")
        conversation_id, now = uuid.uuid4().hex, utcnow()
        messages = [{"role": "assistant", "content": document_scenarios.intake_question(item)}]
        with connection() as con:
            con.execute("INSERT INTO document_conversations(id,owner_id,scenario_id,facts_json,messages_json,created_at,updated_at) VALUES (?,?,?,?,?,?,?)",
                        (conversation_id, user["id"], item["id"], "{}", json.dumps(messages, ensure_ascii=False), now, now))
            audit(con, user["id"], "start", "document_conversation", conversation_id)
        return {"id": conversation_id, "scenario_id": item["id"], "title": item["title"],
                "messages": messages, "draft_id": None, "artifact_id": None, "kind": item["kind"]}

    @app.get("/api/v1/documents/conversations")
    def list_document_conversations(user: dict = Depends(require_user)):
        with connection() as con:
            data = rows(con.execute("SELECT id,scenario_id,draft_id,artifact_id,created_at,updated_at FROM document_conversations WHERE owner_id=? ORDER BY updated_at DESC LIMIT 50",
                                    (user["id"],)).fetchall())
        for row in data:
            try:
                item = document_scenarios.get_scenario(row["scenario_id"])
            except HTTPException:
                item = {"title": row["scenario_id"], "kind": "word"}
            row["title"] = item["title"]
            row["kind"] = item["kind"]
        return {"items": data}

    @app.get("/api/v1/documents/conversations/{conversation_id}")
    def read_document_conversation(conversation_id: str, user: dict = Depends(require_user)):
        with connection() as con:
            row = con.execute("SELECT id,scenario_id,facts_json,messages_json,draft_id,artifact_id,created_at,updated_at FROM document_conversations WHERE id=? AND owner_id=?",
                              (conversation_id, user["id"])).fetchone()
        if not row:
            raise HTTPException(404, "文书对话不存在")
        return {"id": row["id"], "scenario_id": row["scenario_id"],
                "title": document_scenarios.get_scenario(row["scenario_id"])["title"],
                "messages": json.loads(row["messages_json"]), "draft_id": row["draft_id"],
                "artifact_id": row["artifact_id"], "kind": document_scenarios.get_scenario(row["scenario_id"])["kind"],
                "created_at": row["created_at"], "updated_at": row["updated_at"]}

    @app.post("/api/v1/documents/conversations/{conversation_id}/messages")
    async def reply_document_conversation(conversation_id: str, body: ConversationMessageInput,
                                          user: dict = Depends(require_user)):
        with connection() as con:
            row = con.execute("SELECT * FROM document_conversations WHERE id=? AND owner_id=?",
                              (conversation_id, user["id"])).fetchone()
        if not row:
            raise HTTPException(404, "文书对话不存在")
        item = document_scenarios.get_scenario(row["scenario_id"])
        facts = json.loads(row["facts_json"])
        messages = json.loads(row["messages_json"])
        reply = body.body.strip()
        if not reply:
            raise HTTPException(422, "请告诉我这份文书的具体情况")
        if len(messages) >= 60:
            raise HTTPException(429, "这份文书的对话已达到上限，请新建对话")
        new_messages = [*messages, {"role": "user", "content": reply}]
        if reply not in {"直接生成", "生成文书", "下载文书", "跳过", "没有补充"}:
            try:
                updates = await document_intake.extract(item, new_messages, facts)
            except document_intake.IntakeError as exc:
                raise HTTPException(503, str(exc)) from exc
            facts.update(updates)
        missing = document_scenarios.missing_required(item, facts)
        draft_id, artifact_id = row["draft_id"], row["artifact_id"]
        if missing:
            answer = document_scenarios.intake_question(item, facts)
        else:
            if item["kind"] == "word":
                title, content = document_scenarios.render_scenario(item["id"], facts)
                draft_id = draft_id or uuid.uuid4().hex
            else:
                payload = document_scenarios.office_payload(item, facts)
                office_files.file_bytes(item["kind"], payload)
                artifact_id = artifact_id or uuid.uuid4().hex
            format_name = {"word": "Word", "excel": "Excel", "ppt": "PPT"}[item["kind"]]
            answer = (f"《{item['title']}》已按你提供的信息制作。可下载 {format_name} 文件或打印；"
                      "未提供的建议/选填内容已标为【待确认】。请核对事实后使用。")
        new_messages.append({"role": "assistant", "content": answer})
        now = utcnow()
        with connection() as con:
            if not missing:
                if item["kind"] == "word":
                    if row["draft_id"]:
                        con.execute("UPDATE document_drafts SET content=?,updated_at=? WHERE id=? AND owner_id=?",
                                    (content, now, draft_id, user["id"]))
                    else:
                        con.execute("INSERT INTO document_drafts(id,owner_id,template_id,title,content,created_at,updated_at) VALUES (?,?,?,?,?,?,?)",
                                    (draft_id, user["id"], item["id"], title, content, now, now))
                    audit(con, user["id"], "generate", "document_draft", draft_id)
                else:
                    if row["artifact_id"]:
                        con.execute("UPDATE office_artifacts SET title=?,payload_json=? WHERE id=? AND owner_id=?",
                                    (payload["title"], json.dumps(payload, ensure_ascii=False), artifact_id, user["id"]))
                    else:
                        con.execute("INSERT INTO office_artifacts(id,owner_id,kind,title,payload_json,created_at) VALUES (?,?,?,?,?,?)",
                                    (artifact_id, user["id"], item["kind"], payload["title"],
                                     json.dumps(payload, ensure_ascii=False), now))
                    audit(con, user["id"], "generate", "office_artifact", artifact_id)
            con.execute("UPDATE document_conversations SET facts_json=?,messages_json=?,draft_id=?,artifact_id=?,updated_at=? WHERE id=? AND owner_id=?",
                        (json.dumps(facts, ensure_ascii=False), json.dumps(new_messages, ensure_ascii=False),
                         draft_id, artifact_id, now, conversation_id, user["id"]))
        return {"id": conversation_id, "scenario_id": item["id"], "title": item["title"],
                "messages": new_messages, "draft_id": draft_id, "artifact_id": artifact_id, "kind": item["kind"]}

    @app.get("/api/v1/documents/templates")
    def templates():
        return {"items": documents.list_templates()}

    @app.post("/api/v1/documents/drafts", status_code=201)
    def create_draft(body: DraftInput, user: dict = Depends(require_user)):
        title, content = documents.render(body.template_id, body.fields)
        draft_id = uuid.uuid4().hex
        with connection() as con:
            con.execute("INSERT INTO document_drafts(id,owner_id,template_id,title,content,created_at,updated_at) VALUES (?,?,?,?,?,?,?)",
                        (draft_id, user["id"], body.template_id, title, content, utcnow(), utcnow()))
            audit(con, user["id"], "create", "document_draft", draft_id)
        return {"id": draft_id, "title": title, "content": content}

    @app.get("/api/v1/documents/drafts")
    def my_drafts(user: dict = Depends(require_user)):
        with connection() as con:
            return {"items": rows(con.execute("SELECT id,template_id,title,created_at,updated_at FROM document_drafts WHERE owner_id=? ORDER BY updated_at DESC LIMIT 100", (user["id"],)).fetchall())}

    @app.get("/api/v1/documents/drafts/{draft_id}")
    def read_draft(draft_id: str, user: dict = Depends(require_user)):
        with connection() as con:
            row = con.execute("SELECT id,template_id,title,content,created_at,updated_at FROM document_drafts WHERE id=? AND owner_id=?", (draft_id, user["id"])).fetchone()
        if not row:
            raise HTTPException(404, "文书不存在")
        return dict(row)

    @app.put("/api/v1/documents/drafts/{draft_id}")
    def update_draft(draft_id: str, body: DraftUpdateInput, user: dict = Depends(require_user)):
        content = body.content.strip()
        if len(content) < 20:
            raise HTTPException(422, "文书正文至少需要 20 个字符")
        with connection() as con:
            updated = con.execute("UPDATE document_drafts SET content=?,updated_at=? WHERE id=? AND owner_id=?",
                                  (content, utcnow(), draft_id, user["id"]))
            if not updated.rowcount:
                raise HTTPException(404, "文书不存在")
            audit(con, user["id"], "update", "document_draft", draft_id)
        return {"id": draft_id, "content": content}

    @app.get("/api/v1/documents/drafts/{draft_id}/download")
    def download_draft(draft_id: str, user: dict = Depends(require_user)):
        with connection() as con:
            draft = con.execute("SELECT title,content FROM document_drafts WHERE id=? AND owner_id=?",
                                (draft_id, user["id"])).fetchone()
        if not draft:
            raise HTTPException(404, "文书不存在")
        return Response(content=office_files.draft_word_bytes(draft["title"], draft["content"]),
                        media_type=office_files.MIME["word"], headers={
                            "Content-Disposition": f'attachment; filename="draft-{draft_id[:12]}.docx"',
                            "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})

    @app.get("/api/v1/documents/drafts/{draft_id}/print", response_class=HTMLResponse)
    def print_draft(draft_id: str, user: dict = Depends(require_user)):
        with connection() as con:
            draft = con.execute("SELECT title,content FROM document_drafts WHERE id=? AND owner_id=?",
                                (draft_id, user["id"])).fetchone()
        if not draft:
            raise HTTPException(404, "文书不存在")
        payload = {"title": draft["title"], "sections": office_files.draft_sections(draft["content"])}
        return HTMLResponse(office_files.print_html("word", payload), headers={"Cache-Control": "private, no-store"})

    @app.get("/api/v1/office/templates")
    def office_templates():
        return {"items": office_files.CATALOG}

    @app.get("/api/v1/office/templates/{template_id}/download")
    def download_office_template(template_id: str):
        try:
            kind, payload = office_files.template_payload(template_id)
        except KeyError as exc:
            raise HTTPException(404, "文件模板不存在") from exc
        return Response(content=office_files.file_bytes(kind, payload), media_type=office_files.MIME[kind],
                        headers={"Content-Disposition": f'attachment; filename="{template_id}.{office_files.EXT[kind]}"',
                                 "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})

    @app.get("/api/v1/office/templates/{template_id}/print", response_class=HTMLResponse)
    def print_office_template(template_id: str):
        try:
            kind, payload = office_files.template_payload(template_id)
        except KeyError as exc:
            raise HTTPException(404, "文件模板不存在") from exc
        return HTMLResponse(office_files.print_html(kind, payload), headers={"Cache-Control": "no-store"})

    @app.post("/api/v1/office/files", status_code=201)
    async def generate_office_file(body: OfficeGenerateInput, user: dict = Depends(require_user)):
        if body.kind not in office_files.MIME:
            raise HTTPException(422, "请选择 Word、Excel 或 PPT")
        if len(body.prompt.strip()) < 20:
            raise HTTPException(422, "请至少用 20 个字描述文件需求")
        with connection() as con:
            count = con.execute("SELECT COUNT(*) FROM office_artifacts WHERE owner_id=? AND created_at>=?",
                                (user["id"], utcnow()[:10])).fetchone()[0]
        if count >= 10:
            raise HTTPException(429, "今日已生成 10 个文件，请明天再试")
        try:
            payload = await office_ai.generate(body.kind, body.prompt.strip())
            office_files.file_bytes(body.kind, payload)
        except (office_ai.OfficeGenerationError, ValueError, KeyError) as exc:
            raise HTTPException(503, str(exc)) from exc
        artifact_id, now = uuid.uuid4().hex, utcnow()
        with connection() as con:
            con.execute("INSERT INTO office_artifacts(id,owner_id,kind,title,payload_json,created_at) VALUES (?,?,?,?,?,?)",
                        (artifact_id, user["id"], body.kind, payload["title"],
                         json.dumps(payload, ensure_ascii=False), now))
            audit(con, user["id"], "generate", "office_artifact", artifact_id)
        return {"id": artifact_id, "kind": body.kind, "title": payload["title"], "created_at": now}

    @app.get("/api/v1/office/files")
    def list_office_files(user: dict = Depends(require_user)):
        with connection() as con:
            return {"items": rows(con.execute("SELECT id,kind,title,created_at FROM office_artifacts WHERE owner_id=? ORDER BY created_at DESC LIMIT 50",
                                             (user["id"],)).fetchall())}

    @app.get("/api/v1/office/files/{artifact_id}/download")
    def download_office_file(artifact_id: str, user: dict = Depends(require_user)):
        with connection() as con:
            item = con.execute("SELECT kind,payload_json FROM office_artifacts WHERE id=? AND owner_id=?",
                               (artifact_id, user["id"])).fetchone()
        if not item:
            raise HTTPException(404, "文件不存在")
        kind = item["kind"]
        return Response(content=office_files.file_bytes(kind, json.loads(item["payload_json"])),
                        media_type=office_files.MIME[kind], headers={
                            "Content-Disposition": f'attachment; filename="office-{artifact_id[:12]}.{office_files.EXT[kind]}"',
                            "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})

    @app.get("/api/v1/office/files/{artifact_id}/print", response_class=HTMLResponse)
    def print_office_file(artifact_id: str, user: dict = Depends(require_user)):
        with connection() as con:
            item = con.execute("SELECT kind,payload_json FROM office_artifacts WHERE id=? AND owner_id=?",
                               (artifact_id, user["id"])).fetchone()
        if not item:
            raise HTTPException(404, "文件不存在")
        return HTMLResponse(office_files.print_html(item["kind"], json.loads(item["payload_json"])),
                            headers={"Cache-Control": "private, no-store"})

    @app.get("/api/v1/info-requests")
    def list_requests(q: str = Query(default="", max_length=100), category: str = Query(default="", max_length=30)):
        sql = "SELECT * FROM info_requests WHERE status='approved'"
        params: list[str] = []
        if category:
            sql += " AND category=?"; params.append(category)
        if q.strip():
            sql += " AND (title LIKE ? OR description LIKE ? OR region LIKE ?)"
            pattern = f"%{q.strip()}%"; params.extend([pattern] * 3)
        sql += " ORDER BY created_at DESC LIMIT 100"
        with connection() as con:
            return {"items": [request_public(row) for row in con.execute(sql, params).fetchall()]}

    @app.get("/api/v1/info-requests/mine")
    def my_requests(user: dict = Depends(require_user)):
        with connection() as con:
            return {"items": rows(con.execute("SELECT * FROM info_requests WHERE owner_id=? ORDER BY created_at DESC LIMIT 100", (user["id"],)).fetchall())}

    @app.post("/api/v1/info-requests", status_code=201)
    def create_request(body: RequestInput, user: dict = Depends(require_user)):
        if body.category not in CATEGORIES:
            raise HTTPException(422, "请选择有效类别")
        combined = f"{body.title} {body.description} {body.purpose}"
        if any(marker in combined for marker in PRIVATE_MARKERS):
            raise HTTPException(422, "内容可能涉及非公开个人或受保护信息，请调整信息范围")
        request_id = uuid.uuid4().hex
        now = utcnow()
        with connection() as con:
            con.execute("""INSERT INTO info_requests(id,owner_id,title,category,region,description,purpose,reward_cents,deadline,created_at,updated_at)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                        (request_id, user["id"], body.title.strip(), body.category, body.region.strip(),
                         body.description.strip(), body.purpose.strip(), body.reward_yuan * 100,
                         body.deadline, now, now))
            audit(con, user["id"], "submit_for_review", "info_request", request_id)
        return {"id": request_id, "status": "pending"}

    @app.get("/api/v1/info-requests/{request_id}")
    def get_request(request_id: str, request: Request):
        session = get_session(request)
        with connection() as con:
            row = con.execute("SELECT * FROM info_requests WHERE id=?", (request_id,)).fetchone()
        if not row or (row["status"] != "approved" and (not session or session["id"] not in {row["owner_id"], row["reviewed_by"]} and session["role"] != "admin")):
            raise HTTPException(404, "求取不存在")
        return dict(row) if session and (session["id"] == row["owner_id"] or session["role"] == "admin") else request_public(row)

    @app.get("/api/v1/admin/info-requests")
    def pending_requests(user: dict = Depends(require_admin)):
        with connection() as con:
            return {"items": rows(con.execute("SELECT * FROM info_requests WHERE status='pending' ORDER BY created_at LIMIT 100").fetchall())}

    @app.patch("/api/v1/admin/info-requests/{request_id}")
    def review_request(request_id: str, body: ReviewInput, user: dict = Depends(require_admin)):
        if body.status not in {"approved", "rejected"}:
            raise HTTPException(422, "审核状态无效")
        if body.platform_verified and (body.status != "approved" or len(body.verification_basis.strip()) < 10):
            raise HTTPException(422, "平台核验须记录主体和用途的核验依据")
        with connection() as con:
            row = con.execute("SELECT status FROM info_requests WHERE id=?", (request_id,)).fetchone()
            if not row:
                raise HTTPException(404, "求取不存在")
            if row["status"] != "pending":
                raise HTTPException(409, "该求取已处理")
            con.execute("""UPDATE info_requests SET status=?,platform_verified=?,verification_basis=?,review_note=?,reviewed_by=?,reviewed_at=?,updated_at=? WHERE id=?""",
                        (body.status, int(body.platform_verified), body.verification_basis.strip() if body.platform_verified else None,
                         body.note.strip(), user["id"], utcnow(), utcnow(), request_id))
            audit(con, user["id"], "review_" + body.status, "info_request", request_id)
        return {"id": request_id, "status": body.status}

    @app.get("/api/v1/admin/users")
    def admin_users(q: str = Query(default="", max_length=100), limit: int = Query(default=50, ge=1, le=100),
                    offset: int = Query(default=0, ge=0), user: dict = Depends(require_admin)):
        sql = "FROM users WHERE 1=1"
        params: list[str] = []
        if q.strip():
            sql += " AND (email LIKE ? OR display_name LIKE ? OR phone LIKE ?)"
            params = [f"%{q.strip()}%"] * 3
        with connection() as con:
            total = con.execute("SELECT COUNT(*) " + sql, params).fetchone()[0]
            items = rows(con.execute("SELECT id,email,display_name,phone,role,created_at " + sql +
                                     " ORDER BY created_at DESC LIMIT ? OFFSET ?", [*params, limit, offset]).fetchall())
        return {"items": items, "total": total, "limit": limit, "offset": offset}

    @app.patch("/api/v1/admin/users/{target_id}/role")
    def admin_set_role(target_id: str, body: RoleInput, user: dict = Depends(require_admin)):
        if body.role not in {"user", "admin"}:
            raise HTTPException(422, "角色无效")
        if target_id == user["id"] and body.role != "admin":
            raise HTTPException(422, "不能撤销自己的管理员权限")
        with connection() as con:
            target = con.execute("SELECT role FROM users WHERE id=?", (target_id,)).fetchone()
            if not target:
                raise HTTPException(404, "用户不存在")
            if target["role"] == "admin" and body.role == "user":
                count = con.execute("SELECT COUNT(*) FROM users WHERE role='admin'").fetchone()[0]
                if count <= 1:
                    raise HTTPException(422, "至少保留一位管理员")
            con.execute("UPDATE users SET role=? WHERE id=?", (body.role, target_id))
            audit(con, user["id"], "set_role_" + body.role, "user", target_id)
        return {"id": target_id, "role": body.role}

    @app.get("/api/v1/admin/conversations")
    def admin_conversations(q: str = Query(default="", max_length=100), user: dict = Depends(require_admin)):
        sql = """SELECT c.id,c.created_at,r.title AS request_title,
                        ru.display_name AS requester_name,pu.display_name AS provider_name,
                        (SELECT MAX(m.created_at) FROM messages m WHERE m.conversation_id=c.id) AS last_message_at
                 FROM conversations c JOIN info_requests r ON r.id=c.request_id
                 JOIN users ru ON ru.id=c.requester_id JOIN users pu ON pu.id=c.provider_id WHERE 1=1"""
        params: list[str] = []
        if q.strip():
            sql += " AND (r.title LIKE ? OR ru.display_name LIKE ? OR pu.display_name LIKE ?)"
            params = [f"%{q.strip()}%"] * 3
        sql += " ORDER BY COALESCE(last_message_at,c.created_at) DESC LIMIT 100"
        with connection() as con:
            items = rows(con.execute(sql, params).fetchall())
            audit(con, user["id"], "list", "admin_conversations", user["id"])
        return {"items": items}

    @app.get("/api/v1/admin/conversations/{conversation_id}/messages")
    def admin_messages(conversation_id: str, user: dict = Depends(require_admin)):
        with connection() as con:
            exists = con.execute("SELECT id FROM conversations WHERE id=?", (conversation_id,)).fetchone()
            if not exists:
                raise HTTPException(404, "会话不存在")
            items = rows(con.execute("""SELECT m.id,m.body,m.created_at,u.display_name AS sender_name
                                       FROM messages m JOIN users u ON u.id=m.sender_id
                                       WHERE m.conversation_id=? ORDER BY m.created_at LIMIT 200""",
                                    (conversation_id,)).fetchall())
            audit(con, user["id"], "view", "conversation", conversation_id)
        return {"items": items}

    @app.post("/api/v1/info-requests/{request_id}/conversations", status_code=201)
    def start_conversation(request_id: str, user: dict = Depends(require_user)):
        with connection() as con:
            row = con.execute("SELECT owner_id,status FROM info_requests WHERE id=?", (request_id,)).fetchone()
            if not row or row["status"] != "approved":
                raise HTTPException(404, "公开求取不存在")
            if row["owner_id"] == user["id"]:
                raise HTTPException(422, "不能联系自己的求取")
            existing = con.execute("SELECT id FROM conversations WHERE request_id=? AND provider_id=?", (request_id, user["id"])).fetchone()
            if existing:
                return {"id": existing["id"]}
            conversation_id = uuid.uuid4().hex
            con.execute("INSERT INTO conversations(id,request_id,requester_id,provider_id,created_at) VALUES (?,?,?,?,?)",
                        (conversation_id, request_id, row["owner_id"], user["id"], utcnow()))
            audit(con, user["id"], "start", "conversation", conversation_id)
        return {"id": conversation_id}

    @app.get("/api/v1/conversations")
    def my_conversations(user: dict = Depends(require_user)):
        with connection() as con:
            items = rows(con.execute("""SELECT c.id,c.request_id,c.requester_id,c.provider_id,c.created_at,r.title AS request_title
                                        FROM conversations c JOIN info_requests r ON r.id=c.request_id
                                        WHERE c.requester_id=? OR c.provider_id=? ORDER BY c.created_at DESC LIMIT 100""",
                                     (user["id"], user["id"])).fetchall())
        return {"items": items}

    def ensure_participant(con: sqlite3.Connection, conversation_id: str, user_id: str) -> None:
        row = con.execute("SELECT requester_id,provider_id FROM conversations WHERE id=?", (conversation_id,)).fetchone()
        if not row or user_id not in (row["requester_id"], row["provider_id"]):
            raise HTTPException(404, "会话不存在")

    @app.get("/api/v1/conversations/{conversation_id}/messages")
    def list_messages(conversation_id: str, user: dict = Depends(require_user)):
        with connection() as con:
            ensure_participant(con, conversation_id, user["id"])
            return {"items": rows(con.execute("SELECT id,sender_id,body,created_at FROM messages WHERE conversation_id=? ORDER BY created_at LIMIT 200", (conversation_id,)).fetchall())}

    @app.post("/api/v1/conversations/{conversation_id}/messages", status_code=201)
    def send_message(conversation_id: str, body: MessageInput, user: dict = Depends(require_user)):
        message_id = uuid.uuid4().hex
        with connection() as con:
            ensure_participant(con, conversation_id, user["id"])
            con.execute("INSERT INTO messages(id,conversation_id,sender_id,body,created_at) VALUES (?,?,?,?,?)",
                        (message_id, conversation_id, user["id"], body.body.strip(), utcnow()))
            audit(con, user["id"], "send", "message", message_id)
        return {"id": message_id}

    @app.get("/api/v1/lawyers")
    def list_lawyers(q: str = Query(default="", max_length=100)):
        sql = """SELECT p.user_id,COALESCE(NULLIF(p.legal_name,''),u.display_name) AS display_name,
                        p.firm,p.years,p.region,p.specialties_json,p.social_url,p.bio,p.case_summary,
                        p.honors,p.verified_at,p.verification_source
                 FROM lawyer_profiles p JOIN users u ON u.id=p.user_id WHERE p.status='verified'"""
        params: list[str] = []
        if q.strip():
            sql += " AND (u.display_name LIKE ? OR p.firm LIKE ? OR p.region LIKE ? OR p.specialties_json LIKE ?)"
            params = [f"%{q.strip()}%"] * 4
        sql += " ORDER BY p.verified_at DESC LIMIT 100"
        with connection() as con:
            items = rows(con.execute(sql, params).fetchall())
        for item in items:
            item["specialties"] = json.loads(item.pop("specialties_json"))
        return {"items": items}

    @app.get("/api/v1/lawyers/{user_id}/portrait")
    def lawyer_portrait(user_id: str):
        with connection() as con:
            item = con.execute("""SELECT e.mime,e.content FROM lawyer_evidence e
                                  JOIN lawyer_profiles p ON p.user_id=e.user_id
                                  WHERE e.user_id=? AND e.kind='portrait' AND p.status='verified'""",
                               (user_id,)).fetchone()
        if not item:
            raise HTTPException(404, "头像不存在")
        return Response(item["content"], media_type=item["mime"], headers={"Cache-Control": "public, max-age=3600", "X-Content-Type-Options": "nosniff"})

    @app.get("/api/v1/lawyers/profile/mine")
    def my_lawyer_profile(user: dict = Depends(require_user)):
        with connection() as con:
            row = con.execute("SELECT * FROM lawyer_profiles WHERE user_id=?", (user["id"],)).fetchone()
            evidence = [item[0] for item in con.execute("SELECT kind FROM lawyer_evidence WHERE user_id=?", (user["id"],))]
        return {"profile": dict(row) if row else None, "evidence": evidence}

    @app.post("/api/v1/lawyers/evidence/{kind}")
    async def upload_lawyer_evidence(kind: str, file: UploadFile = File(...), user: dict = Depends(require_user)):
        if kind not in {"portrait", "id_front", "id_back", "license_front", "license_record"}:
            raise HTTPException(422, "材料类型无效")
        mime = file.content_type or ""
        if mime not in {"image/jpeg", "image/png", "image/webp"}:
            raise HTTPException(422, "仅接受 JPG、PNG 或 WebP 图片")
        content = await file.read(5_000_001)
        if not content or len(content) > 5_000_000:
            raise HTTPException(422, "图片大小须在 5 MB 以内")
        signatures = {"image/jpeg": content.startswith(b"\xff\xd8\xff"),
                      "image/png": content.startswith(b"\x89PNG\r\n\x1a\n"),
                      "image/webp": content.startswith(b"RIFF") and content[8:12] == b"WEBP"}
        if not signatures[mime]:
            raise HTTPException(422, "图片格式与文件内容不符")
        try:
            with Image.open(BytesIO(content)) as image:
                image.verify()
            with Image.open(BytesIO(content)) as image:
                if image.width * image.height > 20_000_000:
                    raise HTTPException(422, "图片像素过大")
                if kind == "portrait":
                    clean = ImageOps.exif_transpose(image).convert("RGB")
                    clean.thumbnail((1200, 1200))
                    output = BytesIO()
                    clean.save(output, format="JPEG", quality=90)
                    content, mime = output.getvalue(), "image/jpeg"
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
            raise HTTPException(422, "图片文件无法识别") from exc
        evidence_id, now = uuid.uuid4().hex, utcnow()
        with connection() as con:
            con.execute("""INSERT INTO lawyer_evidence(id,user_id,kind,mime,content,created_at) VALUES (?,?,?,?,?,?)
                           ON CONFLICT(user_id,kind) DO UPDATE SET id=excluded.id,mime=excluded.mime,
                           content=excluded.content,created_at=excluded.created_at""",
                        (evidence_id, user["id"], kind, mime, content, now))
            con.execute("UPDATE lawyer_profiles SET status='pending',verified_at=NULL,verified_by=NULL,verification_source=NULL,review_note='',updated_at=? WHERE user_id=?",
                        (now, user["id"]))
            audit(con, user["id"], "upload", "lawyer_evidence", kind)
        return {"kind": kind, "ok": True}

    @app.get("/api/v1/lawyers/evidence/{owner_id}/{kind}")
    def read_lawyer_evidence(owner_id: str, kind: str, user: dict = Depends(require_user)):
        if owner_id != user["id"] and user["role"] != "admin":
            raise HTTPException(403, "无权查看此材料")
        with connection() as con:
            item = con.execute("SELECT mime,content FROM lawyer_evidence WHERE user_id=? AND kind=?", (owner_id, kind)).fetchone()
            if item and owner_id != user["id"]:
                audit(con, user["id"], "view", "lawyer_evidence", f"{owner_id}:{kind}")
        if not item:
            raise HTTPException(404, "材料不存在")
        return Response(item["content"], media_type=item["mime"], headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})

    @app.put("/api/v1/lawyers/profile/mine")
    def save_lawyer_profile(body: LawyerInput, user: dict = Depends(require_user)):
        if any(not 2 <= len(value.strip()) <= 40 for value in body.specialties):
            raise HTTPException(422, "业务领域需为 2–40 个字符")
        if body.social_url:
            parsed = urlsplit(body.social_url)
            if parsed.scheme != "https" or not parsed.netloc:
                raise HTTPException(422, "社交链接须为 HTTPS 地址")
        if body.gender not in {"", "男", "女", "其他"}:
            raise HTTPException(422, "性别选项无效")
        if not re.fullmatch(r"\d{17}[\dXx]|\d{15}", body.id_number):
            raise HTTPException(422, "身份证号码格式无效")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", body.practice_start):
            raise HTTPException(422, "开始执业日期格式无效")
        phone = re.sub(r"[\s-]", "", body.contact_phone)
        if not re.fullmatch(r"\+?\d{7,15}", phone):
            raise HTTPException(422, "联系电话格式无效")
        with connection() as con:
            con.execute("""INSERT INTO lawyer_profiles(user_id,license_no,firm,years,region,specialties_json,social_url,bio,case_summary,legal_name,gender,id_number,practice_start,honors,contact_phone,created_at,updated_at)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                           ON CONFLICT(user_id) DO UPDATE SET license_no=excluded.license_no,firm=excluded.firm,
                           years=excluded.years,region=excluded.region,specialties_json=excluded.specialties_json,
                           social_url=excluded.social_url,bio=excluded.bio,case_summary=excluded.case_summary,
                           legal_name=excluded.legal_name,gender=excluded.gender,id_number=excluded.id_number,
                           practice_start=excluded.practice_start,honors=excluded.honors,contact_phone=excluded.contact_phone,
                           status='pending',verified_at=NULL,verified_by=NULL,verification_source=NULL,review_note='',updated_at=excluded.updated_at""",
                        (user["id"], body.license_no.strip(), body.firm.strip(), body.years, body.region.strip(),
                         json.dumps([v.strip() for v in body.specialties], ensure_ascii=False), body.social_url,
                         body.bio.strip(), body.case_summary.strip(), body.legal_name.strip(), body.gender,
                         body.id_number.upper(), body.practice_start, body.honors.strip(), phone, utcnow(), utcnow()))
            audit(con, user["id"], "submit_for_review", "lawyer_profile", user["id"])
        return {"status": "pending"}

    @app.get("/api/v1/admin/lawyers")
    def pending_lawyers(user: dict = Depends(require_admin)):
        with connection() as con:
            items = rows(con.execute("SELECT * FROM lawyer_profiles WHERE status='pending' ORDER BY created_at LIMIT 100").fetchall())
            for item in items:
                item["evidence"] = [row[0] for row in con.execute("SELECT kind FROM lawyer_evidence WHERE user_id=?", (item["user_id"],))]
            return {"items": items}

    @app.patch("/api/v1/admin/lawyers/{user_id}")
    def review_lawyer(user_id: str, body: LawyerReviewInput, user: dict = Depends(require_admin)):
        if body.status not in {"verified", "rejected"}:
            raise HTTPException(422, "审核状态无效")
        if body.status == "verified":
            parsed = urlsplit(body.verification_source)
            if parsed.scheme != "https" or not parsed.netloc:
                raise HTTPException(422, "核验通过须填写 HTTPS 执业信息来源")
        with connection() as con:
            row = con.execute("SELECT status FROM lawyer_profiles WHERE user_id=?", (user_id,)).fetchone()
            if not row:
                raise HTTPException(404, "律师资料不存在")
            if row["status"] != "pending":
                raise HTTPException(409, "该资料已处理")
            evidence = {item[0] for item in con.execute("SELECT kind FROM lawyer_evidence WHERE user_id=?", (user_id,))}
            missing = {"portrait", "id_front", "id_back", "license_front", "license_record"} - evidence
            if body.status == "verified" and missing:
                raise HTTPException(422, "缺少认证材料：" + "、".join(sorted(missing)))
            con.execute("UPDATE lawyer_profiles SET status=?,verified_at=?,verified_by=?,verification_source=?,review_note=?,updated_at=? WHERE user_id=?",
                        (body.status, utcnow() if body.status == "verified" else None, user["id"],
                         body.verification_source if body.status == "verified" else None, body.note.strip(), utcnow(), user_id))
            audit(con, user["id"], "review_" + body.status, "lawyer_profile", user_id)
        return {"status": body.status}

    @app.get("/api/v1/exam/papers")
    def exam_papers(q: str = Query(default="", max_length=100), year: int | None = None):
        sql = "SELECT * FROM exam_papers WHERE 1=1"
        params: list[object] = []
        if year:
            sql += " AND year=?"; params.append(year)
        if q.strip():
            sql += " AND (title LIKE ? OR subject LIKE ? OR paper_type LIKE ?)"
            params.extend([f"%{q.strip()}%"] * 3)
        sql += " ORDER BY year DESC,title LIMIT 100"
        with connection() as con:
            return {"items": rows(con.execute(sql, params).fetchall())}

    @app.get("/api/v1/exam/questions")
    def exam_questions(q: str = Query(default="", max_length=100), year: int | None = None,
                       subject: str = Query(default="", max_length=40)):
        sql = """SELECT q.id,q.paper_id,q.question_no,q.subject,q.stem,q.options_json,q.answer,
                        q.explanation,q.source_url,q.provenance,p.year,p.title AS paper_title
                 FROM exam_questions q JOIN exam_papers p ON p.id=q.paper_id WHERE 1=1"""
        params: list[object] = []
        if year:
            sql += " AND p.year=?"; params.append(year)
        if subject.strip():
            sql += " AND q.subject=?"; params.append(subject.strip())
        if q.strip():
            sql += " AND (q.stem LIKE ? OR q.subject LIKE ? OR p.title LIKE ?)"
            params.extend([f"%{q.strip()}%"] * 3)
        sql += " ORDER BY p.year DESC,q.question_no LIMIT 100"
        with connection() as con:
            items = rows(con.execute(sql, params).fetchall())
        for item in items:
            item["options"] = json.loads(item.pop("options_json"))
        return {"items": items}

    @app.get("/api/v1/exam/mock-sessions")
    def list_mock_sessions(user: dict = Depends(require_user)):
        with connection() as con:
            sessions = con.execute("SELECT id FROM mock_exam_sessions WHERE owner_id=? ORDER BY created_at DESC LIMIT 20",
                                   (user["id"],)).fetchall()
            return {"items": [mock_session_data(con, row["id"], user["id"]) for row in sessions]}

    @app.post("/api/v1/exam/mock-sessions", status_code=201)
    async def start_mock_session(body: MockStartInput, user: dict = Depends(require_user)):
        if body.subject not in {"随机", *exam_practice.SUBJECTS} or body.count not in {5, 10}:
            raise HTTPException(422, "请选择有效科目和题量")
        with connection() as con:
            used = con.execute("""SELECT COUNT(*) FROM mock_exam_questions q
                                  JOIN mock_exam_sessions s ON s.id=q.session_id
                                  WHERE s.owner_id=? AND q.created_at>=?""",
                               (user["id"], utcnow()[:10])).fetchone()[0]
        if used >= 30:
            raise HTTPException(429, "今日已生成 30 道练习题，请明天再试")
        try:
            question = await exam_practice.generate_question(body.subject)
        except (exam_practice.GenerationError, ValueError) as exc:
            raise HTTPException(503, str(exc)) from exc
        session_id, question_id, now = uuid.uuid4().hex, uuid.uuid4().hex, utcnow()
        with connection() as con:
            con.execute("""INSERT INTO mock_exam_sessions
                           (id,owner_id,subject,total_questions,current_position,status,created_at,updated_at)
                           VALUES (?,?,?,?,1,'active',?,?)""",
                        (session_id, user["id"], body.subject, body.count, now, now))
            con.execute("""INSERT INTO mock_exam_questions
                           (id,session_id,position,subject,kind,stem,options_json,answer_keys_json,
                            explanation,knowledge_point,model_name,created_at)
                           VALUES (?,?,1,?,?,?,?,?,?,?,?,?)""",
                        (question_id, session_id, question["subject"], question["kind"], question["stem"],
                         json.dumps(question["options"], ensure_ascii=False),
                         json.dumps(question["answer_keys"]), question["explanation"],
                         question["knowledge_point"], question["model_name"], now))
            audit(con, user["id"], "start", "mock_exam_session", session_id)
            return mock_session_data(con, session_id, user["id"])

    @app.get("/api/v1/exam/mock-sessions/{session_id}")
    def read_mock_session(session_id: str, user: dict = Depends(require_user)):
        with connection() as con:
            return mock_session_data(con, session_id, user["id"])

    @app.post("/api/v1/exam/mock-sessions/{session_id}/answer")
    def answer_mock_session(session_id: str, body: MockAnswerInput, user: dict = Depends(require_user)):
        keys = body.selected_keys
        if len(set(keys)) != len(keys) or any(key not in {"A", "B", "C", "D"} for key in keys):
            raise HTTPException(422, "请选择有效选项")
        with connection() as con:
            session = con.execute("SELECT * FROM mock_exam_sessions WHERE id=? AND owner_id=?",
                                  (session_id, user["id"])).fetchone()
            if not session:
                raise HTTPException(404, "练习不存在")
            if session["status"] != "active":
                raise HTTPException(409, "当前练习不可提交答案")
            question = con.execute("SELECT * FROM mock_exam_questions WHERE session_id=? AND position=?",
                                   (session_id, session["current_position"])).fetchone()
            if not question or question["answered_at"]:
                raise HTTPException(409, "本题已提交，请进入下一题")
            if question["kind"] == "single" and len(keys) != 1:
                raise HTTPException(422, "单选题只能选择一个答案")
            correct = sorted(keys) == json.loads(question["answer_keys_json"])
            now = utcnow()
            updated = con.execute("""UPDATE mock_exam_questions
                                     SET selected_keys_json=?,is_correct=?,answered_at=?
                                     WHERE id=? AND answered_at IS NULL""",
                                  (json.dumps(sorted(keys)), int(correct), now, question["id"]))
            if not updated.rowcount:
                raise HTTPException(409, "本题已提交")
            if session["current_position"] == session["total_questions"]:
                con.execute("UPDATE mock_exam_sessions SET status='completed',updated_at=? WHERE id=?",
                            (now, session_id))
            else:
                con.execute("UPDATE mock_exam_sessions SET updated_at=? WHERE id=?", (now, session_id))
            return mock_session_data(con, session_id, user["id"])

    @app.post("/api/v1/exam/mock-sessions/{session_id}/next")
    async def next_mock_question(session_id: str, user: dict = Depends(require_user)):
        with connection() as con:
            session = con.execute("SELECT * FROM mock_exam_sessions WHERE id=? AND owner_id=?",
                                  (session_id, user["id"])).fetchone()
            if not session:
                raise HTTPException(404, "练习不存在")
            current = con.execute("SELECT answered_at FROM mock_exam_questions WHERE session_id=? AND position=?",
                                  (session_id, session["current_position"])).fetchone()
            if session["status"] != "active" or not current or not current["answered_at"] or session["current_position"] >= session["total_questions"]:
                raise HTTPException(409, "请先完成当前题目")
            used = con.execute("""SELECT COUNT(*) FROM mock_exam_questions q
                                  JOIN mock_exam_sessions s ON s.id=q.session_id
                                  WHERE s.owner_id=? AND q.created_at>=?""",
                               (user["id"], utcnow()[:10])).fetchone()[0]
            if used >= 30:
                raise HTTPException(429, "今日已生成 30 道练习题，请明天再试")
            con.execute("UPDATE mock_exam_sessions SET status='generating',updated_at=? WHERE id=?",
                        (utcnow(), session_id))
            subject, position = session["subject"], session["current_position"] + 1
        try:
            question = await exam_practice.generate_question(subject)
        except (exam_practice.GenerationError, ValueError) as exc:
            with connection() as con:
                con.execute("UPDATE mock_exam_sessions SET status='active',updated_at=? WHERE id=? AND owner_id=? AND status='generating'",
                            (utcnow(), session_id, user["id"]))
            raise HTTPException(503, str(exc)) from exc
        now = utcnow()
        with connection() as con:
            con.execute("""INSERT INTO mock_exam_questions
                           (id,session_id,position,subject,kind,stem,options_json,answer_keys_json,
                            explanation,knowledge_point,model_name,created_at)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (uuid.uuid4().hex, session_id, position, question["subject"], question["kind"],
                         question["stem"], json.dumps(question["options"], ensure_ascii=False),
                         json.dumps(question["answer_keys"]), question["explanation"],
                         question["knowledge_point"], question["model_name"], now))
            con.execute("UPDATE mock_exam_sessions SET current_position=?,status='active',updated_at=? WHERE id=? AND owner_id=?",
                        (position, now, session_id, user["id"]))
            return mock_session_data(con, session_id, user["id"])

    return app


app = create_app()
