from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.collector import archive_and_save_search_result
from src.database import connect_database
from app import application


def search_response_bytes(product_count=35, invalid_item_index=None):
    products = []
    for product_index in range(product_count):
        item_id = str(700000000000 + product_index)
        if product_index == invalid_item_index:
            item_id = ""
        platform_host = "detail.tmall.com" if product_index % 2 == 0 else "item.taobao.com"
        products.append(
            {
                "image": f"https://img.example.com/{product_index}.jpg",
                "productUrl": f"https://{platform_host}/item.htm?id={item_id}",
                "itemId": item_id,
                "skuId": str(5100000000000 + product_index),
                "title": f"苹果15手机壳样本{product_index + 1}",
                "shopUrl": f"https://store.taobao.com/shop-{product_index}",
                "shopName": f"样本店铺{product_index + 1}",
                "price": str(8.9 + product_index),
            }
        )
    response = {
        "result": {
            "keyword": "苹果15手机壳",
            "type": "all",
            "count": product_count,
            "products": products,
        }
    }
    return json.dumps(response, ensure_ascii=False).encode("utf-8")


class SearchCaptureTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = TemporaryDirectory()
        self.application_data_directory = Path(self.temporary_directory.name) / "app-data"
        with closing(connect_database(self.application_data_directory)) as connection:
            cursor = connection.execute(
                """
                INSERT INTO market_projects (keyword, normalized_keyword)
                VALUES (?, ?)
                """,
                ("苹果15手机壳", "苹果15手机壳"),
            )
            connection.commit()
            self.project_id = cursor.lastrowid

    def tearDown(self):
        self.temporary_directory.cleanup()

    def _write_source_result(self, filename, response_bytes):
        source_path = Path(self.temporary_directory.name) / "cli-results" / filename
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_bytes(response_bytes)
        return source_path

    @staticmethod
    def _browser_product(item_id="9001"):
        return {
            "item_id": item_id,
            "sku_id": None,
            "title": "HLA海澜之家男款短袖T恤",
            "shop_name": "海澜之家男装旗舰店",
            "display_price": "68",
            "product_url": f"https://detail.tmall.com/item.htm?id={item_id}",
            "shop_url": None,
            "image_url": f"https://img.alicdn.com/{item_id}.jpg",
            "platform_type": "tmall",
            "suspected_ad": False,
            "payment_text": "7000+人付款",
            "origin_text": "江苏 无锡",
            "promotion_text": "补贴后",
            "logistics_text": "次日达 48小时内发",
            "card_text": "HLA海澜之家男款短袖T恤 ¥68 补贴后 7000+人付款 江苏 无锡 次日达",
        }

    @patch("app.run_search_products")
    @patch("app.capture_search_page")
    def test_search_api_prefers_complete_browser_capture(self, capture_page, run_search):
        capture_page.return_value = {
            "status": "success",
            "page_number": 1,
            "captured_at": "2026-08-10T14:00:00+08:00",
            "raw_source_ref": "raw/browser-page-1.json",
            "products": [self._browser_product()],
            "has_next_page": True,
        }
        previous_data_directory = application.state.application_data_directory
        application.state.application_data_directory = self.application_data_directory
        try:
            with TestClient(application) as client:
                response = client.post(
                    f"/api/projects/{self.project_id}/searches",
                    json={},
                )
        finally:
            application.state.application_data_directory = previous_data_directory

        self.assertEqual(201, response.status_code)
        payload = response.json()
        self.assertEqual("browser", payload["capture_source"])
        self.assertEqual("7000+人付款", payload["results"][0]["payment_text"])
        self.assertEqual("江苏 无锡", payload["results"][0]["origin_text"])
        self.assertEqual("补贴后", payload["results"][0]["promotion_text"])
        self.assertEqual("次日达 48小时内发", payload["results"][0]["logistics_text"])
        self.assertEqual(1, payload["captured_page_count"])
        self.assertTrue(payload["can_collect_next_page"])
        run_search.assert_not_called()

    @patch("app.run_search_products")
    @patch("app.capture_search_page")
    def test_search_api_login_gate_saves_nothing(self, capture_page, run_search):
        capture_page.return_value = {
            "status": "login_required",
            "message": "请扫码登录后重新点击开始搜索。",
        }
        previous_data_directory = application.state.application_data_directory
        application.state.application_data_directory = self.application_data_directory
        try:
            with TestClient(application) as client:
                response = client.post(
                    f"/api/projects/{self.project_id}/searches",
                    json={},
                )
        finally:
            application.state.application_data_directory = previous_data_directory

        self.assertEqual(409, response.status_code)
        self.assertEqual("taobao_browser_login_required", response.json()["detail"]["code"])
        run_search.assert_not_called()
        with closing(connect_database(self.application_data_directory)) as connection:
            self.assertEqual(0, connection.execute("SELECT COUNT(*) FROM search_snapshots").fetchone()[0])

    @patch("app.run_search_products")
    @patch("app.capture_search_page")
    def test_search_api_uses_native_fallback_after_browser_technical_failure(
        self,
        capture_page,
        run_search,
    ):
        capture_page.side_effect = RuntimeError("browser connection failed")

        def write_cli_result(keyword, request_path, result_path):
            Path(request_path).parent.mkdir(parents=True, exist_ok=True)
            Path(request_path).write_text("{}", encoding="utf-8")
            Path(result_path).write_bytes(search_response_bytes(product_count=12))

        run_search.side_effect = write_cli_result
        previous_data_directory = application.state.application_data_directory
        application.state.application_data_directory = self.application_data_directory
        try:
            with TestClient(application) as client:
                response = client.post(
                    f"/api/projects/{self.project_id}/searches",
                    json={},
                )
        finally:
            application.state.application_data_directory = previous_data_directory

        self.assertEqual(201, response.status_code)
        self.assertEqual("taobao_native_fallback", response.json()["capture_source"])
        self.assertEqual(12, response.json()["result_count"])
        run_search.assert_called_once()

    def test_saves_requested_limits_with_rank_time_and_exact_raw_bytes(self):
        response_bytes = search_response_bytes()

        for capture_index, requested_result_count in enumerate((10, 20, 30), start=1):
            with self.subTest(requested_result_count=requested_result_count):
                source_path = self._write_source_result(
                    f"source-{requested_result_count}.json",
                    response_bytes,
                )
                raw_archive_path = (
                    self.application_data_directory
                    / "raw"
                    / f"capture-{requested_result_count}.json"
                )
                captured_at = f"2026-08-06T12:00:0{capture_index}+08:00"

                saved_snapshot = archive_and_save_search_result(
                    self.application_data_directory,
                    self.project_id,
                    source_path,
                    raw_archive_path,
                    requested_result_count,
                    captured_at,
                )

                self.assertEqual(requested_result_count, saved_snapshot["result_count"])
                self.assertEqual(response_bytes, raw_archive_path.read_bytes())
                partial_files = list(
                    raw_archive_path.parent.glob(f".{raw_archive_path.name}.*.partial")
                )
                self.assertEqual([], partial_files)

                with closing(connect_database(self.application_data_directory)) as connection:
                    snapshot_row = connection.execute(
                        """
                        SELECT captured_at, requested_result_count, raw_source_ref
                        FROM search_snapshots WHERE id = ?
                        """,
                        (saved_snapshot["snapshot_id"],),
                    ).fetchone()
                    ranks = [
                        row[0]
                        for row in connection.execute(
                            """
                            SELECT display_rank FROM search_results
                            WHERE snapshot_id = ? ORDER BY display_rank
                            """,
                            (saved_snapshot["snapshot_id"],),
                        ).fetchall()
                    ]

                self.assertEqual(captured_at, snapshot_row["captured_at"])
                self.assertEqual(requested_result_count, snapshot_row["requested_result_count"])
                self.assertEqual(str(raw_archive_path), snapshot_row["raw_source_ref"])
                self.assertEqual(
                    list(range(1, requested_result_count + 1)),
                    ranks,
                )

    def test_invalid_limit_fails_before_raw_archive_is_created(self):
        source_path = self._write_source_result("source.json", search_response_bytes())
        raw_archive_path = self.application_data_directory / "raw" / "invalid-limit.json"

        with self.assertRaisesRegex(ValueError, "requested_result_count=25"):
            archive_and_save_search_result(
                self.application_data_directory,
                self.project_id,
                source_path,
                raw_archive_path,
                25,
                "2026-08-06T12:00:00+08:00",
            )

        self.assertFalse(raw_archive_path.exists())

    def test_parse_failure_keeps_raw_file_and_writes_no_database_rows(self):
        response_bytes = search_response_bytes(invalid_item_index=4)
        source_path = self._write_source_result("invalid-product.json", response_bytes)
        raw_archive_path = self.application_data_directory / "raw" / "invalid-product.json"

        with self.assertRaisesRegex(ValueError, "product_index=4.*itemId=''"):
            archive_and_save_search_result(
                self.application_data_directory,
                self.project_id,
                source_path,
                raw_archive_path,
                10,
                "2026-08-06T12:00:00+08:00",
            )

        self.assertEqual(response_bytes, raw_archive_path.read_bytes())
        with closing(connect_database(self.application_data_directory)) as connection:
            snapshot_count = connection.execute(
                "SELECT COUNT(*) FROM search_snapshots"
            ).fetchone()[0]
            product_count = connection.execute("SELECT COUNT(*) FROM products").fetchone()[0]
            result_count = connection.execute(
                "SELECT COUNT(*) FROM search_results"
            ).fetchone()[0]
        self.assertEqual((0, 0, 0), (snapshot_count, product_count, result_count))

    def test_database_failure_rolls_back_whole_batch_but_keeps_raw_file(self):
        response = json.loads(search_response_bytes(product_count=10).decode("utf-8"))
        response["result"]["products"][1]["itemId"] = response["result"]["products"][0][
            "itemId"
        ]
        response_bytes = json.dumps(response, ensure_ascii=False).encode("utf-8")
        source_path = self._write_source_result("duplicate-item.json", response_bytes)
        raw_archive_path = self.application_data_directory / "raw" / "duplicate-item.json"

        with self.assertRaisesRegex(sqlite3.IntegrityError, "UNIQUE"):
            archive_and_save_search_result(
                self.application_data_directory,
                self.project_id,
                source_path,
                raw_archive_path,
                10,
                "2026-08-06T12:00:00+08:00",
            )

        self.assertEqual(response_bytes, raw_archive_path.read_bytes())
        with closing(connect_database(self.application_data_directory)) as connection:
            snapshot_count = connection.execute(
                "SELECT COUNT(*) FROM search_snapshots"
            ).fetchone()[0]
            product_count = connection.execute("SELECT COUNT(*) FROM products").fetchone()[0]
            result_count = connection.execute(
                "SELECT COUNT(*) FROM search_results"
            ).fetchone()[0]
        self.assertEqual((0, 0, 0), (snapshot_count, product_count, result_count))

    @patch("app.run_search_products")
    @patch("app.capture_search_page")
    def test_search_api_runs_collection_and_saves_snapshot(self, capture_page, run_search):
        capture_page.side_effect = RuntimeError("browser unavailable")
        previous_data_directory = application.state.application_data_directory
        application.state.application_data_directory = self.application_data_directory

        def write_cli_result(keyword, request_path, result_path):
            self.assertEqual("苹果15手机壳", keyword)
            Path(request_path).parent.mkdir(parents=True, exist_ok=True)
            Path(request_path).write_text("{}", encoding="utf-8")
            Path(result_path).write_bytes(search_response_bytes(product_count=12))

        run_search.side_effect = write_cli_result
        try:
            with TestClient(application) as client:
                response = client.post(
                    f"/api/projects/{self.project_id}/searches",
                    json={"result_count": 10},
                )
        finally:
            application.state.application_data_directory = previous_data_directory

        self.assertEqual(201, response.status_code)
        self.assertEqual(10, response.json()["result_count"])
        self.assertEqual(list(range(1, 11)), [
            result["display_rank"] for result in response.json()["results"]
        ])
        self.assertTrue(all(
            result["completeness_percent"] == 100
            for result in response.json()["results"]
        ))
        self.assertTrue(Path(response.json()["raw_source_ref"]).is_file())
        with closing(connect_database(self.application_data_directory)) as connection:
            saved_result_count = connection.execute(
                "SELECT COUNT(*) FROM search_results WHERE snapshot_id = ?",
                (response.json()["snapshot_id"],),
            ).fetchone()[0]
        self.assertEqual(10, saved_result_count)

    @patch("app.run_search_products")
    @patch("app.capture_search_page")
    def test_search_api_without_limit_saves_every_returned_product(self, capture_page, run_search):
        capture_page.side_effect = RuntimeError("browser unavailable")
        previous_data_directory = application.state.application_data_directory
        application.state.application_data_directory = self.application_data_directory

        def write_cli_result(keyword, request_path, result_path):
            Path(request_path).parent.mkdir(parents=True, exist_ok=True)
            Path(request_path).write_text("{}", encoding="utf-8")
            Path(result_path).write_bytes(search_response_bytes(product_count=35))

        run_search.side_effect = write_cli_result
        try:
            with TestClient(application) as client:
                response = client.post(
                    f"/api/projects/{self.project_id}/searches",
                    json={},
                )
        finally:
            application.state.application_data_directory = previous_data_directory

        self.assertEqual(201, response.status_code)
        self.assertEqual(35, response.json()["result_count"])
        self.assertEqual(list(range(1, 36)), [
            result["display_rank"] for result in response.json()["results"]
        ])
        with closing(connect_database(self.application_data_directory)) as connection:
            saved_result_count = connection.execute(
                "SELECT COUNT(*) FROM search_results WHERE snapshot_id = ?",
                (response.json()["snapshot_id"],),
            ).fetchone()[0]
        self.assertEqual(35, saved_result_count)

    @patch("app.run_search_products")
    @patch("app.capture_search_page")
    def test_search_api_rejects_unknown_project_before_collection(self, capture_page, run_search):
        previous_data_directory = application.state.application_data_directory
        application.state.application_data_directory = self.application_data_directory
        try:
            with TestClient(application) as client:
                response = client.post(
                    "/api/projects/999/searches",
                    json={"result_count": 10},
                )
        finally:
            application.state.application_data_directory = previous_data_directory

        self.assertEqual(404, response.status_code)
        self.assertEqual(999, response.json()["detail"]["value"])
        capture_page.assert_not_called()
        run_search.assert_not_called()

    @patch("app.run_search_products")
    @patch("app.capture_search_page")
    def test_search_api_returns_login_prompt_when_taobao_is_logged_out(self, capture_page, run_search):
        capture_page.side_effect = RuntimeError("browser unavailable")
        run_search.side_effect = RuntimeError(
            "taobao-native search failed: exit_code=1 "
            "stdout='{\"error\":\"未登录，已打开登录页面，请先登录淘宝账号\"}' stderr=''"
        )
        previous_data_directory = application.state.application_data_directory
        application.state.application_data_directory = self.application_data_directory
        try:
            with TestClient(application) as client:
                response = client.post(
                    f"/api/projects/{self.project_id}/searches",
                    json={},
                )
        finally:
            application.state.application_data_directory = previous_data_directory

        self.assertEqual(409, response.status_code)
        self.assertEqual("taobao_login_required", response.json()["detail"]["code"])
        self.assertEqual(
            "淘宝采集尚未登录。请先在已打开的淘宝登录页面完成扫码登录，再重新搜索。",
            response.json()["detail"]["message"],
        )

    @patch("app.run_search_products")
    @patch("app.capture_search_page")
    def test_search_api_hides_internal_details_for_other_capture_failures(self, capture_page, run_search):
        capture_page.side_effect = RuntimeError("browser unavailable")
        run_search.side_effect = RuntimeError("private path and command details")
        previous_data_directory = application.state.application_data_directory
        application.state.application_data_directory = self.application_data_directory
        try:
            with TestClient(application) as client:
                response = client.post(
                    f"/api/projects/{self.project_id}/searches",
                    json={},
                )
        finally:
            application.state.application_data_directory = previous_data_directory

        self.assertEqual(502, response.status_code)
        self.assertEqual("taobao_search_failed", response.json()["detail"]["code"])
        self.assertNotIn("private path", response.text)

    def test_homepage_contains_search_controls_and_result_fields(self):
        with TestClient(application) as client:
            homepage = client.get("/")
            script = client.get("/static/app.js")

        self.assertEqual(200, homepage.status_code)
        for element_id in (
            'id="project-form"',
            'id="search-submit"',
            'id="search-message"',
            'id="capture-progress"',
            'id="result-filters"',
            'id="minimum-price"',
            'id="maximum-price"',
            'id="platform-filter"',
            'id="result-pagination"',
            'id="image-preview"',
            'id="product-results"',
        ):
            self.assertIn(element_id, homepage.text)
        self.assertIn("输入关键词，直接采集", homepage.text)
        for field_name in (
            "display_rank",
            "image_url",
            "shop_name",
            "display_price",
            "platform_type",
            "captured_at",
        ):
            self.assertIn(field_name, script.text)
        self.assertIn("canonicalProductUrl", script.text)
        self.assertIn("click.simba.taobao.com", script.text)
        self.assertIn("append", script.text)


if __name__ == "__main__":
    unittest.main()
