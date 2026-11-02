import json
import os
from pathlib import Path
import sqlite3
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEVELOPMENT_DATA_DIRECTORY = PROJECT_ROOT / ".local-data"
PACKAGED_DIRECTORY_NAME = "LaobingMarketIntelligence"
APPLICATION_DATA_DIRECTORY_ENV = "TAOBAO_MARKET_DATA_DIRECTORY"
DATABASE_FILENAME = "market-intelligence.sqlite3"
SEARCH_COMPLETENESS_FIELDS = (
    "item_id",
    "sku_id",
    "title",
    "shop_name",
    "display_price",
    "product_url",
    "shop_url",
    "image_url",
)

SCHEMA_MIGRATIONS = (
    (
        1,
        (
            """
            CREATE TABLE schema_versions (
                version INTEGER PRIMARY KEY CHECK (version > 0),
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE market_projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                keyword TEXT NOT NULL,
                normalized_keyword TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
        ),
    ),
    (
        2,
        (
            """
            CREATE TABLE products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id TEXT NOT NULL UNIQUE CHECK (length(trim(item_id)) > 0),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE search_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                keyword TEXT NOT NULL CHECK (length(trim(keyword)) > 0),
                search_type TEXT NOT NULL CHECK (search_type IN ('all', 'taobao', 'tmall')),
                requested_result_count INTEGER NOT NULL
                    CHECK (requested_result_count IN (10, 20, 30)),
                captured_at TEXT NOT NULL CHECK (length(trim(captured_at)) > 0),
                raw_source_ref TEXT NOT NULL CHECK (length(trim(raw_source_ref)) > 0),
                parser_version INTEGER NOT NULL CHECK (parser_version > 0),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES market_projects(id) ON DELETE CASCADE,
                UNIQUE (project_id, captured_at)
            )
            """,
            """
            CREATE TABLE search_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                display_rank INTEGER NOT NULL CHECK (display_rank > 0),
                sku_id TEXT,
                title TEXT,
                shop_name TEXT,
                display_price TEXT,
                product_url TEXT,
                shop_url TEXT,
                image_url TEXT,
                platform_type TEXT NOT NULL
                    CHECK (platform_type IN ('taobao', 'tmall', 'unknown')),
                suspected_ad INTEGER CHECK (suspected_ad IN (0, 1) OR suspected_ad IS NULL),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (snapshot_id) REFERENCES search_snapshots(id) ON DELETE CASCADE,
                FOREIGN KEY (product_id) REFERENCES products(id),
                UNIQUE (snapshot_id, display_rank),
                UNIQUE (snapshot_id, product_id)
            )
            """,
            """
            CREATE TRIGGER prevent_products_update
            BEFORE UPDATE ON products
            BEGIN
                SELECT RAISE(ABORT, 'append-only products');
            END
            """,
            """
            CREATE TRIGGER prevent_search_snapshots_update
            BEFORE UPDATE ON search_snapshots
            BEGIN
                SELECT RAISE(ABORT, 'append-only search_snapshots');
            END
            """,
            """
            CREATE TRIGGER prevent_search_results_update
            BEFORE UPDATE ON search_results
            BEGIN
                SELECT RAISE(ABORT, 'append-only search_results');
            END
            """,
            """
            CREATE INDEX search_snapshots_project_captured_at
            ON search_snapshots (project_id, captured_at DESC)
            """,
            """
            CREATE INDEX search_results_product_id
            ON search_results (product_id)
            """,
        ),
    ),
    (
        3,
        (
            """
            CREATE TABLE product_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL,
                captured_at TEXT NOT NULL CHECK (length(trim(captured_at)) > 0),
                page_url TEXT NOT NULL CHECK (length(trim(page_url)) > 0),
                title TEXT NOT NULL CHECK (length(trim(title)) > 0),
                main_image_url TEXT,
                visible_price_text TEXT,
                shop_name TEXT,
                shop_rating_text TEXT,
                shop_positive_rate_text TEXT,
                shop_shipping_text TEXT,
                shop_refund_text TEXT,
                sold_text TEXT,
                repeat_buyer_text TEXT,
                cart_text TEXT,
                review_count_text TEXT,
                review_preview_text TEXT,
                services_json TEXT NOT NULL CHECK (length(trim(services_json)) > 0),
                attributes_text TEXT,
                completeness_percent INTEGER NOT NULL
                    CHECK (completeness_percent BETWEEN 0 AND 100),
                raw_source_ref TEXT NOT NULL CHECK (length(trim(raw_source_ref)) > 0),
                parser_version INTEGER NOT NULL CHECK (parser_version > 0),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (product_id) REFERENCES products(id),
                UNIQUE (product_id, captured_at)
            )
            """,
            """
            CREATE TABLE sku_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_snapshot_id INTEGER NOT NULL UNIQUE,
                captured_at TEXT NOT NULL CHECK (length(trim(captured_at)) > 0),
                selected_options_json TEXT NOT NULL
                    CHECK (length(trim(selected_options_json)) > 0),
                display_price_text TEXT,
                sku_price_text TEXT,
                price_status TEXT NOT NULL CHECK (
                    price_status IN (
                        'captured',
                        'missing_after_refresh',
                        'ambiguous_after_refresh'
                    )
                ),
                raw_source_ref TEXT NOT NULL CHECK (length(trim(raw_source_ref)) > 0),
                parser_version INTEGER NOT NULL CHECK (parser_version > 0),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (product_snapshot_id)
                    REFERENCES product_snapshots(id) ON DELETE CASCADE,
                CHECK (
                    (price_status = 'captured'
                        AND sku_price_text IS NOT NULL
                        AND length(trim(sku_price_text)) > 0)
                    OR
                    (price_status IN ('missing_after_refresh', 'ambiguous_after_refresh')
                        AND sku_price_text IS NULL)
                )
            )
            """,
            """
            CREATE TRIGGER prevent_product_snapshots_update
            BEFORE UPDATE ON product_snapshots
            BEGIN
                SELECT RAISE(ABORT, 'append-only product_snapshots');
            END
            """,
            """
            CREATE TRIGGER prevent_sku_snapshots_update
            BEFORE UPDATE ON sku_snapshots
            BEGIN
                SELECT RAISE(ABORT, 'append-only sku_snapshots');
            END
            """,
            """
            CREATE INDEX product_snapshots_product_captured_at
            ON product_snapshots (product_id, captured_at DESC)
            """,
        ),
    ),
    (
        4,
        (
            """
            CREATE TABLE search_snapshot_pages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_id INTEGER NOT NULL,
                page_number INTEGER NOT NULL CHECK (page_number > 0),
                captured_at TEXT NOT NULL CHECK (length(trim(captured_at)) > 0),
                raw_source_ref TEXT NOT NULL CHECK (length(trim(raw_source_ref)) > 0),
                status TEXT NOT NULL CHECK (status IN ('success', 'exhausted')),
                result_count INTEGER NOT NULL CHECK (result_count >= 0),
                added_result_count INTEGER NOT NULL CHECK (added_result_count >= 0),
                has_next_page INTEGER NOT NULL CHECK (has_next_page IN (0, 1)),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (snapshot_id) REFERENCES search_snapshots(id) ON DELETE CASCADE,
                UNIQUE (snapshot_id, page_number)
            )
            """,
            """
            INSERT INTO search_snapshot_pages (
                snapshot_id,
                page_number,
                captured_at,
                raw_source_ref,
                status,
                result_count,
                added_result_count,
                has_next_page
            )
            SELECT
                search_snapshots.id,
                1,
                search_snapshots.captured_at,
                search_snapshots.raw_source_ref,
                'success',
                COUNT(search_results.id),
                COUNT(search_results.id),
                1
            FROM search_snapshots
            LEFT JOIN search_results
                ON search_results.snapshot_id = search_snapshots.id
            GROUP BY search_snapshots.id
            """,
            """
            CREATE TRIGGER prevent_search_snapshot_pages_update
            BEFORE UPDATE ON search_snapshot_pages
            BEGIN
                SELECT RAISE(ABORT, 'append-only search_snapshot_pages');
            END
            """,
            """
            CREATE INDEX search_snapshot_pages_snapshot_page
            ON search_snapshot_pages (snapshot_id, page_number)
            """,
        ),
    ),
    (
        5,
        (
            "ALTER TABLE search_results ADD COLUMN payment_text TEXT",
            "ALTER TABLE search_results ADD COLUMN origin_text TEXT",
            "ALTER TABLE search_results ADD COLUMN promotion_text TEXT",
            "ALTER TABLE search_results ADD COLUMN logistics_text TEXT",
            "ALTER TABLE search_results ADD COLUMN card_text TEXT",
            """
            CREATE TABLE product_capture_archives (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_snapshot_id INTEGER NOT NULL UNIQUE,
                captured_at TEXT NOT NULL CHECK (length(trim(captured_at)) > 0),
                product_fields_json TEXT NOT NULL CHECK (length(trim(product_fields_json)) > 0),
                images_json TEXT NOT NULL CHECK (length(trim(images_json)) > 0),
                sku_catalog_json TEXT NOT NULL CHECK (length(trim(sku_catalog_json)) > 0),
                reviews_json TEXT NOT NULL CHECK (length(trim(reviews_json)) > 0),
                questions_json TEXT NOT NULL CHECK (length(trim(questions_json)) > 0),
                videos_json TEXT NOT NULL CHECK (length(trim(videos_json)) > 0),
                coverage_json TEXT NOT NULL CHECK (length(trim(coverage_json)) > 0),
                capture_status_json TEXT NOT NULL CHECK (length(trim(capture_status_json)) > 0),
                raw_source_refs_json TEXT NOT NULL CHECK (length(trim(raw_source_refs_json)) > 0),
                parser_version INTEGER NOT NULL CHECK (parser_version > 0),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (product_snapshot_id)
                    REFERENCES product_snapshots(id) ON DELETE CASCADE
            )
            """,
            """
            CREATE TRIGGER prevent_product_capture_archives_update
            BEFORE UPDATE ON product_capture_archives
            BEGIN
                SELECT RAISE(ABORT, 'append-only product_capture_archives');
            END
            """,
            """
            CREATE INDEX product_capture_archives_snapshot
            ON product_capture_archives (product_snapshot_id)
            """,
        ),
    ),
    (
        6,
        (
            """
            CREATE TABLE complete_market_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_id INTEGER NOT NULL,
                generated_at TEXT NOT NULL CHECK (length(trim(generated_at)) > 0),
                method_version TEXT NOT NULL CHECK (length(trim(method_version)) > 0),
                model_name TEXT NOT NULL CHECK (length(trim(model_name)) > 0),
                capabilities_json TEXT NOT NULL CHECK (length(trim(capabilities_json)) > 0),
                analysis_json TEXT NOT NULL CHECK (length(trim(analysis_json)) > 0),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (snapshot_id) REFERENCES search_snapshots(id) ON DELETE CASCADE
            )
            """,
            """
            CREATE TRIGGER prevent_complete_market_reports_update
            BEFORE UPDATE ON complete_market_reports
            BEGIN
                SELECT RAISE(ABORT, 'append-only complete_market_reports');
            END
            """,
            """
            CREATE INDEX complete_market_reports_snapshot_generated
            ON complete_market_reports (snapshot_id, generated_at DESC, id DESC)
            """,
        ),
    ),
    (
        7,
        (
            """
            CREATE TABLE project_own_products (
                project_id INTEGER PRIMARY KEY,
                product_id INTEGER NOT NULL,
                updated_at TEXT NOT NULL CHECK (length(trim(updated_at)) > 0),
                FOREIGN KEY (project_id) REFERENCES market_projects(id) ON DELETE CASCADE,
                FOREIGN KEY (product_id) REFERENCES products(id)
            )
            """,
        ),
    ),
    (
        8,
        (
            "DROP TRIGGER IF EXISTS prevent_complete_market_reports_update",
            "DROP INDEX IF EXISTS complete_market_reports_snapshot_generated",
            "DROP TABLE IF EXISTS complete_market_reports",
            "DROP TABLE IF EXISTS project_own_products",
        ),
    ),
    (
        9,
        (
            """
            CREATE TABLE monitor_settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                enabled INTEGER NOT NULL CHECK (enabled IN (0, 1)),
                run_time TEXT NOT NULL CHECK (run_time GLOB '[0-2][0-9]:[0-5][0-9]'),
                updated_at TEXT NOT NULL CHECK (length(trim(updated_at)) > 0)
            )
            """,
            """
            INSERT INTO monitor_settings (id, enabled, run_time, updated_at)
            VALUES (1, 0, '10:00', CURRENT_TIMESTAMP)
            """,
            """
            CREATE TABLE monitor_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_type TEXT NOT NULL CHECK (task_type IN ('keyword', 'competitor')),
                target_key TEXT NOT NULL CHECK (length(trim(target_key)) > 0),
                project_id INTEGER NOT NULL,
                item_id TEXT,
                product_url TEXT,
                label TEXT NOT NULL CHECK (length(trim(label)) > 0),
                enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
                created_at TEXT NOT NULL CHECK (length(trim(created_at)) > 0),
                updated_at TEXT NOT NULL CHECK (length(trim(updated_at)) > 0),
                FOREIGN KEY (project_id) REFERENCES market_projects(id) ON DELETE CASCADE,
                UNIQUE (task_type, target_key),
                CHECK (
                    (task_type = 'keyword' AND item_id IS NULL AND product_url IS NULL)
                    OR
                    (task_type = 'competitor'
                        AND item_id IS NOT NULL
                        AND length(trim(item_id)) > 0
                        AND product_url IS NOT NULL
                        AND length(trim(product_url)) > 0)
                )
            )
            """,
            """
            CREATE INDEX monitor_tasks_enabled_type
            ON monitor_tasks (enabled, task_type, id)
            """,
            """
            CREATE TABLE monitor_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL CHECK (length(trim(started_at)) > 0),
                finished_at TEXT,
                status TEXT NOT NULL CHECK (status IN ('running', 'success', 'partial', 'failed', 'skipped')),
                task_count INTEGER NOT NULL DEFAULT 0 CHECK (task_count >= 0),
                success_count INTEGER NOT NULL DEFAULT 0 CHECK (success_count >= 0),
                failure_count INTEGER NOT NULL DEFAULT 0 CHECK (failure_count >= 0),
                summary_json TEXT NOT NULL DEFAULT '{}' CHECK (length(trim(summary_json)) > 0),
                error_text TEXT
            )
            """,
            """
            CREATE INDEX monitor_runs_started_at
            ON monitor_runs (started_at DESC, id DESC)
            """,
        ),
    ),
    (
        10,
        (
            "ALTER TABLE monitor_tasks ADD COLUMN page_count INTEGER NOT NULL DEFAULT 1 CHECK (page_count BETWEEN 1 AND 3)",
        ),
    ),
    (
        11,
        (
            "ALTER TABLE monitor_tasks RENAME TO monitor_tasks_v10",
            """
            CREATE TABLE monitor_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_type TEXT NOT NULL CHECK (task_type IN ('keyword', 'competitor', 'shop')),
                target_key TEXT NOT NULL CHECK (length(trim(target_key)) > 0),
                project_id INTEGER NOT NULL,
                item_id TEXT,
                product_url TEXT,
                shop_url TEXT,
                shop_name TEXT,
                label TEXT NOT NULL CHECK (length(trim(label)) > 0),
                enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
                created_at TEXT NOT NULL CHECK (length(trim(created_at)) > 0),
                updated_at TEXT NOT NULL CHECK (length(trim(updated_at)) > 0),
                page_count INTEGER NOT NULL DEFAULT 1 CHECK (page_count BETWEEN 1 AND 3),
                FOREIGN KEY (project_id) REFERENCES market_projects(id) ON DELETE CASCADE,
                UNIQUE (task_type, target_key),
                CHECK (
                    (task_type = 'keyword' AND item_id IS NULL AND product_url IS NULL AND shop_url IS NULL)
                    OR
                    (task_type = 'competitor'
                        AND item_id IS NOT NULL AND length(trim(item_id)) > 0
                        AND product_url IS NOT NULL AND length(trim(product_url)) > 0
                        AND shop_url IS NULL)
                    OR
                    (task_type = 'shop'
                        AND item_id IS NULL AND product_url IS NULL
                        AND shop_url IS NOT NULL AND length(trim(shop_url)) > 0)
                )
            )
            """,
            """
            INSERT INTO monitor_tasks (
                id, task_type, target_key, project_id, item_id, product_url,
                shop_url, shop_name, label, enabled, created_at, updated_at, page_count
            )
            SELECT id, task_type, target_key, project_id, item_id, product_url,
                   NULL, NULL, label, enabled, created_at, updated_at, page_count
            FROM monitor_tasks_v10
            """,
            "DROP TABLE monitor_tasks_v10",
            """
            CREATE INDEX monitor_tasks_enabled_type
            ON monitor_tasks (enabled, task_type, id)
            """,
            """
            CREATE TABLE shop_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                monitor_task_id INTEGER NOT NULL,
                captured_at TEXT NOT NULL CHECK (length(trim(captured_at)) > 0),
                shop_url TEXT NOT NULL CHECK (length(trim(shop_url)) > 0),
                shop_name TEXT,
                raw_source_ref TEXT NOT NULL CHECK (length(trim(raw_source_ref)) > 0),
                result_count INTEGER NOT NULL CHECK (result_count >= 0),
                parser_version INTEGER NOT NULL DEFAULT 1 CHECK (parser_version > 0),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (monitor_task_id) REFERENCES monitor_tasks(id) ON DELETE CASCADE,
                UNIQUE (monitor_task_id, captured_at)
            )
            """,
            """
            CREATE TABLE shop_snapshot_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                shop_snapshot_id INTEGER NOT NULL,
                item_id TEXT NOT NULL CHECK (length(trim(item_id)) > 0),
                title TEXT,
                product_url TEXT,
                image_url TEXT,
                price_text TEXT,
                payment_text TEXT,
                display_rank INTEGER NOT NULL CHECK (display_rank > 0),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (shop_snapshot_id) REFERENCES shop_snapshots(id) ON DELETE CASCADE,
                UNIQUE (shop_snapshot_id, item_id)
            )
            """,
            "CREATE INDEX shop_snapshots_task_captured ON shop_snapshots (monitor_task_id, captured_at DESC, id DESC)",
            "CREATE INDEX shop_snapshot_items_snapshot_rank ON shop_snapshot_items (shop_snapshot_id, display_rank)",
        ),
    ),
    (
        12,
        (
            """
            CREATE TABLE competitor_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL UNIQUE,
                source_url TEXT NOT NULL CHECK (length(trim(source_url)) > 0),
                resolved_url TEXT NOT NULL CHECK (length(trim(resolved_url)) > 0),
                first_captured_at TEXT NOT NULL CHECK (length(trim(first_captured_at)) > 0),
                last_captured_at TEXT NOT NULL CHECK (length(trim(last_captured_at)) > 0),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL CHECK (length(trim(updated_at)) > 0),
                FOREIGN KEY (product_id) REFERENCES products(id)
            )
            """,
            """
            CREATE INDEX competitor_records_last_captured
            ON competitor_records (last_captured_at DESC, id DESC)
            """,
        ),
    ),
    (
        13,
        (
            "DROP INDEX IF EXISTS shop_snapshot_items_snapshot_rank",
            "DROP INDEX IF EXISTS shop_snapshots_task_captured",
            "DROP INDEX IF EXISTS monitor_tasks_enabled_type",
            "ALTER TABLE shop_snapshot_items RENAME TO shop_snapshot_items_v12",
            "ALTER TABLE shop_snapshots RENAME TO shop_snapshots_v12",
            "ALTER TABLE monitor_tasks RENAME TO monitor_tasks_v12",
            """
            CREATE TABLE monitor_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_type TEXT NOT NULL CHECK (task_type IN ('keyword', 'competitor', 'shop')),
                target_key TEXT NOT NULL CHECK (length(trim(target_key)) > 0),
                project_id INTEGER,
                item_id TEXT,
                product_url TEXT,
                shop_url TEXT,
                shop_name TEXT,
                label TEXT NOT NULL CHECK (length(trim(label)) > 0),
                enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
                created_at TEXT NOT NULL CHECK (length(trim(created_at)) > 0),
                updated_at TEXT NOT NULL CHECK (length(trim(updated_at)) > 0),
                page_count INTEGER NOT NULL DEFAULT 1 CHECK (page_count BETWEEN 1 AND 3),
                FOREIGN KEY (project_id) REFERENCES market_projects(id) ON DELETE CASCADE,
                UNIQUE (task_type, target_key),
                CHECK (
                    (task_type = 'keyword'
                        AND project_id IS NOT NULL
                        AND item_id IS NULL AND product_url IS NULL AND shop_url IS NULL)
                    OR
                    (task_type = 'competitor'
                        AND item_id IS NOT NULL AND length(trim(item_id)) > 0
                        AND product_url IS NOT NULL AND length(trim(product_url)) > 0
                        AND shop_url IS NULL)
                    OR
                    (task_type = 'shop'
                        AND project_id IS NOT NULL
                        AND item_id IS NULL AND product_url IS NULL
                        AND shop_url IS NOT NULL AND length(trim(shop_url)) > 0)
                )
            )
            """,
            """
            CREATE TABLE shop_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                monitor_task_id INTEGER NOT NULL,
                captured_at TEXT NOT NULL CHECK (length(trim(captured_at)) > 0),
                shop_url TEXT NOT NULL CHECK (length(trim(shop_url)) > 0),
                shop_name TEXT,
                raw_source_ref TEXT NOT NULL CHECK (length(trim(raw_source_ref)) > 0),
                result_count INTEGER NOT NULL CHECK (result_count >= 0),
                parser_version INTEGER NOT NULL DEFAULT 1 CHECK (parser_version > 0),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (monitor_task_id) REFERENCES monitor_tasks(id) ON DELETE CASCADE,
                UNIQUE (monitor_task_id, captured_at)
            )
            """,
            """
            CREATE TABLE shop_snapshot_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                shop_snapshot_id INTEGER NOT NULL,
                item_id TEXT NOT NULL CHECK (length(trim(item_id)) > 0),
                title TEXT,
                product_url TEXT,
                image_url TEXT,
                price_text TEXT,
                payment_text TEXT,
                display_rank INTEGER NOT NULL CHECK (display_rank > 0),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (shop_snapshot_id) REFERENCES shop_snapshots(id) ON DELETE CASCADE,
                UNIQUE (shop_snapshot_id, item_id)
            )
            """,
            """
            INSERT INTO monitor_tasks (
                id, task_type, target_key, project_id, item_id, product_url,
                shop_url, shop_name, label, enabled, created_at, updated_at, page_count
            )
            SELECT id, task_type, target_key, project_id, item_id, product_url,
                   shop_url, shop_name, label, enabled, created_at, updated_at, page_count
            FROM monitor_tasks_v12
            """,
            """
            INSERT INTO shop_snapshots (
                id, monitor_task_id, captured_at, shop_url, shop_name, raw_source_ref,
                result_count, parser_version, created_at
            )
            SELECT id, monitor_task_id, captured_at, shop_url, shop_name, raw_source_ref,
                   result_count, parser_version, created_at
            FROM shop_snapshots_v12
            """,
            """
            INSERT INTO shop_snapshot_items (
                id, shop_snapshot_id, item_id, title, product_url, image_url,
                price_text, payment_text, display_rank, created_at
            )
            SELECT id, shop_snapshot_id, item_id, title, product_url, image_url,
                   price_text, payment_text, display_rank, created_at
            FROM shop_snapshot_items_v12
            """,
            "DROP TABLE shop_snapshot_items_v12",
            "DROP TABLE shop_snapshots_v12",
            "DROP TABLE monitor_tasks_v12",
            "CREATE INDEX monitor_tasks_enabled_type ON monitor_tasks (enabled, task_type, id)",
            "CREATE INDEX shop_snapshots_task_captured ON shop_snapshots (monitor_task_id, captured_at DESC, id DESC)",
            "CREATE INDEX shop_snapshot_items_snapshot_rank ON shop_snapshot_items (shop_snapshot_id, display_rank)",
        ),
    ),
    (
        14,
        (
            """
            INSERT OR IGNORE INTO competitor_records (
                product_id,
                source_url,
                resolved_url,
                first_captured_at,
                last_captured_at,
                created_at,
                updated_at
            )
            SELECT
                latest.product_id,
                latest.page_url,
                latest.page_url,
                history.first_captured_at,
                history.last_captured_at,
                history.first_captured_at,
                history.last_captured_at
            FROM product_snapshots AS latest
            JOIN (
                SELECT
                    product_id,
                    MIN(captured_at) AS first_captured_at,
                    MAX(captured_at) AS last_captured_at
                FROM product_snapshots
                GROUP BY product_id
            ) AS history ON history.product_id = latest.product_id
            WHERE latest.id = (
                SELECT candidate.id
                FROM product_snapshots AS candidate
                WHERE candidate.product_id = latest.product_id
                ORDER BY candidate.captured_at DESC, candidate.id DESC
                LIMIT 1
            )
            """,
        ),
    ),
)


def resolve_application_data_directory(*, packaged=None, local_app_data=None):
    configured_directory = os.environ.get(APPLICATION_DATA_DIRECTORY_ENV)
    if str(configured_directory or "").strip():
        return Path(configured_directory).expanduser()

    if packaged is None:
        packaged = bool(getattr(sys, "frozen", False))
    if not isinstance(packaged, bool):
        raise ValueError(f"packaged must be bool: actual={packaged!r}")

    if not packaged:
        return DEVELOPMENT_DATA_DIRECTORY

    if local_app_data is None:
        local_app_data = os.environ.get("LOCALAPPDATA")
    if not str(local_app_data or "").strip():
        raise ValueError(f"local_app_data={local_app_data!r} is required when packaged=True")

    return Path(local_app_data) / PACKAGED_DIRECTORY_NAME / "data"


def _validate_schema_migrations(schema_migrations):
    if not schema_migrations:
        raise ValueError(f"schema_migrations must not be empty: actual={schema_migrations!r}")

    for expected_version, migration in enumerate(schema_migrations, start=1):
        if not isinstance(migration, tuple) or len(migration) != 2:
            raise ValueError(f"invalid migration entry: actual={migration!r}")
        migration_version, sql_statements = migration
        if migration_version != expected_version:
            raise ValueError(
                f"migration versions must be sequential: "
                f"expected_version={expected_version} actual_version={migration_version!r}"
            )
        if not sql_statements:
            raise ValueError(
                f"migration statements must not be empty: migration_version={migration_version}"
            )
        for sql_statement in sql_statements:
            if not isinstance(sql_statement, str) or not sql_statement.strip():
                raise ValueError(
                    f"migration SQL must be non-empty text: "
                    f"migration_version={migration_version} actual={sql_statement!r}"
                )


def _read_applied_versions(connection):
    version_table_exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_versions'"
    ).fetchone()
    if version_table_exists is None:
        return set()

    return {
        row[0]
        for row in connection.execute(
            "SELECT version FROM schema_versions ORDER BY version"
        ).fetchall()
    }


def apply_schema_migrations(connection, schema_migrations=SCHEMA_MIGRATIONS):
    _validate_schema_migrations(schema_migrations)
    failed_migration_version = 0

    try:
        connection.execute("BEGIN IMMEDIATE")
        with connection:
            applied_versions = _read_applied_versions(connection)
            declared_versions = {version for version, _ in schema_migrations}
            unknown_versions = sorted(applied_versions - declared_versions)
            if unknown_versions:
                raise RuntimeError(
                    f"database contains unknown schema versions: actual={unknown_versions}"
                )

            for migration_version, sql_statements in schema_migrations:
                if migration_version in applied_versions:
                    continue
                failed_migration_version = migration_version
                for sql_statement in sql_statements:
                    connection.execute(sql_statement)
                connection.execute(
                    "INSERT INTO schema_versions (version) VALUES (?)",
                    (migration_version,),
                )
    except sqlite3.DatabaseError as exc:
        raise RuntimeError(
            f"Database migration failed: migration_version={failed_migration_version} "
            f"sqlite_error={exc}"
        ) from exc


def initialize_database(application_data_directory=None, *, schema_migrations=SCHEMA_MIGRATIONS):
    if application_data_directory is None:
        application_data_directory = resolve_application_data_directory()
    if not str(application_data_directory).strip():
        raise ValueError(
            f"application_data_directory must not be empty: "
            f"actual={application_data_directory!r}"
        )

    resolved_directory = Path(application_data_directory)
    if resolved_directory.exists() and not resolved_directory.is_dir():
        raise NotADirectoryError(
            f"application_data_directory is not a directory: actual={resolved_directory}"
        )
    resolved_directory.mkdir(parents=True, exist_ok=True)
    database_path = resolved_directory / DATABASE_FILENAME

    try:
        connection = sqlite3.connect(database_path)
    except sqlite3.DatabaseError as exc:
        raise RuntimeError(
            f"Cannot open SQLite database: path={database_path} sqlite_error={exc}"
        ) from exc

    try:
        connection.execute("PRAGMA foreign_keys = ON")
        apply_schema_migrations(connection, schema_migrations)
    finally:
        connection.close()

    return database_path


def connect_database(application_data_directory=None):
    database_path = initialize_database(application_data_directory)
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def save_search_snapshot(
    connection,
    project_id,
    keyword,
    search_type,
    requested_result_count,
    captured_at,
    raw_source_ref,
    parsed_products,
    *,
    has_next_page=True,
    read_result_count=None,
):
    if read_result_count is None:
        read_result_count = len(parsed_products)
    if read_result_count < len(parsed_products):
        raise ValueError(
            "read_result_count cannot be smaller than saved products: "
            f"read_result_count={read_result_count!r} saved={len(parsed_products)!r}"
        )
    with connection:
        snapshot_cursor = connection.execute(
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
                keyword,
                search_type,
                requested_result_count,
                captured_at,
                raw_source_ref,
                1,
            ),
        )
        snapshot_id = snapshot_cursor.lastrowid

        connection.execute(
            """
            INSERT INTO search_snapshot_pages (
                snapshot_id,
                page_number,
                captured_at,
                raw_source_ref,
                status,
                result_count,
                added_result_count,
                has_next_page
            ) VALUES (?, 1, ?, ?, 'success', ?, ?, ?)
            """,
            (
                snapshot_id,
                captured_at,
                raw_source_ref,
                read_result_count,
                len(parsed_products),
                int(bool(has_next_page)),
            ),
        )

        for display_rank, parsed_product in enumerate(parsed_products, start=1):
            connection.execute(
                "INSERT INTO products (item_id) VALUES (?) ON CONFLICT(item_id) DO NOTHING",
                (parsed_product["item_id"],),
            )
            product_row = connection.execute(
                "SELECT id FROM products WHERE item_id = ?",
                (parsed_product["item_id"],),
            ).fetchone()
            if product_row is None:
                raise RuntimeError(
                    f"Saved product not found: item_id={parsed_product['item_id']!r}"
                )

            connection.execute(
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
                    suspected_ad,
                    payment_text,
                    origin_text,
                    promotion_text,
                    logistics_text,
                    card_text
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot_id,
                    product_row["id"],
                    display_rank,
                    parsed_product["sku_id"],
                    parsed_product["title"],
                    parsed_product["shop_name"],
                    parsed_product["display_price"],
                    parsed_product["product_url"],
                    parsed_product["shop_url"],
                    parsed_product["image_url"],
                    parsed_product["platform_type"],
                    parsed_product["suspected_ad"],
                    parsed_product.get("payment_text"),
                    parsed_product.get("origin_text"),
                    parsed_product.get("promotion_text"),
                    parsed_product.get("logistics_text"),
                    parsed_product.get("card_text"),
                ),
            )

    return snapshot_id


def append_search_snapshot_page(
    connection,
    project_id,
    snapshot_id,
    page_number,
    captured_at,
    raw_source_ref,
    parsed_products,
    *,
    has_next_page,
    status="success",
):
    if status not in {"success", "exhausted"}:
        raise ValueError(f"invalid page status: actual={status!r}")
    if status == "exhausted" and parsed_products:
        raise ValueError("exhausted page must not contain products")

    snapshot_row = connection.execute(
        "SELECT id FROM search_snapshots WHERE id = ? AND project_id = ?",
        (snapshot_id, project_id),
    ).fetchone()
    if snapshot_row is None:
        raise LookupError(
            f"Search snapshot not found: snapshot_id={snapshot_id} project_id={project_id}"
        )

    last_page_row = connection.execute(
        """
        SELECT page_number, has_next_page
        FROM search_snapshot_pages
        WHERE snapshot_id = ?
        ORDER BY page_number DESC
        LIMIT 1
        """,
        (snapshot_id,),
    ).fetchone()
    expected_page_number = (last_page_row["page_number"] if last_page_row else 0) + 1
    if page_number != expected_page_number:
        raise ValueError(
            f"next page must be {expected_page_number}: actual={page_number!r}"
        )
    if last_page_row is not None and not bool(last_page_row["has_next_page"]):
        raise ValueError("snapshot has no next page")

    existing_item_ids = {
        str(row["item_id"])
        for row in connection.execute(
            """
            SELECT products.item_id
            FROM search_results
            JOIN products ON products.id = search_results.product_id
            WHERE search_results.snapshot_id = ?
            """,
            (snapshot_id,),
        ).fetchall()
    }
    unique_products = []
    page_item_ids = set()
    for parsed_product in parsed_products:
        item_id = str(parsed_product["item_id"])
        if item_id in existing_item_ids or item_id in page_item_ids:
            continue
        page_item_ids.add(item_id)
        unique_products.append(parsed_product)

    maximum_rank_row = connection.execute(
        "SELECT COALESCE(MAX(display_rank), 0) AS maximum_rank FROM search_results WHERE snapshot_id = ?",
        (snapshot_id,),
    ).fetchone()
    maximum_rank = maximum_rank_row["maximum_rank"]

    with connection:
        connection.execute(
            """
            INSERT INTO search_snapshot_pages (
                snapshot_id,
                page_number,
                captured_at,
                raw_source_ref,
                status,
                result_count,
                added_result_count,
                has_next_page
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot_id,
                page_number,
                captured_at,
                raw_source_ref,
                status,
                len(parsed_products),
                len(unique_products),
                int(bool(has_next_page)),
            ),
        )
        for offset, parsed_product in enumerate(unique_products, start=1):
            connection.execute(
                "INSERT INTO products (item_id) VALUES (?) ON CONFLICT(item_id) DO NOTHING",
                (parsed_product["item_id"],),
            )
            product_row = connection.execute(
                "SELECT id FROM products WHERE item_id = ?",
                (parsed_product["item_id"],),
            ).fetchone()
            if product_row is None:
                raise RuntimeError(
                    f"Saved product not found: item_id={parsed_product['item_id']!r}"
                )
            connection.execute(
                """
                INSERT INTO search_results (
                    snapshot_id, product_id, display_rank, sku_id, title,
                    shop_name, display_price, product_url, shop_url, image_url,
                    platform_type, suspected_ad, payment_text, origin_text,
                    promotion_text, logistics_text, card_text
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot_id,
                    product_row["id"],
                    maximum_rank + offset,
                    parsed_product["sku_id"],
                    parsed_product["title"],
                    parsed_product["shop_name"],
                    parsed_product["display_price"],
                    parsed_product["product_url"],
                    parsed_product["shop_url"],
                    parsed_product["image_url"],
                    parsed_product["platform_type"],
                    parsed_product["suspected_ad"],
                    parsed_product.get("payment_text"),
                    parsed_product.get("origin_text"),
                    parsed_product.get("promotion_text"),
                    parsed_product.get("logistics_text"),
                    parsed_product.get("card_text"),
                ),
            )

    return {
        "status": status,
        "page_number": page_number,
        "result_count": len(parsed_products),
        "read_result_count": len(parsed_products),
        "duplicate_result_count": len(parsed_products) - len(unique_products),
        "added_result_count": len(unique_products),
        "has_next_page": bool(has_next_page),
    }


def search_result_response(search_result, display_rank, captured_at):
    present_field_count = sum(
        search_result[field_name] not in (None, "")
        for field_name in SEARCH_COMPLETENESS_FIELDS
    )
    return {
        "item_id": search_result["item_id"],
        "sku_id": search_result["sku_id"],
        "title": search_result["title"],
        "shop_name": search_result["shop_name"],
        "display_price": search_result["display_price"],
        "product_url": search_result["product_url"],
        "shop_url": search_result["shop_url"],
        "image_url": search_result["image_url"],
        "platform_type": search_result["platform_type"],
        "suspected_ad": search_result["suspected_ad"],
        "payment_text": search_result["payment_text"],
        "origin_text": search_result["origin_text"],
        "promotion_text": search_result["promotion_text"],
        "logistics_text": search_result["logistics_text"],
        "card_text": search_result["card_text"],
        "display_rank": display_rank,
        "captured_at": captured_at,
        "completeness_percent": round(
            present_field_count * 100 / len(SEARCH_COMPLETENESS_FIELDS)
        ),
    }


def _require_project(connection, project_id):
    project_row = connection.execute(
        "SELECT id FROM market_projects WHERE id = ?",
        (project_id,),
    ).fetchone()
    if project_row is None:
        raise LookupError(f"Market project not found: project_id={project_id}")


def list_search_snapshots(connection, project_id):
    _require_project(connection, project_id)
    snapshot_rows = connection.execute(
        """
        SELECT
            search_snapshots.id,
            search_snapshots.captured_at,
            search_snapshots.requested_result_count,
            search_snapshots.raw_source_ref,
            COUNT(search_results.id) AS result_count,
            (
                SELECT COUNT(*)
                FROM search_snapshot_pages
                WHERE search_snapshot_pages.snapshot_id = search_snapshots.id
                    AND search_snapshot_pages.status = 'success'
            ) AS captured_page_count,
            (
                SELECT COALESCE(MAX(page_number), 0) + 1
                FROM search_snapshot_pages
                WHERE search_snapshot_pages.snapshot_id = search_snapshots.id
            ) AS next_page_number,
            COALESCE((
                SELECT has_next_page
                FROM search_snapshot_pages
                WHERE search_snapshot_pages.snapshot_id = search_snapshots.id
                ORDER BY page_number DESC
                LIMIT 1
            ), 0) AS can_collect_next_page
        FROM search_snapshots
        LEFT JOIN search_results
            ON search_results.snapshot_id = search_snapshots.id
        WHERE search_snapshots.project_id = ?
        GROUP BY search_snapshots.id
        ORDER BY search_snapshots.captured_at DESC, search_snapshots.id DESC
        """,
        (project_id,),
    ).fetchall()
    return [
        {
            "snapshot_id": snapshot_row["id"],
            "captured_at": snapshot_row["captured_at"],
            "requested_result_count": snapshot_row["requested_result_count"],
            "result_count": snapshot_row["result_count"],
            "raw_source_ref": snapshot_row["raw_source_ref"],
            "captured_page_count": snapshot_row["captured_page_count"],
            "next_page_number": snapshot_row["next_page_number"],
            "can_collect_next_page": bool(snapshot_row["can_collect_next_page"]),
        }
        for snapshot_row in snapshot_rows
    ]


def list_search_raw_source_refs(connection, snapshot_id=None):
    parameters = ()
    where_clause = ""
    if snapshot_id is not None:
        where_clause = "WHERE search_snapshot_pages.snapshot_id = ?"
        parameters = (snapshot_id,)
    rows = connection.execute(
        f"""
        SELECT search_snapshot_pages.raw_source_ref
        FROM search_snapshot_pages
        JOIN search_snapshots
            ON search_snapshots.id = search_snapshot_pages.snapshot_id
        {where_clause}
        ORDER BY
            search_snapshots.captured_at DESC,
            search_snapshots.id DESC,
            search_snapshot_pages.page_number ASC
        """,
        parameters,
    ).fetchall()
    return [row["raw_source_ref"] for row in rows]


def read_search_snapshot(connection, snapshot_id, project_id=None):
    snapshot_row = connection.execute(
        """
        SELECT id, project_id, captured_at, requested_result_count, raw_source_ref
        FROM search_snapshots WHERE id = ?
        """,
        (snapshot_id,),
    ).fetchone()
    if snapshot_row is None:
        raise LookupError(f"Search snapshot not found: snapshot_id={snapshot_id}")
    if project_id is not None and snapshot_row["project_id"] != project_id:
        raise LookupError(
            f"Search snapshot does not belong to project: "
            f"snapshot_id={snapshot_id} project_id={project_id} "
            f"actual_project_id={snapshot_row['project_id']}"
        )

    result_rows = connection.execute(
        """
        SELECT
            products.item_id,
            search_results.sku_id,
            search_results.title,
            search_results.shop_name,
            search_results.display_price,
            search_results.product_url,
            search_results.shop_url,
            search_results.image_url,
            search_results.platform_type,
            search_results.suspected_ad,
            search_results.payment_text,
            search_results.origin_text,
            search_results.promotion_text,
            search_results.logistics_text,
            search_results.card_text,
            search_results.display_rank
        FROM search_results
        JOIN products ON products.id = search_results.product_id
        WHERE search_results.snapshot_id = ?
        ORDER BY search_results.display_rank
        """,
        (snapshot_id,),
    ).fetchall()
    results = [
        search_result_response(
            result_row,
            result_row["display_rank"],
            snapshot_row["captured_at"],
        )
        for result_row in result_rows
    ]
    page_summary_row = connection.execute(
        """
        SELECT
            SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS captured_page_count,
            COALESCE(MAX(page_number), 0) + 1 AS next_page_number,
            COALESCE((
                SELECT latest.has_next_page
                FROM search_snapshot_pages AS latest
                WHERE latest.snapshot_id = ?
                ORDER BY latest.page_number DESC
                LIMIT 1
            ), 0) AS can_collect_next_page
        FROM search_snapshot_pages
        WHERE snapshot_id = ?
        """,
        (snapshot_id, snapshot_id),
    ).fetchone()
    return {
        "snapshot_id": snapshot_row["id"],
        "captured_at": snapshot_row["captured_at"],
        "requested_result_count": snapshot_row["requested_result_count"],
        "result_count": len(results),
        "raw_source_ref": snapshot_row["raw_source_ref"],
        "raw_source_refs": list_search_raw_source_refs(connection, snapshot_id),
        "captured_page_count": page_summary_row["captured_page_count"] or 0,
        "next_page_number": page_summary_row["next_page_number"],
        "can_collect_next_page": bool(page_summary_row["can_collect_next_page"]),
        "results": results,
    }


def compare_search_snapshots(
    connection,
    project_id,
    older_snapshot_id,
    newer_snapshot_id,
):
    older_snapshot = read_search_snapshot(
        connection,
        older_snapshot_id,
        project_id,
    )
    newer_snapshot = read_search_snapshot(
        connection,
        newer_snapshot_id,
        project_id,
    )
    older_by_item_id = {
        result["item_id"]: result for result in older_snapshot["results"]
    }
    newer_by_item_id = {
        result["item_id"]: result for result in newer_snapshot["results"]
    }

    added_item_ids = sorted(newer_by_item_id.keys() - older_by_item_id.keys())
    removed_item_ids = sorted(older_by_item_id.keys() - newer_by_item_id.keys())
    shared_item_ids = sorted(older_by_item_id.keys() & newer_by_item_id.keys())
    rank_changes = []
    price_changes = []
    payment_changes = []
    promotion_changes = []
    logistics_changes = []
    shop_changes = []
    title_changes = []
    image_changes = []
    for item_id in shared_item_ids:
        older_result = older_by_item_id[item_id]
        newer_result = newer_by_item_id[item_id]
        if older_result["display_rank"] != newer_result["display_rank"]:
            rank_changes.append(
                {
                    "item_id": item_id,
                    "title": newer_result["title"] or older_result["title"],
                    "old_rank": older_result["display_rank"],
                    "new_rank": newer_result["display_rank"],
                }
            )
        if older_result["display_price"] != newer_result["display_price"]:
            price_changes.append(
                {
                    "item_id": item_id,
                    "title": newer_result["title"] or older_result["title"],
                    "old_price": older_result["display_price"],
                    "new_price": newer_result["display_price"],
                }
            )
        for field_name, changes in (
            ("payment_text", payment_changes),
            ("promotion_text", promotion_changes),
            ("logistics_text", logistics_changes),
            ("shop_name", shop_changes),
            ("title", title_changes),
            ("image_url", image_changes),
        ):
            if older_result.get(field_name) == newer_result.get(field_name):
                continue
            changes.append(
                {
                    "item_id": item_id,
                    "title": newer_result["title"] or older_result["title"],
                    "old_value": older_result.get(field_name),
                    "new_value": newer_result.get(field_name),
                }
            )

    return {
        "older_snapshot_id": older_snapshot_id,
        "newer_snapshot_id": newer_snapshot_id,
        "added": [newer_by_item_id[item_id] for item_id in added_item_ids],
        "removed": [older_by_item_id[item_id] for item_id in removed_item_ids],
        "rank_changes": rank_changes,
        "price_changes": price_changes,
        "payment_changes": payment_changes,
        "promotion_changes": promotion_changes,
        "logistics_changes": logistics_changes,
        "shop_changes": shop_changes,
        "title_changes": title_changes,
        "image_changes": image_changes,
    }


def _required_snapshot_text(field_name, value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty text: actual={value!r}")
    return value.strip()


def _optional_snapshot_text(field_name, value):
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be text or None: actual={value!r}")
    normalized_value = value.strip()
    return normalized_value or None


def _required_snapshot_object(field_name, value):
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be an object: actual={value!r}")
    return value


def _validated_product_capture(product_detail, captured_at, raw_source_ref):
    detail = _required_snapshot_object("product_detail", product_detail)
    product = _required_snapshot_object("product_detail.product", detail.get("product"))
    shop = _required_snapshot_object("product_detail.shop", detail.get("shop"))
    sales = _required_snapshot_object("product_detail.sales", detail.get("sales"))
    reviews = _required_snapshot_object("product_detail.reviews", detail.get("reviews"))
    attributes = _required_snapshot_object(
        "product_detail.attributes",
        detail.get("attributes"),
    )
    services = detail.get("services")
    if not isinstance(services, list) or any(
        not isinstance(service, str) or not service.strip() for service in services
    ):
        raise ValueError(
            f"product_detail.services must be a list of non-empty text: "
            f"actual={services!r}"
        )
    normalized_services = list(dict.fromkeys(service.strip() for service in services))
    captured_at = _required_snapshot_text("captured_at", captured_at)
    raw_source_ref = _required_snapshot_text("raw_source_ref", raw_source_ref)

    normalized = {
        "item_id": _required_snapshot_text("product.item_id", product.get("item_id")),
        "captured_at": captured_at,
        "page_url": _required_snapshot_text("page_url", detail.get("page_url")),
        "title": _required_snapshot_text("product.page_title", product.get("page_title")),
        "main_image_url": _optional_snapshot_text(
            "product.main_image_url",
            product.get("main_image_url"),
        ),
        "visible_price_text": _optional_snapshot_text(
            "product.visible_price_text",
            product.get("visible_price_text"),
        ),
        "shop_name": _optional_snapshot_text("shop.name", shop.get("name")),
        "shop_rating_text": _optional_snapshot_text(
            "shop.rating_text",
            shop.get("rating_text"),
        ),
        "shop_positive_rate_text": _optional_snapshot_text(
            "shop.positive_rate_text",
            shop.get("positive_rate_text"),
        ),
        "shop_shipping_text": _optional_snapshot_text(
            "shop.shipping_text",
            shop.get("shipping_text"),
        ),
        "shop_refund_text": _optional_snapshot_text(
            "shop.refund_text",
            shop.get("refund_text"),
        ),
        "sold_text": _optional_snapshot_text("sales.sold_text", sales.get("sold_text")),
        "repeat_buyer_text": _optional_snapshot_text(
            "sales.repeat_buyer_text",
            sales.get("repeat_buyer_text"),
        ),
        "cart_text": _optional_snapshot_text("sales.cart_text", sales.get("cart_text")),
        "review_count_text": _optional_snapshot_text(
            "reviews.count_text",
            reviews.get("count_text"),
        ),
        "review_preview_text": _optional_snapshot_text(
            "reviews.preview_text",
            reviews.get("preview_text"),
        ),
        "services": normalized_services,
        "attributes_text": _optional_snapshot_text(
            "attributes.visible_text",
            attributes.get("visible_text"),
        ),
        "raw_source_ref": raw_source_ref,
    }
    completeness_values = (
        normalized["title"],
        normalized["main_image_url"],
        normalized["visible_price_text"],
        normalized["shop_name"],
        normalized["sold_text"],
        normalized["review_count_text"],
        normalized["attributes_text"],
        normalized_services or None,
    )
    normalized["completeness_percent"] = round(
        sum(value is not None for value in completeness_values)
        * 100
        / len(completeness_values)
    )
    return normalized


def _validated_sku_capture(sku_capture, captured_at):
    if sku_capture is None:
        return None
    capture = _required_snapshot_object("sku_capture", sku_capture)
    selected_options = capture.get("selected_options")
    if not isinstance(selected_options, list) or not selected_options:
        raise ValueError(
            f"sku_capture.selected_options must be a non-empty list: "
            f"actual={selected_options!r}"
        )
    normalized_options = []
    seen_dimensions = set()
    for option_index, option in enumerate(selected_options):
        option = _required_snapshot_object(
            f"sku_capture.selected_options[{option_index}]",
            option,
        )
        dimension = _required_snapshot_text("SKU dimension", option.get("dimension"))
        value = _required_snapshot_text("SKU value", option.get("value"))
        element_index = option.get("index")
        if (
            not isinstance(element_index, int)
            or isinstance(element_index, bool)
            or element_index < 0
        ):
            raise ValueError(
                f"SKU index must be a non-negative integer: actual={element_index!r}"
            )
        if dimension in seen_dimensions:
            raise ValueError(f"SKU dimension is duplicated: actual={dimension!r}")
        seen_dimensions.add(dimension)
        normalized_options.append(
            {"dimension": dimension, "value": value, "index": element_index}
        )

    price_status = capture.get("price_status")
    if price_status not in (
        "captured",
        "missing_after_refresh",
        "ambiguous_after_refresh",
    ):
        raise ValueError(f"Unsupported SKU price_status: actual={price_status!r}")
    sku_price_text = _optional_snapshot_text(
        "sku_capture.sku_price_text",
        capture.get("sku_price_text"),
    )
    if price_status == "captured" and sku_price_text is None:
        raise ValueError("captured SKU price requires non-empty sku_price_text")
    if price_status != "captured" and sku_price_text is not None:
        raise ValueError(
            f"{price_status} SKU price requires sku_price_text=None: "
            f"actual={sku_price_text!r}"
        )
    return {
        "captured_at": captured_at,
        "selected_options": normalized_options,
        "display_price_text": _optional_snapshot_text(
            "sku_capture.display_price_text",
            capture.get("display_price_text"),
        ),
        "sku_price_text": sku_price_text,
        "price_status": price_status,
        "raw_source_ref": _required_snapshot_text(
            "sku_capture.raw_price_ref",
            capture.get("raw_price_ref"),
        ),
    }


def _validated_product_archive(archive, captured_at):
    if archive is None:
        return None
    archive = _required_snapshot_object("product_archive", archive)
    expected_types = {
        "product_fields": dict,
        "images": list,
        "sku_catalog": dict,
        "reviews": dict,
        "questions": dict,
        "videos": list,
        "coverage": dict,
        "capture_status": dict,
        "raw_source_refs": dict,
    }
    normalized = {"captured_at": captured_at}
    for field_name, expected_type in expected_types.items():
        value = archive.get(field_name)
        if not isinstance(value, expected_type):
            raise ValueError(
                f"product_archive.{field_name} must be {expected_type.__name__}: "
                f"actual={value!r}"
            )
        normalized[field_name] = value
    return normalized


def save_product_capture(
    connection,
    product_detail,
    captured_at,
    raw_source_ref,
    *,
    sku_capture=None,
    archive=None,
):
    product_capture = _validated_product_capture(
        product_detail,
        captured_at,
        raw_source_ref,
    )
    validated_sku_capture = _validated_sku_capture(
        sku_capture,
        product_capture["captured_at"],
    )
    validated_archive = _validated_product_archive(
        archive,
        product_capture["captured_at"],
    )

    with connection:
        connection.execute(
            "INSERT INTO products (item_id) VALUES (?) ON CONFLICT(item_id) DO NOTHING",
            (product_capture["item_id"],),
        )
        product_row = connection.execute(
            "SELECT id FROM products WHERE item_id = ?",
            (product_capture["item_id"],),
        ).fetchone()
        product_snapshot_cursor = connection.execute(
            """
            INSERT INTO product_snapshots (
                product_id, captured_at, page_url, title, main_image_url,
                visible_price_text, shop_name, shop_rating_text,
                shop_positive_rate_text, shop_shipping_text, shop_refund_text,
                sold_text, repeat_buyer_text, cart_text, review_count_text,
                review_preview_text, services_json, attributes_text,
                completeness_percent, raw_source_ref, parser_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                product_row["id"],
                product_capture["captured_at"],
                product_capture["page_url"],
                product_capture["title"],
                product_capture["main_image_url"],
                product_capture["visible_price_text"],
                product_capture["shop_name"],
                product_capture["shop_rating_text"],
                product_capture["shop_positive_rate_text"],
                product_capture["shop_shipping_text"],
                product_capture["shop_refund_text"],
                product_capture["sold_text"],
                product_capture["repeat_buyer_text"],
                product_capture["cart_text"],
                product_capture["review_count_text"],
                product_capture["review_preview_text"],
                json.dumps(product_capture["services"], ensure_ascii=False),
                product_capture["attributes_text"],
                product_capture["completeness_percent"],
                product_capture["raw_source_ref"],
                1,
            ),
        )
        product_snapshot_id = product_snapshot_cursor.lastrowid
        sku_snapshot_id = None
        archive_id = None
        if validated_sku_capture is not None:
            sku_snapshot_cursor = connection.execute(
                """
                INSERT INTO sku_snapshots (
                    product_snapshot_id, captured_at, selected_options_json,
                    display_price_text, sku_price_text, price_status,
                    raw_source_ref, parser_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    product_snapshot_id,
                    validated_sku_capture["captured_at"],
                    json.dumps(
                        validated_sku_capture["selected_options"],
                        ensure_ascii=False,
                    ),
                    validated_sku_capture["display_price_text"],
                    validated_sku_capture["sku_price_text"],
                    validated_sku_capture["price_status"],
                    validated_sku_capture["raw_source_ref"],
                    1,
                ),
            )
            sku_snapshot_id = sku_snapshot_cursor.lastrowid
        if validated_archive is not None:
            archive_cursor = connection.execute(
                """
                INSERT INTO product_capture_archives (
                    product_snapshot_id, captured_at, product_fields_json,
                    images_json, sku_catalog_json, reviews_json, questions_json,
                    videos_json, coverage_json, capture_status_json,
                    raw_source_refs_json, parser_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    product_snapshot_id,
                    validated_archive["captured_at"],
                    json.dumps(validated_archive["product_fields"], ensure_ascii=False),
                    json.dumps(validated_archive["images"], ensure_ascii=False),
                    json.dumps(validated_archive["sku_catalog"], ensure_ascii=False),
                    json.dumps(validated_archive["reviews"], ensure_ascii=False),
                    json.dumps(validated_archive["questions"], ensure_ascii=False),
                    json.dumps(validated_archive["videos"], ensure_ascii=False),
                    json.dumps(validated_archive["coverage"], ensure_ascii=False),
                    json.dumps(validated_archive["capture_status"], ensure_ascii=False),
                    json.dumps(validated_archive["raw_source_refs"], ensure_ascii=False),
                    1,
                ),
            )
            archive_id = archive_cursor.lastrowid
    return {
        "product_snapshot_id": product_snapshot_id,
        "sku_snapshot_id": sku_snapshot_id,
        "product_archive_id": archive_id,
    }


def _decoded_json_list(raw_json, field_name, snapshot_id):
    try:
        decoded = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Stored {field_name} contains invalid JSON: snapshot_id={snapshot_id}"
        ) from exc
    if not isinstance(decoded, list):
        raise RuntimeError(
            f"Stored {field_name} must be a list: "
            f"snapshot_id={snapshot_id} actual={decoded!r}"
        )
    return decoded


def _decoded_json_value(raw_json, field_name, snapshot_id, expected_type):
    try:
        decoded = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Stored {field_name} contains invalid JSON: snapshot_id={snapshot_id}"
        ) from exc
    if not isinstance(decoded, expected_type):
        raise RuntimeError(
            f"Stored {field_name} must be {expected_type.__name__}: "
            f"snapshot_id={snapshot_id} actual={decoded!r}"
        )
    return decoded


def list_product_snapshots(connection, item_id):
    item_id = _required_snapshot_text("item_id", item_id)
    rows = connection.execute(
        """
        SELECT
            product_snapshots.*,
            sku_snapshots.id AS sku_snapshot_id,
            sku_snapshots.selected_options_json,
            sku_snapshots.display_price_text AS sku_display_price_text,
            sku_snapshots.sku_price_text,
            sku_snapshots.price_status,
            sku_snapshots.raw_source_ref AS sku_raw_source_ref,
            product_capture_archives.id AS product_archive_id,
            product_capture_archives.product_fields_json,
            product_capture_archives.images_json,
            product_capture_archives.sku_catalog_json,
            product_capture_archives.reviews_json,
            product_capture_archives.questions_json,
            product_capture_archives.videos_json,
            product_capture_archives.coverage_json,
            product_capture_archives.capture_status_json,
            product_capture_archives.raw_source_refs_json
        FROM product_snapshots
        JOIN products ON products.id = product_snapshots.product_id
        LEFT JOIN sku_snapshots
            ON sku_snapshots.product_snapshot_id = product_snapshots.id
        LEFT JOIN product_capture_archives
            ON product_capture_archives.product_snapshot_id = product_snapshots.id
        WHERE products.item_id = ?
        ORDER BY product_snapshots.captured_at DESC, product_snapshots.id DESC
        """,
        (item_id,),
    ).fetchall()
    snapshots = []
    for row in rows:
        snapshot = {
            "product_snapshot_id": row["id"],
            "captured_at": row["captured_at"],
            "page_url": row["page_url"],
            "title": row["title"],
            "main_image_url": row["main_image_url"],
            "visible_price_text": row["visible_price_text"],
            "shop_name": row["shop_name"],
            "shop_rating_text": row["shop_rating_text"],
            "shop_positive_rate_text": row["shop_positive_rate_text"],
            "shop_shipping_text": row["shop_shipping_text"],
            "shop_refund_text": row["shop_refund_text"],
            "sold_text": row["sold_text"],
            "repeat_buyer_text": row["repeat_buyer_text"],
            "cart_text": row["cart_text"],
            "review_count_text": row["review_count_text"],
            "review_preview_text": row["review_preview_text"],
            "services": _decoded_json_list(
                row["services_json"],
                "services_json",
                row["id"],
            ),
            "attributes_text": row["attributes_text"],
            "completeness_percent": row["completeness_percent"],
            "raw_source_ref": row["raw_source_ref"],
            "sku": None,
            "archive": None,
        }
        if row["sku_snapshot_id"] is not None:
            snapshot["sku"] = {
                "sku_snapshot_id": row["sku_snapshot_id"],
                "selected_options": _decoded_json_list(
                    row["selected_options_json"],
                    "selected_options_json",
                    row["sku_snapshot_id"],
                ),
                "display_price_text": row["sku_display_price_text"],
                "sku_price_text": row["sku_price_text"],
                "price_status": row["price_status"],
                "raw_source_ref": row["sku_raw_source_ref"],
            }
        if row["product_archive_id"] is not None:
            snapshot["archive"] = {
                "product_archive_id": row["product_archive_id"],
                "product_fields": _decoded_json_value(
                    row["product_fields_json"], "product_fields_json", row["id"], dict
                ),
                "images": _decoded_json_value(
                    row["images_json"], "images_json", row["id"], list
                ),
                "sku_catalog": _decoded_json_value(
                    row["sku_catalog_json"], "sku_catalog_json", row["id"], dict
                ),
                "reviews": _decoded_json_value(
                    row["reviews_json"], "reviews_json", row["id"], dict
                ),
                "questions": _decoded_json_value(
                    row["questions_json"], "questions_json", row["id"], dict
                ),
                "videos": _decoded_json_value(
                    row["videos_json"], "videos_json", row["id"], list
                ),
                "coverage": _decoded_json_value(
                    row["coverage_json"], "coverage_json", row["id"], dict
                ),
                "capture_status": _decoded_json_value(
                    row["capture_status_json"], "capture_status_json", row["id"], dict
                ),
                "raw_source_refs": _decoded_json_value(
                    row["raw_source_refs_json"], "raw_source_refs_json", row["id"], dict
                ),
            }
        snapshots.append(snapshot)
    return snapshots


def upsert_competitor_record(
    connection,
    *,
    item_id,
    source_url,
    resolved_url,
    captured_at,
):
    item_id = _required_snapshot_text("item_id", item_id)
    source_url = _required_snapshot_text("source_url", source_url)
    resolved_url = _required_snapshot_text("resolved_url", resolved_url)
    captured_at = _required_snapshot_text("captured_at", captured_at)
    product_row = connection.execute(
        "SELECT id FROM products WHERE item_id = ?",
        (item_id,),
    ).fetchone()
    if product_row is None:
        raise ValueError(f"competitor product must be saved before registration: item_id={item_id!r}")
    with connection:
        connection.execute(
            """
            INSERT INTO competitor_records (
                product_id, source_url, resolved_url, first_captured_at,
                last_captured_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(product_id) DO UPDATE SET
                source_url = excluded.source_url,
                resolved_url = excluded.resolved_url,
                last_captured_at = excluded.last_captured_at,
                updated_at = excluded.updated_at
            """,
            (
                product_row["id"],
                source_url,
                resolved_url,
                captured_at,
                captured_at,
                captured_at,
            ),
        )
    return get_competitor_record(connection, item_id)


def _competitor_record_from_row(row):
    if row is None:
        return None
    return {
        "id": row["id"],
        "item_id": row["item_id"],
        "source_url": row["source_url"],
        "resolved_url": row["resolved_url"],
        "first_captured_at": row["first_captured_at"],
        "last_captured_at": row["last_captured_at"],
        "snapshot_count": row["snapshot_count"],
        "title": row["title"],
        "main_image_url": row["main_image_url"],
        "visible_price_text": row["visible_price_text"],
        "shop_name": row["shop_name"],
        "sold_text": row["sold_text"],
        "review_count_text": row["review_count_text"],
        "latest_snapshot_at": row["latest_snapshot_at"],
    }


def _competitor_record_query(where_clause=""):
    return f"""
        SELECT
            cr.id,
            p.item_id,
            cr.source_url,
            cr.resolved_url,
            cr.first_captured_at,
            cr.last_captured_at,
            (
                SELECT COUNT(*) FROM product_snapshots counted
                WHERE counted.product_id = p.id
            ) AS snapshot_count,
            latest.title,
            latest.main_image_url,
            latest.visible_price_text,
            latest.shop_name,
            latest.sold_text,
            latest.review_count_text,
            latest.captured_at AS latest_snapshot_at
        FROM competitor_records cr
        JOIN products p ON p.id = cr.product_id
        LEFT JOIN product_snapshots latest ON latest.id = (
            SELECT ps.id FROM product_snapshots ps
            WHERE ps.product_id = p.id
            ORDER BY ps.captured_at DESC, ps.id DESC
            LIMIT 1
        )
        {where_clause}
    """


def list_competitor_records(connection):
    rows = connection.execute(
        _competitor_record_query() + " ORDER BY cr.last_captured_at DESC, cr.id DESC"
    ).fetchall()
    return [_competitor_record_from_row(row) for row in rows]


def get_competitor_record(connection, item_id):
    item_id = _required_snapshot_text("item_id", item_id)
    row = connection.execute(
        _competitor_record_query("WHERE p.item_id = ?"),
        (item_id,),
    ).fetchone()
    return _competitor_record_from_row(row)


def delete_competitor_record(connection, item_id):
    item_id = _required_snapshot_text("item_id", item_id)
    with connection:
        connection.execute(
            "DELETE FROM monitor_tasks WHERE task_type = 'competitor' AND item_id = ?",
            (item_id,),
        )
        cursor = connection.execute(
            """
            DELETE FROM competitor_records
            WHERE product_id = (SELECT id FROM products WHERE item_id = ?)
            """,
            (item_id,),
        )
    return cursor.rowcount > 0


def read_monitor_settings(connection):
    row = connection.execute(
        "SELECT enabled, run_time, updated_at FROM monitor_settings WHERE id = 1"
    ).fetchone()
    if row is None:
        raise RuntimeError("monitor settings row is missing")
    return {
        "enabled": bool(row["enabled"]),
        "run_time": row["run_time"],
        "updated_at": row["updated_at"],
    }


def save_monitor_settings(connection, *, enabled, run_time, updated_at):
    if not isinstance(enabled, bool):
        raise ValueError(f"enabled must be bool: actual={enabled!r}")
    if (
        not isinstance(run_time, str)
        or len(run_time) != 5
        or run_time[2] != ":"
        or not run_time[:2].isdigit()
        or not run_time[3:].isdigit()
        or int(run_time[:2]) > 23
        or int(run_time[3:]) > 59
    ):
        raise ValueError(f"run_time must use HH:MM: actual={run_time!r}")
    connection.execute(
        """
        UPDATE monitor_settings
        SET enabled = ?, run_time = ?, updated_at = ?
        WHERE id = 1
        """,
        (int(enabled), run_time, updated_at),
    )
    connection.commit()
    return read_monitor_settings(connection)


def upsert_monitor_task(
    connection,
    *,
    task_type,
    target_key,
    project_id,
    label,
    created_at,
    item_id=None,
    product_url=None,
    shop_url=None,
    shop_name=None,
    page_count=1,
):
    if task_type not in ("keyword", "competitor", "shop"):
        raise ValueError(f"unsupported monitor task_type={task_type!r}")
    if task_type in ("keyword", "shop") and project_id is None:
        raise ValueError(f"project_id is required for monitor task_type={task_type!r}")
    if not isinstance(page_count, int) or isinstance(page_count, bool) or page_count not in (1, 2, 3):
        raise ValueError(f"page_count must be 1, 2, or 3: actual={page_count!r}")
    connection.execute(
        """
        INSERT INTO monitor_tasks (
            task_type, target_key, project_id, item_id, product_url, shop_url, shop_name,
            label, enabled, created_at, updated_at, page_count
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
        ON CONFLICT(task_type, target_key) DO UPDATE SET
            project_id = excluded.project_id,
            item_id = excluded.item_id,
            product_url = excluded.product_url,
            shop_url = excluded.shop_url,
            shop_name = excluded.shop_name,
            label = excluded.label,
            page_count = excluded.page_count,
            enabled = 1,
            updated_at = excluded.updated_at
        """,
        (
            task_type,
            target_key,
            project_id,
            item_id,
            product_url,
            shop_url,
            shop_name,
            label,
            created_at,
            created_at,
            page_count,
        ),
    )
    connection.commit()
    return connection.execute(
        "SELECT * FROM monitor_tasks WHERE task_type = ? AND target_key = ?",
        (task_type, target_key),
    ).fetchone()


def list_monitor_tasks(connection, *, enabled_only=False):
    where_clause = "WHERE monitor_tasks.enabled = 1" if enabled_only else ""
    rows = connection.execute(
        f"""
        SELECT
            monitor_tasks.*,
            market_projects.keyword AS keyword
        FROM monitor_tasks
        LEFT JOIN market_projects ON market_projects.id = monitor_tasks.project_id
        {where_clause}
        ORDER BY monitor_tasks.task_type, monitor_tasks.id
        """
    ).fetchall()
    tasks = []
    for row in rows:
        task = {
            "id": row["id"],
            "task_type": row["task_type"],
            "project_id": row["project_id"],
            "keyword": row["keyword"],
            "item_id": row["item_id"],
            "product_url": row["product_url"],
            "shop_url": row["shop_url"],
            "shop_name": row["shop_name"],
            "label": row["label"],
            "enabled": bool(row["enabled"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "page_count": row["page_count"],
        }
        if row["task_type"] == "competitor":
            evidence = connection.execute(
                """
                SELECT ps.main_image_url AS image_url, ps.shop_name,
                       ps.visible_price_text AS price_text, ps.sold_text AS payment_text,
                       ps.captured_at
                FROM product_snapshots ps
                JOIN products p ON p.id = ps.product_id
                WHERE p.item_id = ?
                ORDER BY ps.captured_at DESC, ps.id DESC LIMIT 1
                """,
                (row["item_id"],),
            ).fetchone()
            if evidence is None:
                evidence = connection.execute(
                    """
                    SELECT sr.image_url, sr.shop_name, sr.display_price AS price_text,
                           sr.payment_text, ss.captured_at
                    FROM search_results sr
                    JOIN products p ON p.id = sr.product_id
                    JOIN search_snapshots ss ON ss.id = sr.snapshot_id
                    WHERE p.item_id = ? AND ss.project_id = ?
                    ORDER BY ss.captured_at DESC, sr.id DESC LIMIT 1
                    """,
                    (row["item_id"], row["project_id"]),
                ).fetchone()
            if evidence is not None:
                task.update(dict(evidence))
        elif row["task_type"] == "shop":
            snapshot_rows = connection.execute(
                """
                SELECT id, shop_name, result_count, captured_at
                FROM shop_snapshots WHERE monitor_task_id = ?
                ORDER BY captured_at DESC, id DESC LIMIT 2
                """,
                (row["id"],),
            ).fetchall()
            if snapshot_rows:
                task.update(dict(snapshot_rows[0]))
                preview_rows = connection.execute(
                    """
                    SELECT item_id, title, product_url, image_url, price_text, payment_text
                    FROM shop_snapshot_items
                    WHERE shop_snapshot_id = ?
                    ORDER BY display_rank LIMIT 4
                    """,
                    (snapshot_rows[0]["id"],),
                ).fetchall()
                task["preview_products"] = [dict(item) for item in preview_rows]
            else:
                task["preview_products"] = []
            task["recent_new_products"] = []
            task["recent_new_count"] = 0
            if len(snapshot_rows) > 1:
                new_rows = connection.execute(
                    """
                    SELECT current_items.item_id, current_items.title,
                           current_items.product_url, current_items.image_url,
                           current_items.price_text, current_items.payment_text
                    FROM shop_snapshot_items current_items
                    LEFT JOIN shop_snapshot_items previous_items
                      ON previous_items.shop_snapshot_id = ?
                     AND previous_items.item_id = current_items.item_id
                    WHERE current_items.shop_snapshot_id = ?
                      AND previous_items.id IS NULL
                    ORDER BY current_items.display_rank
                    """,
                    (snapshot_rows[1]["id"], snapshot_rows[0]["id"]),
                ).fetchall()
                task["recent_new_count"] = len(new_rows)
                task["recent_new_products"] = [dict(item) for item in new_rows[:3]]
        tasks.append(task)
    return tasks


def save_shop_snapshot(connection, *, monitor_task_id, captured_at, shop_url, shop_name, raw_source_ref, products):
    products = [item for item in (products or []) if isinstance(item, dict) and str(item.get("item_id") or "").strip()]
    cursor = connection.execute(
        """
        INSERT INTO shop_snapshots (
            monitor_task_id, captured_at, shop_url, shop_name, raw_source_ref, result_count
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (monitor_task_id, captured_at, shop_url, shop_name, raw_source_ref, len(products)),
    )
    snapshot_id = cursor.lastrowid
    connection.executemany(
        """
        INSERT INTO shop_snapshot_items (
            shop_snapshot_id, item_id, title, product_url, image_url,
            price_text, payment_text, display_rank
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                snapshot_id, str(item["item_id"]), item.get("title"), item.get("product_url"),
                item.get("image_url"), item.get("price_text"), item.get("payment_text"), index,
            )
            for index, item in enumerate(products, start=1)
        ],
    )
    connection.commit()
    return snapshot_id


def list_shop_snapshots(connection, monitor_task_id, *, limit=3):
    rows = connection.execute(
        """
        SELECT * FROM shop_snapshots WHERE monitor_task_id = ?
        ORDER BY captured_at DESC, id DESC LIMIT ?
        """,
        (monitor_task_id, limit),
    ).fetchall()
    snapshots = []
    for row in rows:
        items = connection.execute(
            "SELECT * FROM shop_snapshot_items WHERE shop_snapshot_id = ? ORDER BY display_rank",
            (row["id"],),
        ).fetchall()
        snapshots.append({
            "shop_snapshot_id": row["id"],
            "captured_at": row["captured_at"],
            "shop_url": row["shop_url"],
            "shop_name": row["shop_name"],
            "raw_source_ref": row["raw_source_ref"],
            "result_count": row["result_count"],
            "products": [dict(item) for item in items],
        })
    return snapshots


def delete_monitor_task(connection, task_id):
    cursor = connection.execute("DELETE FROM monitor_tasks WHERE id = ?", (task_id,))
    connection.commit()
    return cursor.rowcount > 0


def start_monitor_run(connection, *, started_at, task_count):
    cursor = connection.execute(
        """
        INSERT INTO monitor_runs (started_at, status, task_count)
        VALUES (?, 'running', ?)
        """,
        (started_at, task_count),
    )
    connection.commit()
    return cursor.lastrowid


def finish_monitor_run(
    connection,
    run_id,
    *,
    finished_at,
    status,
    success_count,
    failure_count,
    summary,
    error_text=None,
):
    if status not in ("success", "partial", "failed", "skipped"):
        raise ValueError(f"invalid monitor run status={status!r}")
    connection.execute(
        """
        UPDATE monitor_runs
        SET finished_at = ?, status = ?, success_count = ?, failure_count = ?,
            summary_json = ?, error_text = ?
        WHERE id = ?
        """,
        (
            finished_at,
            status,
            success_count,
            failure_count,
            json.dumps(summary, ensure_ascii=False),
            error_text,
            run_id,
        ),
    )
    connection.commit()


def list_monitor_runs(connection, *, limit=10):
    rows = connection.execute(
        """
        SELECT * FROM monitor_runs
        ORDER BY started_at DESC, id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [
        {
            "id": row["id"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
            "status": row["status"],
            "task_count": row["task_count"],
            "success_count": row["success_count"],
            "failure_count": row["failure_count"],
            "summary": json.loads(row["summary_json"]),
            "error_text": row["error_text"],
        }
        for row in rows
    ]
