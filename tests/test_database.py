from contextlib import closing
import os
from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.database import (
    DATABASE_FILENAME,
    SCHEMA_MIGRATIONS,
    connect_database,
    initialize_database,
    resolve_application_data_directory,
)


class DatabaseTests(unittest.TestCase):
    def test_explicit_data_directory_override_is_used_by_source_runtime(self):
        shared_data_directory = Path("C:/Users/Test/AppData/Local/LaobingMarketIntelligence/data")
        with patch.dict(
            os.environ,
            {"TAOBAO_MARKET_DATA_DIRECTORY": str(shared_data_directory)},
        ):
            resolved_directory = resolve_application_data_directory(packaged=False)

        self.assertEqual(shared_data_directory, resolved_directory)

    def test_development_directory_is_explicit(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TAOBAO_MARKET_DATA_DIRECTORY", None)
            resolved_directory = resolve_application_data_directory(packaged=False)

        self.assertEqual(PROJECT_ROOT / ".local-data", resolved_directory)

    def test_packaged_directory_uses_local_app_data(self):
        local_app_data = Path("C:/Users/Test/AppData/Local")
        with patch.dict(os.environ, {"LOCALAPPDATA": str(local_app_data)}):
            resolved_directory = resolve_application_data_directory(packaged=True)

        self.assertEqual(
            local_app_data / "LaobingMarketIntelligence" / "data",
            resolved_directory,
        )

    def test_packaged_directory_rejects_missing_local_app_data(self):
        with self.assertRaisesRegex(ValueError, "local_app_data=''" ):
            resolve_application_data_directory(packaged=True, local_app_data="")

    def test_first_initialization_creates_database_and_version(self):
        with TemporaryDirectory() as directory_name:
            application_data_directory = Path(directory_name) / "app-data"

            database_path = initialize_database(application_data_directory)

            self.assertEqual(
                application_data_directory / DATABASE_FILENAME,
                database_path,
            )
            self.assertTrue(database_path.is_file())
            with closing(sqlite3.connect(database_path)) as connection:
                applied_versions = connection.execute(
                    "SELECT version FROM schema_versions ORDER BY version"
                ).fetchall()
                project_table = connection.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type = 'table' AND name = 'market_projects'"
                ).fetchone()
            expected_versions = [(version,) for version, _ in SCHEMA_MIGRATIONS]
            self.assertEqual(expected_versions, applied_versions)
            self.assertEqual(("market_projects",), project_table)

    def test_repeated_initialization_is_idempotent(self):
        with TemporaryDirectory() as directory_name:
            application_data_directory = Path(directory_name)

            first_database_path = initialize_database(application_data_directory)
            second_database_path = initialize_database(application_data_directory)

            self.assertEqual(first_database_path, second_database_path)
            with closing(sqlite3.connect(second_database_path)) as connection:
                version_rows = connection.execute(
                    "SELECT version FROM schema_versions"
                ).fetchall()
            expected_versions = [(version,) for version, _ in SCHEMA_MIGRATIONS]
            self.assertEqual(expected_versions, version_rows)

    def test_database_connection_enables_foreign_keys(self):
        with TemporaryDirectory() as directory_name:
            with closing(connect_database(Path(directory_name))) as connection:
                foreign_keys_enabled = connection.execute(
                    "PRAGMA foreign_keys"
                ).fetchone()[0]

            self.assertEqual(1, foreign_keys_enabled)

    def test_failed_migration_rolls_back_and_reports_version(self):
        with TemporaryDirectory() as directory_name:
            application_data_directory = Path(directory_name)
            database_path = initialize_database(application_data_directory)
            failing_version = len(SCHEMA_MIGRATIONS) + 1
            failing_migrations = SCHEMA_MIGRATIONS + (
                (
                    failing_version,
                    (
                        "CREATE TABLE should_be_rolled_back (id INTEGER PRIMARY KEY)",
                        "THIS IS NOT VALID SQL",
                    ),
                ),
            )

            with self.assertRaisesRegex(
                RuntimeError,
                f"migration_version={failing_version}",
            ):
                initialize_database(
                    application_data_directory,
                    schema_migrations=failing_migrations,
                )

            with closing(sqlite3.connect(database_path)) as connection:
                rolled_back_table = connection.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type = 'table' AND name = 'should_be_rolled_back'"
                ).fetchone()
                applied_versions = connection.execute(
                    "SELECT version FROM schema_versions ORDER BY version"
                ).fetchall()
            self.assertIsNone(rolled_back_table)
            expected_versions = [(version,) for version, _ in SCHEMA_MIGRATIONS]
            self.assertEqual(expected_versions, applied_versions)


if __name__ == "__main__":
    unittest.main()
