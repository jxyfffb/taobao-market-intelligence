from contextlib import closing
import json
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
from src.browser_search_collector import (
    build_taobao_search_url,
    capture_search_page,
    normalize_browser_search_capture,
)
from src.database import (
    append_search_snapshot_page,
    connect_database,
    read_search_snapshot,
    save_search_snapshot,
)


def product(item_id, index=1):
    host = "detail.tmall.com" if index % 2 else "item.taobao.com"
    return {
        "item_id": str(item_id),
        "sku_id": None,
        "title": f"翻页商品{index}",
        "shop_name": f"翻页店铺{index}",
        "display_price": str(20 + index),
        "product_url": f"https://{host}/item.htm?id={item_id}",
        "shop_url": None,
        "image_url": f"https://img.alicdn.com/{item_id}.jpg",
        "platform_type": "tmall" if index % 2 else "taobao",
        "suspected_ad": None,
    }


class BrowserSearchCollectorTests(unittest.TestCase):
    def test_builds_real_page_url_without_credentials(self):
        url = build_taobao_search_url("男 T恤", 3)

        self.assertIn("https://s.taobao.com/search?", url)
        self.assertIn("q=%E7%94%B7+T%E6%81%A4", url)
        self.assertIn("s=96", url)
        self.assertNotIn("cookie", url.casefold())
        self.assertNotIn("token", url.casefold())

    def test_normalizes_login_state_without_exposing_internal_url(self):
        result = normalize_browser_search_capture(
            {
                "url": "https://login.taobao.com/member/login.jhtml?token=secret",
                "title": "登录",
                "needsLogin": True,
                "products": [],
            },
            expected_keyword="男T恤",
            expected_page_number=2,
        )

        self.assertEqual("login_required", result["status"])
        self.assertEqual("请在弹出的采集浏览器中完成淘宝扫码登录，然后再次点击采集下一页。", result["message"])
        self.assertNotIn("secret", json.dumps(result, ensure_ascii=False))

    def test_first_page_login_message_points_back_to_search(self):
        result = normalize_browser_search_capture(
            {
                "url": "https://login.taobao.com/member/login.jhtml",
                "title": "登录",
                "needsLogin": True,
                "products": [],
            },
            expected_keyword="男T恤",
            expected_page_number=1,
        )

        self.assertEqual("login_required", result["status"])
        self.assertIn("重新点击开始搜索", result["message"])

    def test_identity_verification_page_is_blocked_not_empty(self):
        result = normalize_browser_search_capture(
            {
                "url": "https://passport.taobao.com/iv/identity_verify.htm?token=secret",
                "title": "阿里巴巴集团 | 身份验证",
                "products": [],
            },
            expected_keyword="男T恤",
            expected_page_number=1,
        )

        self.assertEqual("blocked", result["status"])
        self.assertNotIn("secret", json.dumps(result, ensure_ascii=False))

    def test_normalizes_products_and_deduplicates_item_ids(self):
        result = normalize_browser_search_capture(
            {
                "url": "https://s.taobao.com/search?q=%E7%94%B7T%E6%81%A4&s=48",
                "title": "淘宝搜索",
                "needsLogin": False,
                "hasNextPage": True,
                "products": [
                    {
                        "itemId": "9001",
                        "title": "男士短袖T恤",
                        "shopName": "样本店",
                        "shopUrl": "https://store.taobao.com/shop-9001",
                        "price": "39.90",
                        "productUrl": "https://item.taobao.com/item.htm?id=9001&spm=test",
                        "image": "https://img.alicdn.com/9001.jpg_.webp",
                    },
                    {
                        "itemId": "9001",
                        "title": "重复商品",
                        "productUrl": "https://item.taobao.com/item.htm?id=9001",
                    },
                    {
                        "itemId": "9002",
                        "title": "天猫男装",
                        "productUrl": "https://detail.tmall.com/item.htm?id=9002",
                    },
                ],
            },
            expected_keyword="男T恤",
            expected_page_number=2,
        )

        self.assertEqual("success", result["status"])
        self.assertEqual(["9001", "9002"], [item["item_id"] for item in result["products"]])
        self.assertEqual("https://item.taobao.com/item.htm?id=9001", result["products"][0]["product_url"])
        self.assertEqual("https://img.alicdn.com/9001.jpg", result["products"][0]["image_url"])
        self.assertEqual(
            "https://store.taobao.com/shop-9001",
            result["products"][0]["shop_url"],
        )
        self.assertTrue(result["has_next_page"])

    @patch("src.browser_search_collector.time.sleep")
    @patch("src.browser_search_collector._navigate_target")
    @patch("src.browser_search_collector._visible_search_item_ids")
    @patch("src.browser_search_collector._target_for_search_browser")
    @patch("src.browser_search_collector._cdp_ready")
    @patch("src.browser_search_collector._cdp_evaluate")
    def test_waits_for_cards_to_change_before_accepting_next_page(
        self,
        evaluate,
        cdp_ready,
        target_for_search,
        visible_item_ids,
        navigate,
        sleep,
    ):
        target = {
            "id": "search-page",
            "url": "https://s.taobao.com/search?q=%E7%94%B7T%E6%81%A4",
        }
        stale_payload = {
            "url": "https://s.taobao.com/search?q=%E7%94%B7T%E6%81%A4&s=48",
            "title": "淘宝搜索",
            "currentPage": 2,
            "hasNextPage": True,
            "products": [
                {
                    "itemId": "9001",
                    "title": "第一页商品",
                    "productUrl": "https://item.taobao.com/item.htm?id=9001",
                }
            ],
        }
        fresh_payload = {
            **stale_payload,
            "products": [
                {
                    "itemId": "9002",
                    "title": "第二页商品",
                    "productUrl": "https://item.taobao.com/item.htm?id=9002",
                }
            ],
        }
        evaluate.side_effect = [stale_payload, fresh_payload]
        cdp_ready.return_value = True
        target_for_search.return_value = target
        visible_item_ids.return_value = {"9001"}

        with TemporaryDirectory() as temp_directory:
            raw_path = Path(temp_directory) / "page-2.json"
            result = capture_search_page(temp_directory, "男T恤", 2, raw_path)

        self.assertEqual("success", result["status"])
        self.assertEqual(["9002"], [item["item_id"] for item in result["products"]])
        self.assertEqual(2, evaluate.call_count)
        navigate.assert_called_once_with(target, build_taobao_search_url("男T恤", 2))

    @patch("src.browser_search_collector.time.sleep")
    @patch("src.browser_search_collector._navigate_target")
    @patch("src.browser_search_collector._visible_search_item_ids")
    @patch("src.browser_search_collector._target_for_search_browser")
    @patch("src.browser_search_collector._cdp_ready")
    @patch("src.browser_search_collector._cdp_evaluate")
    def test_rejects_stale_next_page_dom_without_saving(
        self,
        evaluate,
        cdp_ready,
        target_for_search,
        visible_item_ids,
        navigate,
        sleep,
    ):
        target = {
            "id": "search-page",
            "url": "https://s.taobao.com/search?q=%E7%94%B7T%E6%81%A4",
        }
        stale_payload = {
            "url": "https://s.taobao.com/search?q=%E7%94%B7T%E6%81%A4&s=48",
            "title": "淘宝搜索",
            "currentPage": 2,
            "hasNextPage": True,
            "products": [
                {
                    "itemId": "9001",
                    "title": "仍是第一页商品",
                    "productUrl": "https://item.taobao.com/item.htm?id=9001",
                }
            ],
        }
        evaluate.return_value = stale_payload
        cdp_ready.return_value = True
        target_for_search.return_value = target
        visible_item_ids.return_value = {"9001"}

        with TemporaryDirectory() as temp_directory:
            raw_path = Path(temp_directory) / "page-2.json"
            result = capture_search_page(temp_directory, "男T恤", 2, raw_path)
            self.assertFalse(raw_path.exists())

        self.assertEqual("failed", result["status"])
        self.assertIn("仍与上一页相同", result["message"])
        navigate.assert_called_once_with(target, build_taobao_search_url("男T恤", 2))


class NextPageDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = TemporaryDirectory()
        self.data_directory = Path(self.temporary_directory.name) / "data"
        with closing(connect_database(self.data_directory)) as connection:
            cursor = connection.execute(
                "INSERT INTO market_projects (keyword, normalized_keyword) VALUES (?, ?)",
                ("男T恤", "男t恤"),
            )
            connection.commit()
            self.project_id = cursor.lastrowid
            self.snapshot_id = save_search_snapshot(
                connection,
                self.project_id,
                "男T恤",
                "all",
                30,
                "2026-08-09T14:00:00+08:00",
                "raw/page-1.json",
                [product("8001", 1), product("8002", 2)],
            )

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_initial_snapshot_is_one_collectible_page(self):
        with closing(connect_database(self.data_directory)) as connection:
            snapshot = read_search_snapshot(connection, self.snapshot_id, self.project_id)

        self.assertEqual(1, snapshot["captured_page_count"])
        self.assertEqual(2, snapshot["next_page_number"])
        self.assertTrue(snapshot["can_collect_next_page"])

    def test_appends_unique_products_to_same_snapshot(self):
        with closing(connect_database(self.data_directory)) as connection:
            appended = append_search_snapshot_page(
                connection,
                self.project_id,
                self.snapshot_id,
                2,
                "2026-08-09T14:05:00+08:00",
                "raw/page-2.json",
                [product("8002", 2), product("8003", 3), product("8004", 4)],
                has_next_page=True,
            )
            snapshot = read_search_snapshot(connection, self.snapshot_id, self.project_id)

        self.assertEqual(2, appended["added_result_count"])
        self.assertEqual(3, appended["read_result_count"])
        self.assertEqual(1, appended["duplicate_result_count"])
        self.assertEqual(4, snapshot["result_count"])
        self.assertEqual(2, snapshot["captured_page_count"])
        self.assertEqual([1, 2, 3, 4], [item["display_rank"] for item in snapshot["results"]])
        self.assertEqual(["8001", "8002", "8003", "8004"], [item["item_id"] for item in snapshot["results"]])

    def test_preserves_structured_market_card_fields_on_appended_pages(self):
        enriched = {
            **product("8003", 3),
            "payment_text": "7000+人付款",
            "origin_text": "江苏 无锡",
            "promotion_text": "补贴后",
            "logistics_text": "次日达",
            "card_text": "男士短袖 ¥68 补贴后 7000+人付款 江苏 无锡 次日达",
        }
        with closing(connect_database(self.data_directory)) as connection:
            append_search_snapshot_page(
                connection,
                self.project_id,
                self.snapshot_id,
                2,
                "2026-08-09T14:05:00+08:00",
                "raw/page-2.json",
                [enriched],
                has_next_page=True,
            )
            snapshot = read_search_snapshot(connection, self.snapshot_id, self.project_id)

        result = next(item for item in snapshot["results"] if item["item_id"] == "8003")
        self.assertEqual("7000+人付款", result["payment_text"])
        self.assertEqual("江苏 无锡", result["origin_text"])
        self.assertEqual("补贴后", result["promotion_text"])
        self.assertEqual("次日达", result["logistics_text"])

    def test_rejects_repeating_the_same_page_without_partial_writes(self):
        with closing(connect_database(self.data_directory)) as connection:
            append_search_snapshot_page(
                connection,
                self.project_id,
                self.snapshot_id,
                2,
                "2026-08-09T14:05:00+08:00",
                "raw/page-2.json",
                [product("8003", 3)],
                has_next_page=True,
            )
            with self.assertRaisesRegex(ValueError, "next page must be 3"):
                append_search_snapshot_page(
                    connection,
                    self.project_id,
                    self.snapshot_id,
                    2,
                    "2026-08-09T14:06:00+08:00",
                    "raw/page-2-repeat.json",
                    [product("8004", 4)],
                    has_next_page=True,
                )
            snapshot = read_search_snapshot(connection, self.snapshot_id, self.project_id)

        self.assertEqual(3, snapshot["result_count"])


class NextPageApiAndUiTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = TemporaryDirectory()
        self.data_directory = Path(self.temporary_directory.name) / "data"
        with closing(connect_database(self.data_directory)) as connection:
            cursor = connection.execute(
                "INSERT INTO market_projects (keyword, normalized_keyword) VALUES (?, ?)",
                ("男T恤", "男t恤"),
            )
            connection.commit()
            self.project_id = cursor.lastrowid
            self.snapshot_id = save_search_snapshot(
                connection,
                self.project_id,
                "男T恤",
                "all",
                30,
                "2026-08-09T14:00:00+08:00",
                "raw/page-1.json",
                [product("8001", 1)],
            )
        self.previous_data_directory = application.state.application_data_directory
        application.state.application_data_directory = self.data_directory

    def tearDown(self):
        application.state.application_data_directory = self.previous_data_directory
        self.temporary_directory.cleanup()

    @patch("app.capture_next_search_page")
    def test_login_required_keeps_existing_snapshot_unchanged(self, capture_next):
        capture_next.return_value = {
            "status": "login_required",
            "message": "请在弹出的采集浏览器中完成淘宝扫码登录，然后再次点击采集下一页。",
        }
        with TestClient(application) as client:
            response = client.post(
                f"/api/projects/{self.project_id}/searches/{self.snapshot_id}/next-page"
            )

        self.assertEqual(200, response.status_code)
        self.assertEqual("login_required", response.json()["status"])
        with closing(connect_database(self.data_directory)) as connection:
            snapshot = read_search_snapshot(connection, self.snapshot_id, self.project_id)
        self.assertEqual(1, snapshot["result_count"])
        self.assertEqual(1, snapshot["captured_page_count"])

    @patch("app.capture_next_search_page")
    def test_successful_api_capture_appends_and_returns_full_snapshot(self, capture_next):
        capture_next.return_value = {
            "status": "success",
            "page_number": 2,
            "captured_at": "2026-08-09T14:05:00+08:00",
            "raw_source_ref": "raw/page-2.json",
            "products": [product("8001", 1), product("8002", 2)],
            "has_next_page": True,
        }
        with TestClient(application) as client:
            response = client.post(
                f"/api/projects/{self.project_id}/searches/{self.snapshot_id}/next-page"
            )

        self.assertEqual(200, response.status_code)
        self.assertEqual("success", response.json()["status"])
        self.assertEqual(2, response.json()["snapshot"]["result_count"])
        self.assertEqual(2, response.json()["snapshot"]["captured_page_count"])
        self.assertEqual(1, response.json()["added_result_count"])
        self.assertEqual(2, response.json()["read_result_count"])
        self.assertEqual(1, response.json()["duplicate_result_count"])

    def test_page_contains_compact_next_page_control(self):
        with TestClient(application) as client:
            homepage = client.get("/")
            script = client.get("/static/app.js")

        self.assertIn('id="capture-next-page"', homepage.text)
        self.assertIn('id="capture-page-summary"', homepage.text)
        self.assertIn("采集下一页", homepage.text)
        self.assertIn("/next-page", script.text)
        self.assertIn("login_required", script.text)
        self.assertIn("result.message", script.text)


if __name__ == "__main__":
    unittest.main()
