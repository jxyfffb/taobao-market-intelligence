from datetime import datetime
from contextlib import closing
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import application
from src.database import connect_database
from src.monitoring import build_windows_task_xml


class MonitoringTests(unittest.TestCase):
    def test_schema_includes_monitor_settings_tasks_and_runs(self):
        with TemporaryDirectory() as directory:
            with closing(connect_database(directory)) as connection:
                table_names = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    )
                }
                settings = connection.execute(
                    "SELECT enabled, run_time FROM monitor_settings WHERE id = 1"
                ).fetchone()
            self.assertTrue({"monitor_settings", "monitor_tasks", "monitor_runs", "shop_snapshots", "shop_snapshot_items"} <= table_names)
            self.assertEqual((0, "10:00"), tuple(settings))

    def test_task_xml_uses_start_when_available_and_ignores_overlap(self):
        task_xml = build_windows_task_xml(
            "10:00",
            now=datetime.fromisoformat("2026-08-14T09:00:00+08:00"),
        )
        self.assertIn("<StartWhenAvailable>true</StartWhenAvailable>", task_xml)
        self.assertIn("<MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>", task_xml)
        self.assertIn("T10:00:00+08:00", task_xml)
        self.assertIn("monitor_runner.py", task_xml)

    def test_keyword_monitor_saves_selected_page_count(self):
        with TemporaryDirectory() as directory:
            previous_directory = application.state.application_data_directory
            application.state.application_data_directory = Path(directory)
            try:
                with TestClient(application) as client:
                    project = client.post("/api/projects", json={"keyword": "男T恤"}).json()
                    added = client.post(
                        f"/api/projects/{project['id']}/monitor/keyword",
                        json={"page_count": 3},
                    )
                    self.assertEqual(201, added.status_code)
                    monitor = client.get("/api/monitor").json()
                    self.assertEqual(3, monitor["tasks"][0]["page_count"])
                    self.assertIn("3 页", added.json()["message"])
            finally:
                application.state.application_data_directory = previous_directory

    def test_monitor_api_adds_keyword_updates_schedule_and_runs_now(self):
        with TemporaryDirectory() as directory:
            previous_directory = application.state.application_data_directory
            application.state.application_data_directory = Path(directory)
            try:
                with TestClient(application) as client:
                    project = client.post("/api/projects", json={"keyword": "男T恤"}).json()
                    added = client.post(f"/api/projects/{project['id']}/monitor/keyword")
                    self.assertEqual(201, added.status_code)

                    with patch("app.install_windows_schedule") as install_schedule:
                        schedule = client.put(
                            "/api/monitor/schedule",
                            json={"enabled": True, "run_time": "10:00"},
                        )
                    self.assertEqual(200, schedule.status_code)
                    install_schedule.assert_called_once()

                    with patch(
                        "app.create_search_snapshot",
                        return_value={"snapshot_id": 12, "result_count": 46},
                    ):
                        run = client.post("/api/monitor/run-now")
                    self.assertEqual(200, run.status_code)
                    self.assertTrue(run.json()["success"])
                    self.assertEqual("success", run.json()["runs"][0]["status"])
                    self.assertEqual(1, run.json()["runs"][0]["success_count"])

                    homepage = client.get("/").text
                    script = client.get("/static/app.js").text
                    self.assertIn('id="monitor-workspace"', homepage)
                    self.assertIn('id="monitor-keyword"', homepage)
                    self.assertIn("/api/monitor/run-now", script)
            finally:
                application.state.application_data_directory = previous_directory

    def test_search_result_can_join_competitor_monitor_without_detail_capture(self):
        with TemporaryDirectory() as directory:
            previous_directory = application.state.application_data_directory
            application.state.application_data_directory = Path(directory)
            try:
                with TestClient(application) as client:
                    project = client.post("/api/projects", json={"keyword": "男T恤"}).json()
                    response = client.post(
                        f"/api/projects/{project['id']}/monitor/competitor",
                        json={
                            "product_url": "https://item.taobao.com/item.htm?id=1234567890",
                            "item_id": "1234567890",
                            "label": "测试竞品",
                        },
                    )
                    self.assertEqual(201, response.status_code)
                    monitor = client.get("/api/monitor").json()
                    self.assertEqual("competitor", monitor["tasks"][0]["task_type"])
                    self.assertEqual("1234567890", monitor["tasks"][0]["item_id"])
                    self.assertEqual("测试竞品", monitor["tasks"][0]["label"])
                    script = client.get("/static/app.js").text
                    homepage = client.get("/").text
                    self.assertIn("/monitor/competitor", script)
                    self.assertIn("collectMonitoredCompetitor", script)
                    self.assertIn("查看竞品资料", script)
                    self.assertIn("竞品采集", script)
                    self.assertIn('id="monitor-change-list"', homepage)
            finally:
                application.state.application_data_directory = previous_directory

    def test_shop_monitor_builds_baseline_and_reports_new_product(self):
        with TemporaryDirectory() as directory:
            previous_directory = application.state.application_data_directory
            application.state.application_data_directory = Path(directory)
            try:
                with TestClient(application) as client:
                    project = client.post("/api/projects", json={"keyword": "男T恤"}).json()
                    added = client.post(
                        f"/api/projects/{project['id']}/monitor/shop",
                        json={
                            "shop_url": "https://example.taobao.com/",
                            "shop_name": "示例旗舰店",
                        },
                    )
                    self.assertEqual(201, added.status_code)
                    base = {
                        "status": "success",
                        "shop_url": "https://example.taobao.com/",
                        "shop_name": "示例旗舰店",
                        "raw_source_ref": str(Path(directory) / "base.json"),
                        "captured_at": "2026-08-14T10:00:00.000001+08:00",
                        "result_count": 1,
                        "products": [{
                            "item_id": "1001", "title": "基础款", "product_url": "https://item.taobao.com/item.htm?id=1001",
                            "image_url": "https://img.alicdn.com/a.jpg", "price_text": "59", "payment_text": "100+人付款",
                        }],
                    }
                    with patch("app.capture_shop_listing", return_value=base):
                        first = client.post("/api/monitor/run-now")
                    self.assertEqual(200, first.status_code)
                    current = {
                        **base,
                        "captured_at": "2026-08-14T10:01:00.000001+08:00",
                        "result_count": 2,
                        "products": base["products"] + [{
                            "item_id": "1002", "title": "今日新品", "product_url": "https://item.taobao.com/item.htm?id=1002",
                            "image_url": "https://img.alicdn.com/b.jpg", "price_text": "69", "payment_text": None,
                        }],
                    }
                    with patch("app.capture_shop_listing", return_value=current):
                        second = client.post("/api/monitor/run-now")
                    self.assertEqual(200, second.status_code)
                    monitor = client.get("/api/monitor").json()
                    self.assertEqual("shop", monitor["tasks"][0]["task_type"])
                    self.assertEqual(2, monitor["tasks"][0]["result_count"])
                    self.assertEqual(2, len(monitor["tasks"][0]["preview_products"]))
                    self.assertEqual("基础款", monitor["tasks"][0]["preview_products"][0]["title"])
                    self.assertEqual(1, monitor["tasks"][0]["recent_new_count"])
                    self.assertEqual("今日新品", monitor["tasks"][0]["recent_new_products"][0]["title"])
                    self.assertTrue(any(change["category"] == "店铺上新" for change in monitor["important_changes"]))
            finally:
                application.state.application_data_directory = previous_directory

    def test_manual_tmall_shop_link_is_cleaned_and_can_capture_baseline(self):
        with TemporaryDirectory() as directory:
            previous_directory = application.state.application_data_directory
            application.state.application_data_directory = Path(directory)
            try:
                with TestClient(application) as client:
                    client.post("/api/projects", json={"keyword": "男T恤"})
                    added = client.post(
                        "/api/monitor/shop",
                        json={"shop_url": "https://tucanofs.tmall.com/category.htm?spm=tracking-value"},
                    )
                    self.assertEqual(201, added.status_code)
                    self.assertEqual(
                        "https://tucanofs.tmall.com/category.htm",
                        added.json()["shop_url"],
                    )
                    captured = {
                        "status": "success",
                        "shop_url": "https://tucanofs.tmall.com/category.htm",
                        "shop_name": "啄木鸟官方旗舰店",
                        "raw_source_ref": str(Path(directory) / "shop.json"),
                        "captured_at": "2026-08-14T18:00:00.000001+08:00",
                        "result_count": 1,
                        "products": [{
                            "item_id": "2001", "title": "店铺商品", "product_url": "https://item.taobao.com/item.htm?id=2001",
                            "image_url": None, "price_text": "69", "payment_text": "100+人付款",
                        }],
                    }
                    with patch("app.capture_shop_listing", return_value=captured):
                        baseline = client.post(
                            f"/api/monitor/tasks/{added.json()['task_id']}/capture-shop"
                        )
                    self.assertEqual(200, baseline.status_code)
                    self.assertTrue(baseline.json()["baseline_created"])
                    self.assertEqual(1, baseline.json()["result_count"])
            finally:
                application.state.application_data_directory = previous_directory


if __name__ == "__main__":
    unittest.main()
