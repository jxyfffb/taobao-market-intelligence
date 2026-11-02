from contextlib import closing
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import application
from src.database import (
    compare_search_snapshots,
    connect_database,
    list_search_snapshots,
    read_search_snapshot,
    save_search_snapshot,
)


def parsed_product(item_id, title, display_price, **overrides):
    product = {
        "item_id": item_id,
        "sku_id": f"sku-{item_id}",
        "title": title,
        "shop_name": "样本店铺",
        "display_price": display_price,
        "product_url": f"https://item.taobao.com/item.htm?id={item_id}",
        "shop_url": "https://store.taobao.com/sample",
        "image_url": f"https://img.example.com/{item_id}.jpg",
        "platform_type": "taobao",
        "suspected_ad": None,
    }
    product.update(overrides)
    return product


class SearchHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = TemporaryDirectory()
        self.application_data_directory = Path(self.temporary_directory.name)
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

            self.older_snapshot_id = save_search_snapshot(
                connection,
                self.project_id,
                "苹果15手机壳",
                "all",
                10,
                "2026-08-05T12:00:00+08:00",
                "raw/older.json",
                [
                    parsed_product("A", "商品 A", "10.0"),
                    parsed_product(
                        "B", "商品 B", "20.0",
                        shop_name="旧店铺",
                        image_url="https://img.example.com/B-old.jpg",
                        payment_text="100+人付款",
                        promotion_text="补贴后",
                        logistics_text="包邮",
                    ),
                    parsed_product("C", "商品 C", "30.0"),
                ],
            )
            self.newer_snapshot_id = save_search_snapshot(
                connection,
                self.project_id,
                "苹果15手机壳",
                "all",
                10,
                "2026-08-06T12:00:00+08:00",
                "raw/newer.json",
                [
                    parsed_product(
                        "B", "商品 B", "22.0",
                        shop_name="新店铺",
                        image_url="https://img.example.com/B-new.jpg",
                        payment_text="200+人付款",
                        promotion_text="官方立减10%",
                        logistics_text="次日达",
                    ),
                    parsed_product("A", "商品 A", "10.0"),
                    parsed_product("D", "商品 D", "40.0"),
                ],
            )

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_lists_all_snapshots_newest_first_and_reopens_results(self):
        with closing(connect_database(self.application_data_directory)) as connection:
            snapshots = list_search_snapshots(connection, self.project_id)
            reopened_snapshot = read_search_snapshot(
                connection,
                self.older_snapshot_id,
            )

        self.assertEqual(
            [self.newer_snapshot_id, self.older_snapshot_id],
            [snapshot["snapshot_id"] for snapshot in snapshots],
        )
        self.assertEqual([3, 3], [snapshot["result_count"] for snapshot in snapshots])
        self.assertEqual(
            ["A", "B", "C"],
            [result["item_id"] for result in reopened_snapshot["results"]],
        )
        self.assertEqual([1, 2, 3], [
            result["display_rank"] for result in reopened_snapshot["results"]
        ])

    def test_diff_reports_added_removed_rank_and_price_changes_without_mutation(self):
        with closing(connect_database(self.application_data_directory)) as connection:
            before_rows = connection.execute(
                """
                SELECT snapshot_id, product_id, display_rank, display_price
                FROM search_results ORDER BY snapshot_id, display_rank
                """
            ).fetchall()

            comparison = compare_search_snapshots(
                connection,
                self.project_id,
                self.older_snapshot_id,
                self.newer_snapshot_id,
            )

            after_rows = connection.execute(
                """
                SELECT snapshot_id, product_id, display_rank, display_price
                FROM search_results ORDER BY snapshot_id, display_rank
                """
            ).fetchall()

        self.assertEqual(["D"], [entry["item_id"] for entry in comparison["added"]])
        self.assertEqual(["C"], [entry["item_id"] for entry in comparison["removed"]])
        self.assertEqual(
            {"A": (1, 2), "B": (2, 1)},
            {
                entry["item_id"]: (entry["old_rank"], entry["new_rank"])
                for entry in comparison["rank_changes"]
            },
        )
        self.assertEqual(
            {"B": ("20.0", "22.0")},
            {
                entry["item_id"]: (entry["old_price"], entry["new_price"])
                for entry in comparison["price_changes"]
            },
        )
        for change_name in (
            "payment_changes",
            "promotion_changes",
            "logistics_changes",
            "shop_changes",
            "image_changes",
        ):
            self.assertEqual(["B"], [entry["item_id"] for entry in comparison[change_name]])
        self.assertEqual(before_rows, after_rows)

    def test_snapshot_must_belong_to_requested_project(self):
        with closing(connect_database(self.application_data_directory)) as connection:
            cursor = connection.execute(
                """
                INSERT INTO market_projects (keyword, normalized_keyword)
                VALUES (?, ?)
                """,
                ("手机支架", "手机支架"),
            )
            connection.commit()
            other_project_id = cursor.lastrowid

            with self.assertRaisesRegex(LookupError, f"project_id={other_project_id}"):
                compare_search_snapshots(
                    connection,
                    other_project_id,
                    self.older_snapshot_id,
                    self.newer_snapshot_id,
                )

    def test_history_and_diff_api_return_saved_snapshots(self):
        previous_data_directory = application.state.application_data_directory
        application.state.application_data_directory = self.application_data_directory
        try:
            with TestClient(application) as client:
                history_response = client.get(
                    f"/api/projects/{self.project_id}/searches"
                )
                snapshot_response = client.get(
                    f"/api/projects/{self.project_id}/searches/{self.older_snapshot_id}"
                )
                diff_response = client.get(
                    f"/api/projects/{self.project_id}/search-diff",
                    params={
                        "older_snapshot_id": self.older_snapshot_id,
                        "newer_snapshot_id": self.newer_snapshot_id,
                    },
                )
        finally:
            application.state.application_data_directory = previous_data_directory

        self.assertEqual(200, history_response.status_code)
        self.assertEqual(2, len(history_response.json()["snapshots"]))
        self.assertEqual(200, snapshot_response.status_code)
        self.assertEqual(3, snapshot_response.json()["result_count"])
        self.assertEqual(
            {
                "valid_count": 3,
                "missing_or_invalid_count": 0,
                "minimum": 10.0,
                "median": 20.0,
                "maximum": 30.0,
            },
            snapshot_response.json()["price_distribution"]["price"],
        )
        self.assertEqual(200, diff_response.status_code)
        self.assertEqual("D", diff_response.json()["added"][0]["item_id"])

    def test_snapshot_api_restores_original_buyer_url_from_raw_capture(self):
        raw_path = self.application_data_directory / "raw" / "buyer-link.json"
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        buyer_url = (
            "https://click.simba.taobao.com/cc_im?"
            "id=9001&skuId=8801&spm=a21n57.1.item.1"
        )
        raw_path.write_text(
            json.dumps(
                {
                    "products": [
                        {
                            "itemId": "9001",
                            "skuId": "8801",
                            "productUrl": buyer_url,
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        with closing(connect_database(self.application_data_directory)) as connection:
            snapshot_id = save_search_snapshot(
                connection,
                self.project_id,
                "苹果15手机壳",
                "all",
                10,
                "2026-08-07T12:00:00+08:00",
                str(raw_path),
                [parsed_product("9001", "商品 9001", "99.0")],
            )

        previous_data_directory = application.state.application_data_directory
        application.state.application_data_directory = self.application_data_directory
        try:
            with TestClient(application) as client:
                response = client.get(
                    f"/api/projects/{self.project_id}/searches/{snapshot_id}"
                )
        finally:
            application.state.application_data_directory = previous_data_directory

        self.assertEqual(200, response.status_code)
        self.assertEqual(buyer_url, response.json()["results"][0].get("buyer_url"))

    def test_homepage_contains_history_reopen_and_diff_controls(self):
        with TestClient(application) as client:
            homepage = client.get("/")
            script = client.get("/static/app.js")

        for element_id in (
            'id="history-list"',
            'id="older-snapshot"',
            'id="newer-snapshot"',
            'id="compare-snapshots"',
            'id="diff-results"',
        ):
            self.assertIn(element_id, homepage.text)
        self.assertIn("search-diff", script.text)
        self.assertIn("rank_changes", script.text)
        self.assertIn("price_changes", script.text)


if __name__ == "__main__":
    unittest.main()
