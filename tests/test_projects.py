from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import application


class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = TemporaryDirectory()
        self.previous_data_directory = getattr(
            application.state,
            "application_data_directory",
            None,
        )
        application.state.application_data_directory = Path(
            self.temporary_directory.name
        )
        self.client = TestClient(application)

    def tearDown(self):
        application.state.application_data_directory = self.previous_data_directory
        self.client.close()
        self.temporary_directory.cleanup()

    def test_create_list_and_reopen_project(self):
        create_response = self.client.post(
            "/api/projects",
            json={"keyword": "  苹果15   手机壳  "},
        )

        self.assertEqual(201, create_response.status_code)
        created_project = create_response.json()
        self.assertEqual("苹果15 手机壳", created_project["keyword"])
        self.assertEqual("苹果15 手机壳", created_project["normalized_keyword"])

        list_response = self.client.get("/api/projects")
        self.assertEqual(200, list_response.status_code)
        self.assertEqual([created_project], list_response.json()["projects"])

        reopened_client = TestClient(application)
        try:
            reopen_response = reopened_client.get(
                f"/api/projects/{created_project['id']}"
            )
        finally:
            reopened_client.close()
        self.assertEqual(200, reopen_response.status_code)
        self.assertEqual(created_project, reopen_response.json())

    def test_normalized_keyword_reuses_existing_search_history(self):
        first_response = self.client.post(
            "/api/projects",
            json={"keyword": "苹果 15 手机壳"},
        )
        duplicate_keyword = "  苹果   15   手机壳  "
        duplicate_response = self.client.post(
            "/api/projects",
            json={"keyword": duplicate_keyword},
        )

        self.assertEqual(201, first_response.status_code)
        self.assertEqual(201, duplicate_response.status_code)
        self.assertEqual(first_response.json()["id"], duplicate_response.json()["id"])
        self.assertEqual("苹果 15 手机壳", duplicate_response.json()["keyword"])
        projects = self.client.get("/api/projects").json()["projects"]
        self.assertEqual(1, len(projects))

    def test_empty_keyword_fails_with_received_value(self):
        empty_keyword = " \t "
        response = self.client.post(
            "/api/projects",
            json={"keyword": empty_keyword},
        )

        self.assertEqual(422, response.status_code)
        self.assertEqual(empty_keyword, response.json()["detail"]["value"])

    def test_too_long_keyword_fails_with_received_value(self):
        too_long_keyword = "壳" * 101
        response = self.client.post(
            "/api/projects",
            json={"keyword": too_long_keyword},
        )

        self.assertEqual(422, response.status_code)
        self.assertEqual(too_long_keyword, response.json()["detail"]["value"])

    def test_project_page_contains_direct_search_and_history(self):
        homepage_response = self.client.get("/")
        script_response = self.client.get("/static/app.js")
        stylesheet_response = self.client.get("/static/styles.css")

        self.assertEqual(200, homepage_response.status_code)
        self.assertIn('id="project-form"', homepage_response.text)
        self.assertIn('id="project-list"', homepage_response.text)
        self.assertIn("搜索历史", homepage_response.text)
        self.assertIn("输入关键词，直接采集", homepage_response.text)
        self.assertNotIn("建立关键词项目", homepage_response.text)
        self.assertEqual(200, script_response.status_code)
        self.assertEqual(200, stylesheet_response.status_code)


if __name__ == "__main__":
    unittest.main()
