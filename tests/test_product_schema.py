from contextlib import closing
from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.database import (
    SCHEMA_MIGRATIONS,
    apply_schema_migrations,
    connect_database,
    list_product_snapshots,
    save_product_capture,
)


def product_detail(item_id="739189137255"):
    return {
        "page_url": f"https://detail.tmall.com/item.htm?id={item_id}",
        "product": {
            "item_id": item_id,
            "page_title": "适用苹果15手机壳透明磨砂防摔保护套",
            "main_image_url": "https://img.alicdn.com/item.jpg",
            "visible_price_text": "￥8.9起",
        },
        "shop": {
            "name": "佰蓝旗舰店",
            "rating_text": "4.7",
            "positive_rate_text": "98%",
            "shipping_text": "20小时发货",
            "refund_text": "1小时内退款",
        },
        "sales": {
            "sold_text": "已售 3000+",
            "repeat_buyer_text": "回头客141人",
            "cart_text": "超500人加购",
        },
        "reviews": {
            "count_text": "115人评价",
            "preview_text": "配合度很好，手感也不错。",
        },
        "services": ["可开发票", "免运费", "7天无理由退换"],
        "attributes": {"visible_text": "磨砂工艺 Apple/苹果适用手机机型"},
    }


def sku_capture(price_status="captured", sku_price_text="8.9"):
    return {
        "selected_options": [
            {"dimension": "适用手机型号", "value": "iPhone 15", "index": 96},
            {"dimension": "颜色分类", "value": "石墨黑", "index": 115},
        ],
        "display_price_text": "8.9起",
        "sku_price_text": sku_price_text,
        "price_status": price_status,
        "raw_price_ref": "raw/product/739189137255/sku-price.json",
    }


def product_archive():
    return {
        "product_fields": {"status": "captured", "origin_text": "广东 广州"},
        "images": [
            {
                "kind": "main",
                "sequence": 1,
                "url": "https://img.alicdn.com/main.jpg",
                "local_status": "saved",
                "local_ref": "assets/products/739189137255/main-001.jpg",
            }
        ],
        "sku_catalog": {"status": "captured", "dimensions": []},
        "reviews": {"status": "captured", "items": []},
        "questions": {"status": "not_exposed", "items": []},
        "videos": [],
        "coverage": {"basic": "captured", "questions": "not_exposed"},
        "capture_status": {"browser": "success", "local_images": "saved"},
        "raw_source_refs": {"browser": "raw/browser.json"},
    }


class ProductSchemaTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = TemporaryDirectory()
        self.application_data_directory = Path(self.temporary_directory.name)

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_migration_creates_detail_archive_tables_and_version_five(self):
        with closing(connect_database(self.application_data_directory)) as connection:
            table_names = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
            versions = [
                row[0]
                for row in connection.execute(
                    "SELECT version FROM schema_versions ORDER BY version"
                ).fetchall()
            ]

        self.assertTrue(
            {"product_snapshots", "sku_snapshots", "product_capture_archives"}
            <= table_names
        )
        self.assertEqual([version for version, _ in SCHEMA_MIGRATIONS], versions)

    def test_same_product_can_store_multiple_captures_and_read_newest_first(self):
        with closing(connect_database(self.application_data_directory)) as connection:
            first = save_product_capture(
                connection,
                product_detail(),
                "2026-08-08T09:00:00+08:00",
                "raw/product/739189137255/detail-0900.json",
                sku_capture=sku_capture(),
            )
            second = save_product_capture(
                connection,
                product_detail(),
                "2026-08-08T10:00:00+08:00",
                "raw/product/739189137255/detail-1000.json",
                sku_capture=sku_capture(
                    "missing_after_refresh",
                    None,
                ),
            )
            snapshots = list_product_snapshots(connection, "739189137255")
            product_count = connection.execute(
                "SELECT COUNT(*) FROM products WHERE item_id = ?",
                ("739189137255",),
            ).fetchone()[0]

        self.assertNotEqual(first["product_snapshot_id"], second["product_snapshot_id"])
        self.assertEqual(1, product_count)
        self.assertEqual(
            ["2026-08-08T10:00:00+08:00", "2026-08-08T09:00:00+08:00"],
            [snapshot["captured_at"] for snapshot in snapshots],
        )
        self.assertEqual("missing_after_refresh", snapshots[0]["sku"]["price_status"])
        self.assertIsNone(snapshots[0]["sku"]["sku_price_text"])
        self.assertEqual("captured", snapshots[1]["sku"]["price_status"])
        self.assertEqual("8.9", snapshots[1]["sku"]["sku_price_text"])
        self.assertEqual(
            "raw/product/739189137255/detail-0900.json",
            snapshots[1]["raw_source_ref"],
        )

    def test_product_archive_is_saved_with_the_append_only_snapshot(self):
        with closing(connect_database(self.application_data_directory)) as connection:
            saved = save_product_capture(
                connection,
                product_detail(),
                "2026-08-10T09:00:00+08:00",
                "raw/product/detail.json",
                archive=product_archive(),
            )
            snapshot = list_product_snapshots(connection, "739189137255")[0]

        self.assertIsNotNone(saved["product_archive_id"])
        self.assertEqual("广东 广州", snapshot["archive"]["product_fields"]["origin_text"])
        self.assertEqual("saved", snapshot["archive"]["images"][0]["local_status"])
        self.assertEqual("not_exposed", snapshot["archive"]["questions"]["status"])

    def test_detail_and_sku_rows_are_append_only_and_keep_foreign_keys(self):
        with closing(connect_database(self.application_data_directory)) as connection:
            saved = save_product_capture(
                connection,
                product_detail(),
                "2026-08-08T09:00:00+08:00",
                "raw/product/detail.json",
                sku_capture=sku_capture(),
            )
            with self.assertRaisesRegex(sqlite3.IntegrityError, "append-only product_snapshots"):
                connection.execute(
                    "UPDATE product_snapshots SET title = ? WHERE id = ?",
                    ("改写标题", saved["product_snapshot_id"]),
                )
            with self.assertRaisesRegex(sqlite3.IntegrityError, "append-only sku_snapshots"):
                connection.execute(
                    "UPDATE sku_snapshots SET sku_price_text = ? WHERE id = ?",
                    ("1.0", saved["sku_snapshot_id"]),
                )
            with self.assertRaisesRegex(sqlite3.IntegrityError, "FOREIGN KEY"):
                connection.execute(
                    """
                    INSERT INTO sku_snapshots (
                        product_snapshot_id, captured_at, selected_options_json,
                        price_status, raw_source_ref, parser_version
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (999, "2026-08-08T11:00:00+08:00", "[]", "missing_after_refresh", "raw/x.json", 1),
                )

    def test_invalid_capture_rolls_back_without_pseudo_success_snapshot(self):
        invalid_sku = sku_capture("captured", None)
        with closing(connect_database(self.application_data_directory)) as connection:
            with self.assertRaisesRegex(ValueError, "captured.*sku_price_text"):
                save_product_capture(
                    connection,
                    product_detail(),
                    "2026-08-08T09:00:00+08:00",
                    "raw/product/detail.json",
                    sku_capture=invalid_sku,
                )
            counts = {
                table_name: connection.execute(
                    f"SELECT COUNT(*) FROM {table_name}"
                ).fetchone()[0]
                for table_name in ("products", "product_snapshots", "sku_snapshots")
            }

        self.assertEqual(
            {"products": 0, "product_snapshots": 0, "sku_snapshots": 0},
            counts,
        )

    def test_failed_version_three_migration_leaves_no_partial_table(self):
        with closing(sqlite3.connect(":memory:")) as connection:
            apply_schema_migrations(connection, SCHEMA_MIGRATIONS[:2])
            broken_migrations = SCHEMA_MIGRATIONS[:2] + (
                (
                    3,
                    (
                        "CREATE TABLE partial_product_snapshots (id INTEGER PRIMARY KEY)",
                        "CREATE TABLE broken product syntax",
                    ),
                ),
            )

            with self.assertRaisesRegex(RuntimeError, "migration_version=3"):
                apply_schema_migrations(connection, broken_migrations)

            partial_table = connection.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type = 'table' AND name = 'partial_product_snapshots'
                """
            ).fetchone()
            versions = connection.execute(
                "SELECT version FROM schema_versions ORDER BY version"
            ).fetchall()

        self.assertIsNone(partial_table)
        self.assertEqual([(1,), (2,)], versions)


if __name__ == "__main__":
    unittest.main()
