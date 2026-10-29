import os
import tempfile
import unittest
from io import BytesIO
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image

from legal_service.app import create_app
from legal_service.db import connection


class ProductFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.environment = patch.dict(os.environ, {"APP_DATA_DIR": self.temp.name}, clear=False)
        self.environment.start()
        self.client = TestClient(create_app())
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.environment.stop()
        self.temp.cleanup()

    def register(self, email, name):
        client = TestClient(self.client.app)
        response = client.post("/api/v1/auth/register", json={
            "email": email, "display_name": name, "password": "long-test-password-123"
        })
        self.assertEqual(response.status_code, 201, response.text)
        return client, response.json()["user"], response.json()["csrf_token"]

    def test_request_moderation_and_conversation_isolation(self):
        owner, owner_user, owner_csrf = self.register("owner@example.com", "求取用户")
        provider, provider_user, provider_csrf = self.register("provider@example.com", "提供用户")
        outsider, _, outsider_csrf = self.register("outsider@example.com", "其他用户")
        request_body = {
            "title": "寻找公开劳动仲裁办事指南", "category": "劳动", "region": "北京市朝阳区",
            "description": "希望找到现行官方劳动仲裁申请材料清单和线上申请入口。",
            "purpose": "用于本人准备提交劳动仲裁申请材料。", "reward_yuan": 80,
        }
        missing_csrf = owner.post("/api/v1/info-requests", json=request_body)
        self.assertEqual(missing_csrf.status_code, 403)
        created = owner.post("/api/v1/info-requests", json=request_body,
                             headers={"X-CSRF-Token": owner_csrf})
        self.assertEqual(created.status_code, 201, created.text)
        request_id = created.json()["id"]
        self.assertEqual(self.client.get("/api/v1/info-requests").json()["items"], [])
        self.assertEqual(provider.get(f"/api/v1/info-requests/{request_id}").status_code, 404)
        self.assertEqual(owner.get("/api/v1/info-requests/mine").json()["items"][0]["status"], "pending")

        with connection() as con:
            con.execute("UPDATE users SET role='admin' WHERE id=?", (owner_user["id"],))
        reviewed = owner.patch(f"/api/v1/admin/info-requests/{request_id}",
                               json={"status": "approved", "platform_verified": True,
                                     "verification_basis": "已核对测试主体资料和信息用途"},
                               headers={"X-CSRF-Token": owner_csrf})
        self.assertEqual(reviewed.status_code, 200, reviewed.text)
        self.assertEqual(len(self.client.get("/api/v1/info-requests").json()["items"]), 1)
        started = provider.post(f"/api/v1/info-requests/{request_id}/conversations",
                                headers={"X-CSRF-Token": provider_csrf})
        self.assertEqual(started.status_code, 201, started.text)
        conversation_id = started.json()["id"]
        self.assertEqual(outsider.get(f"/api/v1/conversations/{conversation_id}/messages").status_code, 404)
        sent = provider.post(f"/api/v1/conversations/{conversation_id}/messages",
                             json={"body": "我找到主管部门发布的公开指南链接。"},
                             headers={"X-CSRF-Token": provider_csrf})
        self.assertEqual(sent.status_code, 201, sent.text)
        self.assertEqual(len(owner.get(f"/api/v1/conversations/{conversation_id}/messages").json()["items"]), 1)
        self.assertEqual(outsider.get("/api/v1/admin/conversations").status_code, 403)
        self.assertEqual(owner.get("/api/v1/admin/conversations").status_code, 200)
        self.assertEqual(owner.get(f"/api/v1/admin/conversations/{conversation_id}/messages").json()["items"][0]["body"],
                         "我找到主管部门发布的公开指南链接。")
        self.assertEqual(outsider.post(f"/api/v1/conversations/{conversation_id}/messages",
                                      json={"body": "我不是会话参与者，不能发消息。"},
                                      headers={"X-CSRF-Token": outsider_csrf}).status_code, 404)

    def test_drafts_are_private_and_lawyer_profile_requires_review(self):
        first, first_user, first_csrf = self.register("first@example.com", "第一用户")
        second, _, second_csrf = self.register("second@example.com", "第二用户")
        draft = first.post("/api/v1/documents/drafts", json={"template_id": "loan-demand", "fields": {
            "borrower": "借款人", "lender": "出借人", "loan_date": "2025 年 1 月 1 日",
            "amount": "1000", "deadline": "2026 年 11 月 1 日"
        }}, headers={"X-CSRF-Token": first_csrf})
        self.assertEqual(draft.status_code, 201, draft.text)
        self.assertEqual(second.get(f"/api/v1/documents/drafts/{draft.json()['id']}").status_code, 404)
        self.assertEqual(second.put(f"/api/v1/documents/drafts/{draft.json()['id']}",
                                    json={"content": "对他人的文书进行越权修改，应当被系统拒绝。"},
                                    headers={"X-CSRF-Token": second_csrf}).status_code, 404)
        edited = first.put(f"/api/v1/documents/drafts/{draft.json()['id']}",
                           json={"content": "借款催告函：请于约定期限内履行还款义务，并保留沟通记录。"},
                           headers={"X-CSRF-Token": first_csrf})
        self.assertEqual(edited.status_code, 200, edited.text)
        self.assertIn("保留沟通记录", first.get(f"/api/v1/documents/drafts/{draft.json()['id']}").json()["content"])
        profile = first.put("/api/v1/lawyers/profile/mine", json={
            "license_no": "TEST-123456", "firm": "测试律师事务所", "years": 5,
            "region": "北京", "specialties": ["劳动争议"], "bio": "这是用于测试的律师资料说明。",
            "legal_name": "测试律师", "id_number": "110101199001011234", "practice_start": "2021-01-01",
            "contact_phone": "13800138000"
        }, headers={"X-CSRF-Token": first_csrf})
        self.assertEqual(profile.status_code, 200, profile.text)
        self.assertEqual(self.client.get("/api/v1/lawyers").json()["items"], [])
        with connection() as con:
            con.execute("UPDATE users SET role='admin' WHERE email='second@example.com'")
        missing = second.patch(f"/api/v1/admin/lawyers/{first_user['id']}",
                               json={"status":"verified", "verification_source":"https://credit.acla.org.cn/"},
                               headers={"X-CSRF-Token": second_csrf})
        self.assertEqual(missing.status_code, 422)
        image_buffer = BytesIO()
        Image.new("RGB", (128, 128), "white").save(image_buffer, format="PNG")
        for kind in ("portrait", "id_front", "id_back", "license_front", "license_record"):
            upload = first.post(f"/api/v1/lawyers/evidence/{kind}",
                                files={"file": ("evidence.png", image_buffer.getvalue(), "image/png")},
                                headers={"X-CSRF-Token": first_csrf})
            self.assertEqual(upload.status_code, 200, upload.text)
            self.assertEqual(second.get(f"/api/v1/lawyers/evidence/{first_user['id']}/{kind}").status_code, 200)
            self.assertEqual(first.get(f"/api/v1/lawyers/evidence/{first_user['id']}/{kind}").status_code, 200)
            self.assertEqual(self.client.get(f"/api/v1/lawyers/evidence/{first_user['id']}/{kind}").status_code, 401)
        reviewed = second.patch(f"/api/v1/admin/lawyers/{first_user['id']}",
                                json={"status":"verified", "verification_source":"https://credit.acla.org.cn/"},
                                headers={"X-CSRF-Token": second_csrf})
        self.assertEqual(reviewed.status_code, 200, reviewed.text)
        listing = self.client.get("/api/v1/lawyers").json()["items"]
        self.assertEqual(len(listing), 1)
        self.assertNotIn("license_no", listing[0])


if __name__ == "__main__":
    unittest.main()
