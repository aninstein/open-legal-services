import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from legal_service.app import create_app
from legal_service.db import connection
from legal_service.source_sync import discover


class AdminFeatureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.environment = patch.dict(os.environ, {"APP_DATA_DIR": self.temp.name, "APP_SYNC_ENABLED": "false"})
        self.environment.start()
        self.client = TestClient(create_app())
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.environment.stop()
        self.temp.cleanup()

    def register(self, email, name):
        client = TestClient(self.client.app)
        result = client.post("/api/v1/auth/register", json={"email": email, "display_name": name,
                                                           "password": "long-test-password-123"})
        self.assertEqual(result.status_code, 201, result.text)
        return client, result.json()["user"], {"X-CSRF-Token": result.json()["csrf_token"]}

    def test_profile_roles_and_template_chat(self):
        admin, admin_user, admin_headers = self.register("admin@example.com", "管理员")
        ordinary, ordinary_user, ordinary_headers = self.register("ordinary@example.com", "普通用户")
        with connection() as con:
            con.execute("UPDATE users SET role='admin' WHERE id=?", (admin_user["id"],))
        self.assertEqual(ordinary.get("/api/v1/admin/users").status_code, 403)
        updated = ordinary.put("/api/v1/profile", json={"display_name": "更新用户", "email": "updated@example.com",
                                                         "phone": "13800138000"}, headers=ordinary_headers)
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(ordinary.get("/api/v1/profile").json()["phone"], "13800138000")
        users = admin.get("/api/v1/admin/users?q=updated").json()
        self.assertEqual(users["total"], 1)
        promoted = admin.patch(f"/api/v1/admin/users/{ordinary_user['id']}/role",
                               json={"role": "admin"}, headers=admin_headers)
        self.assertEqual(promoted.status_code, 200, promoted.text)
        self.assertEqual(ordinary.get("/api/v1/admin/users").status_code, 200)
        demote_self = admin.patch(f"/api/v1/admin/users/{admin_user['id']}/role",
                                  json={"role": "user"}, headers=admin_headers)
        self.assertEqual(demote_self.status_code, 422)

        template = admin.post("/api/v1/admin/document-templates", json={
            "category": "居住租赁", "title": "房屋交接记录", "purpose": "记录房屋交接时的基本事实",
            "fields": [{"key": "tenant", "label": "承租人", "level": "required"},
                       {"key": "address", "label": "房屋地址", "level": "required"},
                       {"key": "date", "label": "交接日期", "level": "recommended"}],
            "paragraphs": ["承租人 {tenant} 于 {date} 对 {address} 的房屋状态进行交接确认。"]
        }, headers=admin_headers)
        self.assertEqual(template.status_code, 201, template.text)
        template_id = template.json()["id"]
        catalog = ordinary.get("/api/v1/documents/scenarios").json()["items"]
        self.assertIn(template_id, [item["id"] for item in catalog])
        started = ordinary.post("/api/v1/documents/conversations", json={"scenario_id": template_id},
                                headers=ordinary_headers)
        self.assertEqual(started.status_code, 201, started.text)
        archived = admin.patch(f"/api/v1/admin/document-templates/{template_id}/archive", headers=admin_headers)
        self.assertEqual(archived.status_code, 200, archived.text)
        self.assertEqual(ordinary.get(f"/api/v1/documents/conversations/{started.json()['id']}").status_code, 200)
        self.assertEqual(ordinary.post("/api/v1/documents/conversations", json={"scenario_id": template_id},
                                       headers=ordinary_headers).status_code, 404)

    def test_official_parser_accepts_only_matching_official_links(self):
        html = '<a href="/zhengce/content/202610/content_123.htm">事业单位登记管理条例</a>'
        html += '<a href="https://evil.example/zhengce/content/202610/content_999.htm">伪造法律条例</a>'
        items = discover("law", html, "https://www.gov.cn/zhengce/")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["published_at"], "2026-10")
        exam_html = '<a href="/pub/202606/t20260605_1.html">2026年国家统一法律职业资格考试公告</a>'
        exam_html += '<a href="/jgsz/202105/t20210501_2.html">负责国家统一法律职业资格考试组织实施工作，编审试题并管理证书的机构职能说明，负责组织培训和指导法学教育的相关工作。</a>'
        notices = discover("exam", exam_html, "https://www.moj.gov.cn/jgsz/jgszjgtj/flzyzgglj/")
        self.assertEqual([item["title"] for item in notices], ["2026年国家统一法律职业资格考试公告"])


if __name__ == "__main__":
    unittest.main()
