import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from legal_service.app import create_app
from legal_service.cli import import_exam
from legal_service.db import initialize


class ExamSearchTests(unittest.TestCase):
    def test_official_links_and_rights_checked_question_import(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"APP_DATA_DIR": temp}):
            initialize()
            with TestClient(create_app()) as client:
                papers = client.get("/api/v1/exam/papers?q=2016").json()["items"]
                self.assertEqual(len(papers), 1)
                self.assertTrue(all(paper["rights_status"] == "link-only" for paper in papers))
                self.assertTrue(any(paper["paper_type"] == "官方试卷目录" for paper in papers))
                self.assertEqual(client.get("/api/v1/exam/questions?q=合同").json()["items"], [])
                path = Path(temp) / "questions.jsonl"
                path.write_text(json.dumps({
                    "paper": {"id": "licensed-test", "year": 2016, "title": "授权测试卷",
                              "subject": "民法", "paper_type": "客观题",
                              "source_url": "https://example.org/paper", "authority": "测试授权方"},
                    "question": {"number": "1", "stem": "合同履行的练习题（测试数据）",
                                 "options": ["A. 示例", "B. 示例"], "answer": "A",
                                 "source_url": "https://example.org/question/1"}
                }, ensure_ascii=False) + "\n", encoding="utf-8")
                with self.assertRaises(ValueError):
                    import_exam(path, "licensed", "http://example.org/rights")
                import_exam(path, "licensed", "https://example.org/rights")
                found = client.get("/api/v1/exam/questions?q=合同&year=2016").json()["items"]
                self.assertEqual(len(found), 1)
                self.assertEqual(found[0]["answer"], "A")
                self.assertEqual(client.get("/api/v1/exam/questions?q=劳动").json()["items"], [])


if __name__ == "__main__":
    unittest.main()
