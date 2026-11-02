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
    SCHEMA_MIGRATIONS,
    apply_schema_migrations,
    connect_database,
    delete_competitor_record,
    get_competitor_record,
    list_competitor_records,
    initialize_database,
    save_product_capture,
    save_search_snapshot,
    upsert_competitor_record,
)


def product_detail(item_id="739189137255", title="男士纯棉短袖", price="68"):
    return {
        "page_url": f"https://item.taobao.com/item.htm?id={item_id}",
        "product": {
            "item_id": item_id,
            "page_title": title,
            "main_image_url": "https://img.alicdn.com/main.jpg",
            "visible_price_text": price,
        },
        "shop": {
            "name": "品牌旗舰店",
            "rating_text": None,
            "positive_rate_text": None,
            "shipping_text": None,
            "refund_text": None,
        },
        "sales": {"sold_text": "7000+人付款", "repeat_buyer_text": None, "cart_text": None},
        "reviews": {"count_text": "200条评价", "preview_text": "面料舒服"},
        "services": [],
        "attributes": {"visible_text": "材质 纯棉"},
    }


class CompetitorRecordTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = TemporaryDirectory()
        self.data_directory = Path(self.temporary_directory.name)
        application.state.application_data_directory = self.data_directory

    def tearDown(self):
        application.state.application_data_directory = None
        self.temporary_directory.cleanup()

    def _seed_record(self, item_id="739189137255", captured_at="2026-08-15T09:00:00+08:00"):
        with closing(connect_database(self.data_directory)) as connection:
            saved = save_product_capture(
                connection,
                product_detail(item_id),
                captured_at,
                f"raw/products/{item_id}/detail.json",
            )
            record = upsert_competitor_record(
                connection,
                item_id=item_id,
                source_url=f"https://e.tb.cn/h.{item_id}",
                resolved_url=f"https://item.taobao.com/item.htm?id={item_id}",
                captured_at=captured_at,
            )
        return saved, record

    def test_record_is_unique_per_item_and_lists_latest_snapshot(self):
        first_saved, first_record = self._seed_record()
        with closing(connect_database(self.data_directory)) as connection:
            second_saved = save_product_capture(
                connection,
                product_detail(title="男士纯棉短袖升级款"),
                "2026-08-15T10:00:00+08:00",
                "raw/products/739189137255/detail-2.json",
            )
            second_record = upsert_competitor_record(
                connection,
                item_id="739189137255",
                source_url="https://item.taobao.com/item.htm?id=739189137255",
                resolved_url="https://item.taobao.com/item.htm?id=739189137255",
                captured_at="2026-08-15T10:00:00+08:00",
            )
            records = list_competitor_records(connection)

        self.assertEqual(first_record["id"], second_record["id"])
        self.assertNotEqual(first_saved["product_snapshot_id"], second_saved["product_snapshot_id"])
        self.assertEqual(1, len(records))
        self.assertEqual(2, records[0]["snapshot_count"])
        self.assertEqual("男士纯棉短袖升级款", records[0]["title"])
        self.assertEqual("2026-08-15T10:00:00+08:00", records[0]["last_captured_at"])

    def test_upgrade_backfills_previously_captured_products_into_history(self):
        with TemporaryDirectory() as directory:
            database_path = initialize_database(
                directory,
                schema_migrations=SCHEMA_MIGRATIONS[:13],
            )
            import sqlite3

            connection = sqlite3.connect(database_path)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            try:
                save_product_capture(
                    connection,
                    product_detail(),
                    "2026-08-14T09:00:00+08:00",
                    "raw/products/739189137255/legacy.json",
                )
                apply_schema_migrations(connection, SCHEMA_MIGRATIONS)
                records = list_competitor_records(connection)
            finally:
                connection.close()

        self.assertEqual(1, len(records))
        self.assertEqual("739189137255", records[0]["item_id"])
        self.assertEqual(1, records[0]["snapshot_count"])

    def test_delete_removes_registry_but_preserves_shared_snapshots(self):
        _, record = self._seed_record()
        with closing(connect_database(self.data_directory)) as connection:
            deleted = delete_competitor_record(connection, "739189137255")
            remaining_record = get_competitor_record(connection, "739189137255")
            snapshot_count = connection.execute(
                "SELECT COUNT(*) FROM product_snapshots"
            ).fetchone()[0]

        self.assertTrue(deleted)
        self.assertIsNone(remaining_record)
        self.assertEqual(1, snapshot_count)

    def test_independent_list_detail_and_delete_api_need_no_market_project(self):
        self._seed_record()
        with TestClient(application) as client:
            listed = client.get("/api/competitors")
            detailed = client.get("/api/competitors/739189137255")
            deleted = client.delete("/api/competitors/739189137255")
            missing = client.get("/api/competitors/739189137255")

        self.assertEqual(200, listed.status_code)
        self.assertEqual("739189137255", listed.json()["records"][0]["item_id"])
        self.assertEqual(200, detailed.status_code)
        self.assertEqual("男士纯棉短袖", detailed.json()["snapshot"]["title"])
        self.assertEqual(200, deleted.status_code)
        self.assertEqual(404, missing.status_code)

    def test_detail_api_returns_page_and_target_sku_price_histories(self):
        item_id = "739189137255"
        outbound_url = (
            "https://item.taobao.com/item.htm?id=739189137255&skuId=9988"
        )
        selected_options = [
            {"dimension": "颜色", "value": "白色", "index": 0},
            {"dimension": "尺码", "value": "L", "index": 1},
        ]
        with closing(connect_database(self.data_directory)) as connection:
            save_product_capture(
                connection,
                product_detail(item_id, price="68.00"),
                "2026-08-14T09:00:00+08:00",
                f"raw/products/{item_id}/detail-1.json",
                sku_capture={
                    "selected_options": selected_options,
                    "display_price_text": "68.00",
                    "sku_price_text": "69.00",
                    "price_status": "captured",
                    "raw_price_ref": f"raw/products/{item_id}/sku-1.json",
                },
            )
            save_product_capture(
                connection,
                product_detail(item_id, price="59.50"),
                "2026-08-15T09:00:00+08:00",
                f"raw/products/{item_id}/detail-2.json",
                sku_capture={
                    "selected_options": selected_options,
                    "display_price_text": "59.50",
                    "sku_price_text": "60.00",
                    "price_status": "captured",
                    "raw_price_ref": f"raw/products/{item_id}/sku-2.json",
                },
            )
            upsert_competitor_record(
                connection,
                item_id=item_id,
                source_url=outbound_url,
                resolved_url=outbound_url,
                captured_at="2026-08-15T09:00:00+08:00",
            )

        with TestClient(application) as client:
            response = client.get(f"/api/competitors/{item_id}")

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual(outbound_url, payload["outbound_url"])
        page_history = payload["history"]["page_price"]
        self.assertEqual([68.0, 59.5], [point["price_value"] for point in page_history["points"]])
        self.assertEqual(59.5, page_history["summary"]["current"])
        self.assertEqual(68.0, page_history["summary"]["previous"])
        self.assertEqual(-8.5, page_history["summary"]["change"])
        self.assertEqual(59.5, page_history["summary"]["minimum"])
        self.assertEqual(68.0, page_history["summary"]["maximum"])
        sku_history = payload["history"]["sku_prices"][0]
        self.assertEqual("颜色：白色 / 尺码：L", sku_history["label"])
        self.assertEqual([69.0, 60.0], [point["price_value"] for point in sku_history["points"]])
        self.assertEqual(60.0, sku_history["summary"]["current"])

    def test_competitor_apis_restore_buyer_url_from_saved_search_capture(self):
        item_id = "739189137255"
        self._seed_record(item_id)
        raw_path = self.data_directory / "raw" / "search-buyer-link.json"
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        buyer_url = (
            "https://detail.tmall.com/item.htm?"
            f"id={item_id}&skuId=9988&spm=a21n57.1.item.7"
        )
        raw_path.write_text(
            json.dumps(
                {
                    "products": [
                        {
                            "itemId": item_id,
                            "skuId": "9988",
                            "productUrl": buyer_url,
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        with closing(connect_database(self.data_directory)) as connection:
            cursor = connection.execute(
                "INSERT INTO market_projects (keyword, normalized_keyword) VALUES (?, ?)",
                ("男士短袖", "男士短袖"),
            )
            connection.commit()
            save_search_snapshot(
                connection,
                cursor.lastrowid,
                "男士短袖",
                "all",
                10,
                "2026-08-15T08:00:00+08:00",
                str(raw_path),
                [
                    {
                        "item_id": item_id,
                        "sku_id": "9988",
                        "title": "男士纯棉短袖",
                        "shop_name": "品牌旗舰店",
                        "display_price": "68",
                        "product_url": f"https://item.taobao.com/item.htm?id={item_id}",
                        "shop_url": "https://store.taobao.com/sample",
                        "image_url": "https://img.example.com/main.jpg",
                        "platform_type": "taobao",
                        "suspected_ad": None,
                    }
                ],
            )

        with TestClient(application) as client:
            listed = client.get("/api/competitors")
            detailed = client.get(f"/api/competitors/{item_id}")

        self.assertEqual(buyer_url, listed.json()["records"][0].get("buyer_url"))
        self.assertEqual(buyer_url, detailed.json()["outbound_url"])

    def test_independent_record_can_join_monitor_and_delete_removes_its_task(self):
        self._seed_record()
        with TestClient(application) as client:
            added = client.post("/api/competitors/739189137255/monitor")
            monitor_before = client.get("/api/monitor").json()
            deleted = client.delete("/api/competitors/739189137255")
            monitor_after = client.get("/api/monitor").json()

        self.assertEqual(201, added.status_code)
        self.assertEqual(1, len(monitor_before["tasks"]))
        self.assertIsNone(monitor_before["tasks"][0]["project_id"])
        self.assertEqual("competitor", monitor_before["tasks"][0]["task_type"])
        self.assertEqual(200, deleted.status_code)
        self.assertEqual([], monitor_after["tasks"])


if __name__ == "__main__":
    unittest.main()
