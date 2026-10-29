"""Daily metadata discovery from accessible official publication indexes.

This stores titles and links, not legal conclusions, case files or exam questions.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

from .db import connection, utcnow

FEEDS = {
    "law": ("国务院政策发布", "https://www.gov.cn/zhengce/"),
    "exam": ("司法部法律职业资格管理局", "https://www.moj.gov.cn/jgsz/jgszjgtj/flzyzgglj/"),
    "case": ("最高人民法院典型案例发布", "https://www.court.gov.cn/zixun/gengduo/104_3.html"),
}
LAW_WORDS = ("法律", "条例", "行政法规", "国务院令", "决定", "办法", "规定")
EXAM_WORDS = ("法律职业资格考试", "司法考试", "法考")
EXAM_NOTICE_WORDS = ("公告", "报名", "成绩公布", "证书颁发", "试题及参考答案", "考试大纲", "政策规定问答")
CASE_WORDS = ("典型案例", "指导性案例", "参考案例")


def relevant_exam_title(title: str) -> bool:
    return (len(title) <= 110 and any(word in title for word in EXAM_WORDS)
            and any(word in title for word in EXAM_NOTICE_WORDS))


class Links(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.items: list[tuple[str, str]] = []
        self.href: str | None = None
        self.text: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            values = dict(attrs)
            self.href = values.get("href")
            self.text = []

    def handle_data(self, data):
        if self.href is not None:
            self.text.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self.href:
            title = " ".join("".join(self.text).split())
            if title:
                self.items.append((title, self.href))
            self.href = None
            self.text = []


def discover(kind: str, html: str, base: str) -> list[dict]:
    parser = Links()
    parser.feed(html)
    words = {"law": LAW_WORDS, "exam": EXAM_WORDS, "case": CASE_WORDS}[kind]
    host = urlsplit(base).hostname
    found: dict[str, dict] = {}
    for title, href in parser.items:
        url = urljoin(base, href).replace("http://www.moj.gov.cn", "https://www.moj.gov.cn")
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname != host or len(title) < 8:
            continue
        if not any(word in title for word in words):
            continue
        if kind == "exam" and not relevant_exam_title(title):
            continue
        if kind == "law" and not ("/zhengce/content/" in parsed.path or "/zhengce/" in parsed.path and parsed.path.endswith(".htm")):
            continue
        if kind == "case" and "/zixun/xiangqing/" not in parsed.path:
            continue
        if kind == "exam" and not parsed.path.endswith(".html"):
            continue
        clean = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
        month = re.search(r"/((?:20)\d{2})(0[1-9]|1[0-2])(?:/|_)", parsed.path)
        published = f"{month.group(1)}-{month.group(2)}" if month else None
        found[clean] = {"kind": kind, "title": title[:180], "source_url": clean,
                        "authority": FEEDS[kind][0], "published_at": published}
    return list(found.values())[:100]


def sync_one(kind: str, *, force: bool = False) -> dict:
    if kind not in FEEDS:
        raise ValueError("unknown source")
    day, now = utcnow()[:10], utcnow()
    with connection() as con:
        previous = con.execute("SELECT status,item_count FROM sync_runs WHERE source_key=? AND run_day=?", (kind, day)).fetchone()
        if previous and previous["status"] == "success" and not force:
            return {"kind": kind, "status": "already_synced", "items": previous["item_count"]}
        con.execute("""INSERT INTO sync_runs(source_key,run_day,status,started_at) VALUES (?,?,'running',?)
                       ON CONFLICT(source_key,run_day) DO UPDATE SET status='running',started_at=excluded.started_at,error=''""",
                    (kind, day, now))
    try:
        with httpx.Client(timeout=12, follow_redirects=True, headers={"User-Agent": "OpenLegalServices/0.1 (+official metadata monitor)"}) as client:
            response = client.get(FEEDS[kind][1])
            response.raise_for_status()
            items = discover(kind, response.text, FEEDS[kind][1])
        if not items:
            raise ValueError("官方页面未解析出匹配条目")
        with connection() as con:
            if kind == "exam":
                for old in con.execute("SELECT id,title FROM official_updates WHERE kind='exam'").fetchall():
                    if not relevant_exam_title(old["title"]):
                        con.execute("DELETE FROM official_updates WHERE id=?", (old["id"],))
            for item in items:
                con.execute("""INSERT OR IGNORE INTO official_updates
                               (id,kind,title,source_url,authority,published_at,discovered_at,summary)
                               VALUES (?,?,?,?,?,?,?,?)""",
                            (hashlib.sha256(item["source_url"].encode()).hexdigest()[:32], kind, item["title"],
                             item["source_url"], item["authority"], item["published_at"], utcnow(),
                             "仅收录官方页面标题与链接；正文、效力和适用范围请到原站核对。"))
            con.execute("UPDATE sync_runs SET status='success',item_count=?,finished_at=?,error='' WHERE source_key=? AND run_day=?",
                        (len(items), utcnow(), kind, day))
        return {"kind": kind, "status": "success", "items": len(items)}
    except Exception as exc:
        with connection() as con:
            con.execute("UPDATE sync_runs SET status='failed',error=?,finished_at=? WHERE source_key=? AND run_day=?",
                        (f"{type(exc).__name__}: {exc}"[:300], utcnow(), kind, day))
        return {"kind": kind, "status": "failed", "error": f"{type(exc).__name__}: {exc}"[:300]}


def sync_all(*, force: bool = False) -> list[dict]:
    return [sync_one(kind, force=force) for kind in FEEDS]


async def daily_loop():
    await asyncio.sleep(5)
    while True:
        try:
            await asyncio.to_thread(sync_all)
        except Exception:
            pass
        await asyncio.sleep(3600)
