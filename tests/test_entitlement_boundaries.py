import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import application


class EntitlementBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.previous_data_directory = application.state.application_data_directory
        application.state.application_data_directory = Path(self.temporary.name)
        self.client = TestClient(application)
        self.addCleanup(self.client.close)
        self.addCleanup(setattr, application.state, "application_data_directory", self.previous_data_directory)

    def unlicensed_status(self):
        return {
            "can_use": False,
            "status": "unactivated",
            "message": "请先激活软件。",
        }

    def test_unlicensed_blocks_capture_monitor_and_ai_but_not_history_or_export(self):
        with (
            patch.dict(os.environ, {"TAOBAO_MARKET_DEV_LICENSE_BYPASS": "0"}),
            patch("app.get_license_status", side_effect=self.unlicensed_status),
        ):
            protected = (
                self.client.post("/api/projects/1/searches", json={"result_count": 10}),
                self.client.post("/api/competitors/prepare", json={"product_url": "https://item.taobao.com/item.htm?id=123456"}),
                self.client.post("/api/monitor/run-now"),
                self.client.post("/api/settings/ai/test"),
            )
            allowed = (
                self.client.get("/api/competitors"),
                self.client.delete("/api/competitors/123456"),
                self.client.get("/api/competitors/123456/export.zip"),
            )
        for response in protected:
            self.assertEqual(403, response.status_code)
            self.assertEqual("license_required", response.json()["detail"]["code"])
        self.assertEqual(200, allowed[0].status_code)
        self.assertIn(allowed[1].status_code, {404})
        self.assertIn(allowed[2].status_code, {404})

    def test_packaged_runtime_ignores_development_bypass(self):
        with (
            patch.dict(os.environ, {"TAOBAO_MARKET_DEV_LICENSE_BYPASS": "1"}),
            patch("app.get_license_status", side_effect=self.unlicensed_status),
            patch("app.sys.frozen", True, create=True),
        ):
            response = self.client.post("/api/monitor/run-now")
        self.assertEqual(403, response.status_code)

    def test_source_bypass_is_visible_and_explicit(self):
        with (
            patch.dict(os.environ, {"TAOBAO_MARKET_DEV_LICENSE_BYPASS": "1"}),
            patch("app.get_license_status", side_effect=self.unlicensed_status),
        ):
            response = self.client.get("/api/license/status")
        self.assertEqual(200, response.status_code)
        self.assertTrue(response.json()["can_use"])
        self.assertEqual("development_bypass", response.json()["status"])


if __name__ == "__main__":
    unittest.main()
