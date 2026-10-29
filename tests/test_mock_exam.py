import json
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from legal_service.app import create_app
from legal_service.exam_practice import GenerationError, _parse_question


def sample_question(kind="single"):
    return {"subject": "民法", "kind": kind, "stem": "甲与乙签订合同后发生争议，按照一般规则应当如何处理？",
            "options": {"A": "先核对合同约定", "B": "完全忽略合同约定", "C": "只凭一方口述处理", "D": "未经核对直接销毁材料"},
            "answer_keys": ["A"] if kind == "single" else ["A", "C"],
            "explanation": "应当先核对合同约定及事实材料，其他做法缺少必要的事实基础。",
            "knowledge_point": "合同争议处理", "model_name": "test-model"}


class MockExamTests(unittest.TestCase):
    def test_generation_validation(self):
        data = sample_question("multiple")
        raw = json.dumps({key: data[key] for key in ("stem", "options", "answer_keys", "explanation", "knowledge_point")}, ensure_ascii=False)
        self.assertEqual(_parse_question(raw, "民法", "multiple", "test-model")["answer_keys"], ["A", "C"])
        array_data = {**data, "options": list(data["options"].values())}
        array_raw = json.dumps({key: array_data[key] for key in ("stem", "options", "answer_keys", "explanation", "knowledge_point")}, ensure_ascii=False)
        self.assertEqual(len(_parse_question(array_raw, "民法", "multiple", "test-model")["options"]), 4)
        with self.assertRaises(GenerationError):
            _parse_question(raw.replace('"A", "C"', '"A"'), "民法", "multiple", "test-model")

    def test_private_session_grading_and_completion(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"APP_DATA_DIR": temp}):
            with TestClient(create_app()) as app:
                owner = TestClient(app.app)
                other = TestClient(app.app)
                owner_auth = owner.post("/api/v1/auth/register", json={"email": "mock-owner@example.com", "display_name": "模拟用户", "password": "long-test-password-123"})
                other_auth = other.post("/api/v1/auth/register", json={"email": "mock-other@example.com", "display_name": "其他用户", "password": "long-test-password-123"})
                owner_header = {"X-CSRF-Token": owner_auth.json()["csrf_token"]}
                other_header = {"X-CSRF-Token": other_auth.json()["csrf_token"]}
                url = "/api/v1/exam/mock-sessions"
                with patch("legal_service.exam_practice.generate_question", new=AsyncMock(side_effect=[sample_question(), sample_question("multiple"), sample_question(), sample_question(), sample_question()])):
                    self.assertEqual(owner.post(url, json={"subject": "民法", "count": 5}).status_code, 403)
                    started = owner.post(url, json={"subject": "民法", "count": 5}, headers=owner_header)
                    self.assertEqual(started.status_code, 201, started.text)
                    data = started.json()
                    session_url = f"{url}/{data['id']}"
                    self.assertNotIn("answer_keys", data["question"])
                    self.assertNotIn("explanation", data["question"])
                    self.assertEqual(other.get(session_url).status_code, 404)
                    self.assertEqual(other.post(f"{session_url}/answer", json={"selected_keys": ["A"]}, headers=other_header).status_code, 404)
                    self.assertEqual(owner.post(f"{session_url}/next", headers=owner_header).status_code, 409)
                    wrong = owner.post(f"{session_url}/answer", json={"selected_keys": ["B"]}, headers=owner_header)
                    self.assertEqual(wrong.status_code, 200, wrong.text)
                    self.assertFalse(wrong.json()["question"]["is_correct"])
                    self.assertEqual(wrong.json()["question"]["answer_keys"], ["A"])
                    self.assertEqual(owner.post(f"{session_url}/answer", json={"selected_keys": ["A"]}, headers=owner_header).status_code, 409)
                    for position in range(2, 6):
                        nxt = owner.post(f"{session_url}/next", headers=owner_header)
                        self.assertEqual(nxt.status_code, 200, nxt.text)
                        self.assertEqual(nxt.json()["current_position"], position)
                        self.assertNotIn("answer_keys", nxt.json()["question"])
                        keys = ["A", "C"] if position == 2 else ["A"]
                        answered = owner.post(f"{session_url}/answer", json={"selected_keys": keys}, headers=owner_header)
                        self.assertEqual(answered.status_code, 200, answered.text)
                    final = answered.json()
                    self.assertEqual(final["status"], "completed")
                    self.assertEqual(final["correct_count"], 4)
                    self.assertEqual(final["points"], 5)
                    self.assertEqual(len(owner.get(url).json()["items"]), 1)
                    self.assertEqual(other.get(url).json()["items"], [])
                    self.assertEqual(owner.post(f"{session_url}/next", headers=owner_header).status_code, 409)


if __name__ == "__main__":
    unittest.main()
