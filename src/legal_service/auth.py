"""Password hashing, server-side sessions, and CSRF checks."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from fastapi import HTTPException, Request

from .db import audit, connection, utcnow

COOKIE_NAME = "legal_session"
SESSION_DAYS = 14
HASH_ITERATIONS = 600_000


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, HASH_ITERATIONS)
    return f"pbkdf2_sha256${HASH_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, count, salt, expected = encoded.split("$")
        if algorithm != "pbkdf2_sha256" or not 100_000 <= int(count) <= 1_000_000:
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), int(count))
        return hmac.compare_digest(digest, bytes.fromhex(expected))
    except (ValueError, TypeError):
        return False


def normalize_email(email: str) -> str:
    value = email.strip().lower()
    if len(value) > 254 or "@" not in value or value.startswith("@") or value.endswith("@"):
        raise HTTPException(422, "请输入有效的邮箱地址")
    return value


def register(email: str, display_name: str, password: str) -> dict:
    email = normalize_email(email)
    display_name = display_name.strip()
    if not 2 <= len(display_name) <= 40:
        raise HTTPException(422, "昵称需为 2–40 个字符")
    if len(password) < 12 or len(password) > 256:
        raise HTTPException(422, "密码需为 12–256 个字符")
    user_id = uuid.uuid4().hex
    with connection() as con:
        try:
            con.execute("INSERT INTO users(id,email,display_name,password_hash,created_at) VALUES (?,?,?,?,?)",
                        (user_id, email, display_name, hash_password(password), utcnow()))
        except sqlite3.IntegrityError as exc:
            raise HTTPException(409, "该邮箱已注册") from exc
        audit(con, user_id, "register", "user", user_id)
    return {"id": user_id, "email": email, "display_name": display_name, "role": "user"}


def create_session(user_id: str) -> tuple[str, str]:
    token = secrets.token_urlsafe(48)
    csrf = secrets.token_urlsafe(32)
    expires = (datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)).isoformat(timespec="seconds")
    with connection() as con:
        con.execute("INSERT INTO sessions(token_hash,user_id,csrf_token,expires_at,created_at) VALUES (?,?,?,?,?)",
                    (hashlib.sha256(token.encode()).hexdigest(), user_id, csrf, expires, utcnow()))
        audit(con, user_id, "login", "user", user_id)
    return token, csrf


def get_session(request: Request) -> dict | None:
    token = request.cookies.get(COOKIE_NAME)
    if not token or len(token) > 200:
        return None
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with connection() as con:
        row = con.execute("""SELECT u.id,u.email,u.display_name,u.role,s.csrf_token,s.expires_at
                             FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=?""",
                          (token_hash,)).fetchone()
        if not row:
            return None
        if datetime.fromisoformat(row["expires_at"]) <= datetime.now(timezone.utc):
            con.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash,))
            return None
        return dict(row)


def require_user(request: Request) -> dict:
    session = get_session(request)
    if not session:
        raise HTTPException(401, "请先登录")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        supplied = request.headers.get("x-csrf-token", "")
        if not supplied or not hmac.compare_digest(supplied, session["csrf_token"]):
            raise HTTPException(403, "CSRF 验证失败，请刷新页面后重试")
    return session


def require_admin(request: Request) -> dict:
    session = require_user(request)
    if session["role"] != "admin":
        raise HTTPException(403, "需要管理员权限")
    return session


def check_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if not origin:
        return
    parsed = urlsplit(origin)
    if parsed.scheme not in {"http", "https"} or parsed.netloc != request.headers.get("host"):
        raise HTTPException(403, "跨站请求被拒绝")


def delete_session(request: Request) -> None:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return
    with connection() as con:
        con.execute("DELETE FROM sessions WHERE token_hash=?", (hashlib.sha256(token.encode()).hexdigest(),))
