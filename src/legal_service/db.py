"""SQLite persistence and curated, link-only public source catalog."""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def db_path() -> Path:
    base = Path(os.getenv("APP_DATA_DIR", ".runtime/data")).resolve()
    base.mkdir(parents=True, exist_ok=True, mode=0o700)
    return base / "legal.sqlite3"


@contextmanager
def connection() -> Iterator[sqlite3.Connection]:
    con = sqlite3.connect(db_path(), timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA busy_timeout=10000")
    try:
        yield con
        con.commit()
    except BaseException:
        con.rollback()
        raise
    finally:
        con.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE, display_name TEXT NOT NULL,
  password_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'user'
    CHECK(role IN ('user','admin')), created_at TEXT NOT NULL,
  phone TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_users_role_created ON users(role,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_users_created ON users(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_users_display_name ON users(display_name);
CREATE TABLE IF NOT EXISTS sessions (
  token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  csrf_token TEXT NOT NULL, expires_at TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE TABLE IF NOT EXISTS sources (
  id INTEGER PRIMARY KEY, kind TEXT NOT NULL, title TEXT NOT NULL,
  authority TEXT NOT NULL, url TEXT NOT NULL UNIQUE, summary TEXT NOT NULL,
  jurisdiction TEXT NOT NULL DEFAULT '中国大陆', verified_at TEXT NOT NULL,
  access_policy TEXT NOT NULL DEFAULT 'link-only'
);
CREATE INDEX IF NOT EXISTS idx_sources_kind ON sources(kind);
CREATE TABLE IF NOT EXISTS info_requests (
  id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id),
  title TEXT NOT NULL, category TEXT NOT NULL, region TEXT NOT NULL,
  description TEXT NOT NULL, purpose TEXT NOT NULL,
  reward_cents INTEGER NOT NULL DEFAULT 0 CHECK(reward_cents >= 0),
  deadline TEXT, status TEXT NOT NULL DEFAULT 'pending'
    CHECK(status IN ('pending','approved','rejected','closed')),
  platform_verified INTEGER NOT NULL DEFAULT 0 CHECK(platform_verified IN (0,1)),
  verification_basis TEXT,
  review_note TEXT, reviewed_by TEXT REFERENCES users(id),
  reviewed_at TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_requests_status ON info_requests(status,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_requests_owner ON info_requests(owner_id,created_at DESC);
CREATE TABLE IF NOT EXISTS conversations (
  id TEXT PRIMARY KEY, request_id TEXT NOT NULL REFERENCES info_requests(id),
  requester_id TEXT NOT NULL REFERENCES users(id),
  provider_id TEXT NOT NULL REFERENCES users(id), created_at TEXT NOT NULL,
  UNIQUE(request_id,provider_id)
);
CREATE INDEX IF NOT EXISTS idx_conversations_requester ON conversations(requester_id);
CREATE INDEX IF NOT EXISTS idx_conversations_provider ON conversations(provider_id);
CREATE TABLE IF NOT EXISTS messages (
  id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL REFERENCES conversations(id),
  sender_id TEXT NOT NULL REFERENCES users(id), body TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id,created_at);
CREATE INDEX IF NOT EXISTS idx_messages_created ON messages(created_at DESC);
CREATE TABLE IF NOT EXISTS lawyer_profiles (
  user_id TEXT PRIMARY KEY REFERENCES users(id), license_no TEXT NOT NULL,
  firm TEXT NOT NULL, years INTEGER NOT NULL CHECK(years >= 0),
  region TEXT NOT NULL, specialties_json TEXT NOT NULL, social_url TEXT,
  bio TEXT NOT NULL, case_summary TEXT NOT NULL DEFAULT '',
  legal_name TEXT NOT NULL DEFAULT '', gender TEXT NOT NULL DEFAULT '',
  id_number TEXT NOT NULL DEFAULT '', practice_start TEXT NOT NULL DEFAULT '',
  honors TEXT NOT NULL DEFAULT '', contact_phone TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK(status IN ('pending','verified','rejected')),
  verified_at TEXT, verified_by TEXT REFERENCES users(id), verification_source TEXT,
  review_note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_lawyers_status ON lawyer_profiles(status);
CREATE TABLE IF NOT EXISTS lawyer_evidence (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  kind TEXT NOT NULL CHECK(kind IN ('portrait','id_front','id_back','license_front','license_record')),
  mime TEXT NOT NULL CHECK(mime IN ('image/jpeg','image/png','image/webp')),
  content BLOB NOT NULL, created_at TEXT NOT NULL,
  UNIQUE(user_id,kind)
);
CREATE INDEX IF NOT EXISTS idx_lawyer_evidence_user ON lawyer_evidence(user_id);
CREATE TABLE IF NOT EXISTS custom_document_templates (
  id TEXT PRIMARY KEY, category TEXT NOT NULL, title TEXT NOT NULL,
  purpose TEXT NOT NULL, fields_json TEXT NOT NULL, paragraphs_json TEXT NOT NULL,
  intake_prompt TEXT NOT NULL, source_url TEXT, active INTEGER NOT NULL DEFAULT 1,
  created_by TEXT NOT NULL REFERENCES users(id), created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_custom_templates_active ON custom_document_templates(active,category,title);
CREATE TABLE IF NOT EXISTS official_updates (
  id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('law','exam','case')),
  title TEXT NOT NULL, source_url TEXT NOT NULL UNIQUE, authority TEXT NOT NULL,
  published_at TEXT, discovered_at TEXT NOT NULL, summary TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_official_updates_kind_date ON official_updates(kind,published_at DESC,discovered_at DESC);
CREATE TABLE IF NOT EXISTS sync_runs (
  source_key TEXT NOT NULL, run_day TEXT NOT NULL, status TEXT NOT NULL,
  item_count INTEGER NOT NULL DEFAULT 0, error TEXT NOT NULL DEFAULT '',
  started_at TEXT NOT NULL, finished_at TEXT, PRIMARY KEY(source_key,run_day)
);
CREATE TABLE IF NOT EXISTS exam_papers (
  id TEXT PRIMARY KEY, year INTEGER NOT NULL, title TEXT NOT NULL,
  subject TEXT NOT NULL, paper_type TEXT NOT NULL, source_url TEXT NOT NULL UNIQUE,
  authority TEXT NOT NULL, rights_status TEXT NOT NULL
    CHECK(rights_status IN ('link-only','licensed','public-domain','permission')),
  verified_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_exam_papers_year ON exam_papers(year,subject);
CREATE TABLE IF NOT EXISTS exam_questions (
  id TEXT PRIMARY KEY, paper_id TEXT NOT NULL REFERENCES exam_papers(id),
  question_no TEXT NOT NULL, subject TEXT NOT NULL, stem TEXT NOT NULL,
  options_json TEXT NOT NULL, answer TEXT, explanation TEXT,
  source_url TEXT NOT NULL, rights_status TEXT NOT NULL
    CHECK(rights_status IN ('licensed','public-domain','permission')),
  provenance TEXT NOT NULL, created_at TEXT NOT NULL,
  UNIQUE(paper_id,question_no)
);
CREATE INDEX IF NOT EXISTS idx_exam_questions_subject ON exam_questions(subject);
CREATE TABLE IF NOT EXISTS mock_exam_sessions (
  id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  subject TEXT NOT NULL, total_questions INTEGER NOT NULL CHECK(total_questions IN (5,10)),
  current_position INTEGER NOT NULL DEFAULT 1, status TEXT NOT NULL DEFAULT 'active'
    CHECK(status IN ('active','generating','completed')),
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_mock_sessions_owner ON mock_exam_sessions(owner_id,created_at DESC);
CREATE TABLE IF NOT EXISTS mock_exam_questions (
  id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES mock_exam_sessions(id) ON DELETE CASCADE,
  position INTEGER NOT NULL, subject TEXT NOT NULL, kind TEXT NOT NULL
    CHECK(kind IN ('single','multiple')),
  stem TEXT NOT NULL, options_json TEXT NOT NULL, answer_keys_json TEXT NOT NULL,
  explanation TEXT NOT NULL, knowledge_point TEXT NOT NULL,
  model_name TEXT NOT NULL, selected_keys_json TEXT,
  is_correct INTEGER CHECK(is_correct IN (0,1)), answered_at TEXT, created_at TEXT NOT NULL,
  UNIQUE(session_id,position)
);
CREATE INDEX IF NOT EXISTS idx_mock_questions_session ON mock_exam_questions(session_id,position);
CREATE INDEX IF NOT EXISTS idx_mock_questions_created ON mock_exam_questions(created_at);
CREATE TABLE IF NOT EXISTS document_drafts (
  id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id),
  template_id TEXT NOT NULL, title TEXT NOT NULL, content TEXT NOT NULL,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_document_drafts_owner ON document_drafts(owner_id,updated_at DESC);
CREATE TABLE IF NOT EXISTS document_conversations (
  id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  scenario_id TEXT NOT NULL, facts_json TEXT NOT NULL, messages_json TEXT NOT NULL,
  draft_id TEXT REFERENCES document_drafts(id), artifact_id TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_document_conversations_owner ON document_conversations(owner_id,updated_at DESC);
CREATE TABLE IF NOT EXISTS office_artifacts (
  id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  kind TEXT NOT NULL CHECK(kind IN ('word','excel','ppt')),
  title TEXT NOT NULL, payload_json TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_office_artifacts_owner ON office_artifacts(owner_id,created_at DESC);
CREATE TABLE IF NOT EXISTS audit_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, actor_id TEXT,
  action TEXT NOT NULL, entity_type TEXT NOT NULL, entity_id TEXT NOT NULL,
  detail TEXT NOT NULL, created_at TEXT NOT NULL
);
"""


SOURCE_SEED = [
    ("law", "国家法律法规数据库", "全国人大常委会办公厅", "https://flk.npc.gov.cn/search", "检索法律法规、效力状态和历史版本；具体条文以原站为准。"),
    ("law", "国家行政法规库", "司法部", "https://xzfg.moj.gov.cn/", "检索行政法规现行文本与历史沿革。"),
    ("case", "人民法院案例库", "最高人民法院", "https://rmfyalk.court.gov.cn/", "检索指导性案例与参考案例；用于类案参考。"),
    ("service", "国家政务服务平台", "国务院办公厅", "https://gjzwfw.www.gov.cn/", "按地区查找办事指南、材料和官方办理入口。"),
    ("company", "国家企业信用信息公示系统", "国家市场监督管理总局", "https://www.gsxt.gov.cn/", "查询公开的企业登记、股东及出资信息；部分查询可能要求实名。"),
    ("lawyer", "全国律师诚信信息公示平台", "中华全国律师协会", "https://credit.acla.org.cn/", "查询律师与律师事务所公开的执业和诚信信息。"),
    ("service", "12348 中国法网", "司法部", "https://www.12348.gov.cn/", "公共法律咨询、援助和法律服务指引。"),
]

# Only live directory metadata and links are shipped. Several historical item URLs
# within the Ministry's archive returned 404 during the 2026-10-28 check.
EXAM_PAPER_SEED = [
    ("moj-2017-index", 2017, "2017 年国家司法考试试题及参考答案发布目录", "综合", "官方发布目录", "https://www.moj.gov.cn/fzgz/fzgzggflfwx/fzgzflzyzgks/index_12.html"),
    ("moj-2016-index", 2016, "2016 年国家司法考试试卷与参考答案目录", "综合", "官方试卷目录", "https://www.moj.gov.cn/jgsz/jgszzsdw/zsdwgjsfkszx/gjsfkskskt/index_1.html"),
    ("moj-2015-papers", 2015, "2015 年国家司法考试试卷目录", "综合", "官方试卷目录", "https://www.moj.gov.cn/jgsz/jgszzsdw/zsdwgjsfkszx/gjsfkskskt/index_2.html"),
    ("moj-2014-index", 2014, "2014 年国家司法考试试卷目录（含卷二、卷三）", "综合", "官方试卷目录", "https://www.moj.gov.cn/jgsz/jgszzsdw/zsdwgjsfkszx/gjsfkskskt/index_3.html"),
    ("moj-2013-index", 2013, "2013 年国家司法考试试卷与参考答案目录", "综合", "官方试卷目录", "https://www.moj.gov.cn/jgsz/jgszzsdw/zsdwgjsfkszx/gjsfksfzkjj/index_8.html"),
]


def initialize() -> None:
    with connection() as con:
        con.execute("PRAGMA journal_mode=WAL")
        con.executescript(SCHEMA)
        if "phone" not in {row[1] for row in con.execute("PRAGMA table_info(users)")}:
            con.execute("ALTER TABLE users ADD COLUMN phone TEXT NOT NULL DEFAULT ''")
        con.execute("CREATE INDEX IF NOT EXISTS idx_users_phone ON users(phone) WHERE phone != ''")
        profile_columns = {row[1] for row in con.execute("PRAGMA table_info(lawyer_profiles)")}
        for name in ("legal_name", "gender", "id_number", "practice_start", "honors", "contact_phone", "review_note"):
            if name not in profile_columns:
                con.execute(f"ALTER TABLE lawyer_profiles ADD COLUMN {name} TEXT NOT NULL DEFAULT ''")
        if "artifact_id" not in {row[1] for row in con.execute("PRAGMA table_info(document_conversations)")}:
            con.execute("ALTER TABLE document_conversations ADD COLUMN artifact_id TEXT")
        # Remove superseded/dead seed URLs from earlier local versions.
        con.execute("DELETE FROM exam_papers WHERE rights_status='link-only' AND (id LIKE 'moj-%-paper-%' OR id LIKE 'moj-%-answer-%')")
        con.execute("DELETE FROM exam_papers WHERE rights_status='link-only' AND id IN ('moj-2017-release','moj-2015-index','moj-2014-index','moj-2015-answers','moj-2014-papers')")
        con.execute("UPDATE exam_papers SET title=?,source_url=? WHERE id='moj-2016-index'",
                    (EXAM_PAPER_SEED[1][2], EXAM_PAPER_SEED[1][5]))
        con.execute("UPDATE exam_papers SET title=?,source_url=? WHERE id='moj-2013-index'",
                    (EXAM_PAPER_SEED[-1][2], EXAM_PAPER_SEED[-1][5]))
        now = "2026-10-28"  # Source catalog research date, not a fresh check on every restart.
        con.executemany(
            "INSERT OR IGNORE INTO sources(kind,title,authority,url,summary,verified_at) VALUES (?,?,?,?,?,?)",
            [(kind, title, authority, url, summary, now) for kind, title, authority, url, summary in SOURCE_SEED],
        )
        con.executemany(
            "INSERT OR IGNORE INTO exam_papers(id,year,title,subject,paper_type,source_url,authority,rights_status,verified_at) VALUES (?,?,?,?,?,?,?,?,?)",
            [(id_, year, title, subject, paper_type, url, "司法部", "link-only", now)
             for id_, year, title, subject, paper_type, url in EXAM_PAPER_SEED],
        )


def audit(con: sqlite3.Connection, actor_id: str | None, action: str, kind: str, entity_id: str, detail: str = "") -> None:
    con.execute(
        "INSERT INTO audit_events(actor_id,action,entity_type,entity_id,detail,created_at) VALUES (?,?,?,?,?,?)",
        (actor_id, action, kind, entity_id, detail[:500], utcnow()),
    )


def rows(items: list[sqlite3.Row]) -> list[dict]:
    return [dict(item) for item in items]
