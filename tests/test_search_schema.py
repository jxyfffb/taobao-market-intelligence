from contextlib import closing
from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.database import SCHEMA_MIGRATIONS, apply_schema_migrations, connect_database


class SearchSchemaTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = TemporaryDirectory()
        self.application_data_directory = Path(self.temporary_directory.name)

    def tearDown(self):
        self.temporary_directory.cleanup()

    def _insert_project(self, connection):
        cursor = connection.execute(
            """
            INSERT INTO market_projects (keyword, normalized_keyword)
            VALUES (?, ?)
            """,
            ("苹果15手机壳", "苹果15手机壳"),
        )
        return cursor.lastrowid

    def _insert_product(self, connection, item_id="739189137255"):
        cursor = connection.execute(
            "INSERT INTO products (item_id) VALUES (?)",
            (item_id,),
        )
        return cursor.lastrowid

    def _insert_snapshot(self, connection, project_id, captured_at="2026-08-06T12:00:00+08:00"):
        cursor = connection.execute(
            """
            INSERT INTO search_snapshots (
                project_id,
                keyword,
                search_type,
                requested_result_count,
                captured_at,
                raw_source_ref,
                parser_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                "苹果15手机壳",
                "all",
                10,
                captured_at,
                "raw/search-20260806.json",
                1,
            ),
        )
        return cursor.lastrowid

    def _insert_search_result(self, connection, snapshot_id, product_id):
        cursor = connection.execute(
            """
            INSERT INTO search_results (
                snapshot_id,
                product_id,
                display_rank,
                sku_id,
                title,
                shop_name,
                display_price,
                product_url,
                shop_url,
                image_url,
                platform_type,
                suspected_ad
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot_id,
                product_id,
                1,
                "5102288369848",
                "适用苹果15手机壳透明防摔款",
                "佰蓝旗舰店",
                "8.9",
                "https://detail.tmall.com/item.htm?id=739189137255",
                "https://store.taobao.com/example-one",
                "https://img.example.com/739189137255.jpg",
                "tmall",
                0,
            ),
        )
        return cursor.lastrowid

    def test_migration_creates_search_tables_and_version_two(self):
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
            {"market_projects", "search_snapshots", "products", "search_results"}
            <= table_names
        )
        self.assertEqual(
            [version for version, _ in SCHEMA_MIGRATIONS],
            versions,
        )

    def test_product_and_snapshot_result_unique_keys_reject_duplicates(self):
        with closing(connect_database(self.application_data_directory)) as connection:
            project_id = self._insert_project(connection)
            product_id = self._insert_product(connection)
            snapshot_id = self._insert_snapshot(connection, project_id)
            self._insert_search_result(connection, snapshot_id, product_id)

            with self.assertRaisesRegex(sqlite3.IntegrityError, "UNIQUE"):
                self._insert_product(connection)
            with self.assertRaisesRegex(sqlite3.IntegrityError, "UNIQUE"):
                self._insert_snapshot(connection, project_id)
            with self.assertRaisesRegex(sqlite3.IntegrityError, "UNIQUE"):
                connection.execute(
                    """
                    INSERT INTO search_results (
                        snapshot_id, product_id, display_rank, title,
                        product_url, platform_type
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        snapshot_id,
                        self._insert_product(connection, "812345678901"),
                        1,
                        "重复排名",
                        "https://item.taobao.com/item.htm?id=812345678901",
                        "taobao",
                    ),
                )
            with self.assertRaisesRegex(sqlite3.IntegrityError, "UNIQUE"):
                connection.execute(
                    """
                    INSERT INTO search_results (
                        snapshot_id, product_id, display_rank, title,
                        product_url, platform_type
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        snapshot_id,
                        product_id,
                        2,
                        "重复商品",
                        "https://detail.tmall.com/item.htm?id=739189137255",
                        "tmall",
                    ),
                )

    def test_foreign_keys_reject_unknown_project_snapshot_and_product(self):
        with closing(connect_database(self.application_data_directory)) as connection:
            with self.assertRaisesRegex(sqlite3.IntegrityError, "FOREIGN KEY"):
                self._insert_snapshot(connection, 999)

            project_id = self._insert_project(connection)
            snapshot_id = self._insert_snapshot(connection, project_id)
            product_id = self._insert_product(connection)
            with self.assertRaisesRegex(sqlite3.IntegrityError, "FOREIGN KEY"):
                self._insert_search_result(connection, 999, product_id)
            with self.assertRaisesRegex(sqlite3.IntegrityError, "FOREIGN KEY"):
                self._insert_search_result(connection, snapshot_id, 999)

    def test_search_rows_are_append_only(self):
        with closing(connect_database(self.application_data_directory)) as connection:
            project_id = self._insert_project(connection)
            product_id = self._insert_product(connection)
            snapshot_id = self._insert_snapshot(connection, project_id)
            result_id = self._insert_search_result(connection, snapshot_id, product_id)

            with self.assertRaisesRegex(sqlite3.IntegrityError, "append-only products"):
                connection.execute(
                    "UPDATE products SET item_id = ? WHERE id = ?",
                    ("changed-item-id", product_id),
                )
            with self.assertRaisesRegex(sqlite3.IntegrityError, "append-only search_snapshots"):
                connection.execute(
                    "UPDATE search_snapshots SET keyword = ? WHERE id = ?",
                    ("改写关键词", snapshot_id),
                )
            with self.assertRaisesRegex(sqlite3.IntegrityError, "append-only search_results"):
                connection.execute(
                    "UPDATE search_results SET display_rank = ? WHERE id = ?",
                    (2, result_id),
                )

            stored_keyword = connection.execute(
                "SELECT keyword FROM search_snapshots WHERE id = ?",
                (snapshot_id,),
            ).fetchone()[0]
            stored_rank = connection.execute(
                "SELECT display_rank FROM search_results WHERE id = ?",
                (result_id,),
            ).fetchone()[0]
            self.assertEqual("苹果15手机壳", stored_keyword)
            self.assertEqual(1, stored_rank)

    def test_failed_search_migration_leaves_no_partial_table(self):
        with closing(sqlite3.connect(":memory:")) as connection:
            apply_schema_migrations(connection, SCHEMA_MIGRATIONS[:1])
            broken_search_migrations = SCHEMA_MIGRATIONS[:1] + (
                (
                    2,
                    (
                        "CREATE TABLE partial_search_table (id INTEGER PRIMARY KEY)",
                        "CREATE TABLE broken search syntax",
                    ),
                ),
            )

            with self.assertRaisesRegex(RuntimeError, "migration_version=2"):
                apply_schema_migrations(connection, broken_search_migrations)

            partial_table = connection.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type = 'table' AND name = 'partial_search_table'
                """
            ).fetchone()
            versions = connection.execute(
                "SELECT version FROM schema_versions ORDER BY version"
            ).fetchall()

        self.assertIsNone(partial_table)
        self.assertEqual([(1,)], versions)


if __name__ == "__main__":
    unittest.main()
