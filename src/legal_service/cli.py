"""Local operator commands. Never print passwords or question payloads."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sqlite3
import sys
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv

from .auth import hash_password, normalize_email
from .db import audit, connection, initialize, utcnow
from .source_sync import sync_all


def https_url(value: str, label: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError(f"{label} must be an HTTPS URL without embedded credentials")
    return value


def bootstrap_admin(email: str, display_name: str) -> None:
    email = normalize_email(email)
    password = getpass.getpass("New admin password (12+ characters): ")
    if len(password) < 12 or len(password) > 256:
        raise SystemExit("Admin password must be 12–256 characters")
    with connection() as con:
        row = con.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
        if row:
            con.execute("UPDATE users SET password_hash=?,role='admin',display_name=? WHERE id=?",
                        (hash_password(password), display_name, row["id"]))
            user_id = row["id"]
        else:
            user_id = uuid.uuid4().hex
            con.execute("INSERT INTO users(id,email,display_name,password_hash,role,created_at) VALUES (?,?,?,?,?,?)",
                        (user_id, email, display_name, hash_password(password), "admin", utcnow()))
        con.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
        audit(con, user_id, "bootstrap_admin", "user", user_id)
    print(f"Admin ready: {email}")


def import_exam(path: Path, basis: str, evidence: str) -> None:
    if basis not in {"licensed", "permission", "public-domain"}:
        raise SystemExit("Unsupported rights basis")
    https_url(evidence, "Rights evidence")
    if not path.is_file():
        raise SystemExit("JSONL file does not exist")
    count = 0
    with connection() as con, path.open("r", encoding="utf-8") as handle:
        for line_no, raw in enumerate(handle, 1):
            if not raw.strip():
                continue
            try:
                item = json.loads(raw)
                paper = item["paper"]
                question = item["question"]
                paper_id = str(paper["id"])
                year = int(paper["year"])
                title = str(paper["title"]).strip()
                subject = str(paper["subject"]).strip()
                paper_type = str(paper["paper_type"]).strip()
                paper_url = https_url(str(paper["source_url"]), "Paper source")
                authority = str(paper["authority"]).strip()
                number = str(question["number"]).strip()
                stem = str(question["stem"]).strip()
                options = question.get("options", [])
                source_url = https_url(str(question.get("source_url") or paper_url), "Question source")
                if not (2000 <= year <= 2100 and all((paper_id, title, subject, paper_type, authority, number, stem))):
                    raise ValueError("missing/invalid paper or question metadata")
                if not isinstance(options, list) or len(options) > 10 or any(not isinstance(x, str) for x in options):
                    raise ValueError("options must be a string list")
                if len(stem) > 10000 or len(title) > 200 or len(number) > 30:
                    raise ValueError("question metadata too long")
                question_id = str(question.get("id") or uuid.uuid5(uuid.NAMESPACE_URL, paper_id + ":" + number).hex)
                con.execute("""INSERT INTO exam_papers(id,year,title,subject,paper_type,source_url,authority,rights_status,verified_at)
                               VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                               year=excluded.year,title=excluded.title,subject=excluded.subject,
                               paper_type=excluded.paper_type,source_url=excluded.source_url,
                               authority=excluded.authority,rights_status=excluded.rights_status,
                               verified_at=excluded.verified_at""",
                            (paper_id, year, title, subject, paper_type, paper_url, authority, basis, utcnow()))
                con.execute("""INSERT INTO exam_questions(id,paper_id,question_no,subject,stem,options_json,answer,explanation,source_url,rights_status,provenance,created_at)
                               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                               ON CONFLICT(paper_id,question_no) DO UPDATE SET
                               subject=excluded.subject,stem=excluded.stem,options_json=excluded.options_json,
                               answer=excluded.answer,explanation=excluded.explanation,source_url=excluded.source_url,
                               rights_status=excluded.rights_status,provenance=excluded.provenance""",
                            (question_id, paper_id, number, str(question.get("subject") or subject), stem,
                             json.dumps(options, ensure_ascii=False), question.get("answer"),
                             question.get("explanation"), source_url, basis, evidence, utcnow()))
                count += 1
            except (KeyError, ValueError, TypeError, sqlite3.IntegrityError, json.JSONDecodeError) as exc:
                raise SystemExit(f"Invalid JSONL at line {line_no}: {type(exc).__name__}: {exc}") from exc
        if count == 0:
            raise SystemExit("JSONL contains no questions")
        audit(con, None, "import", "exam_questions", str(path.name), f"count={count};basis={basis};evidence={evidence}")
    print(f"Imported {count} question records")


def main() -> None:
    load_dotenv(Path.cwd() / ".env")
    parser = argparse.ArgumentParser(prog="legal-service")
    commands = parser.add_subparsers(dest="command", required=True)
    admin = commands.add_parser("bootstrap-admin")
    admin.add_argument("--email", required=True)
    admin.add_argument("--name", default="平台管理员")
    exam = commands.add_parser("import-exam")
    exam.add_argument("--file", type=Path, required=True)
    exam.add_argument("--rights-basis", choices=["licensed", "permission", "public-domain"], required=True)
    exam.add_argument("--rights-evidence", required=True)
    sync = commands.add_parser("sync-sources")
    sync.add_argument("--force", action="store_true", help="Recheck sources even after today's successful run")
    args = parser.parse_args()
    initialize()
    if args.command == "bootstrap-admin":
        bootstrap_admin(args.email, args.name)
    elif args.command == "import-exam":
        try:
            import_exam(args.file, args.rights_basis, args.rights_evidence)
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
    elif args.command == "sync-sources":
        for result in sync_all(force=args.force):
            print(f"{result['kind']}: {result['status']} ({result.get('items', 0)} items)" +
                  (f" — {result['error']}" if result.get('error') else ""))


if __name__ == "__main__":
    main()
