from contextlib import closing
from io import BytesIO
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from openpyxl import load_workbook
from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import application
from src.database import connect_database, read_search_snapshot, save_search_snapshot
from src.reports import export_search_snapshot_xlsx


def png_bytes():
    output = BytesIO()
    Image.new("RGB", (120, 120), "#e87932").save(output, format="PNG")
    return output.getvalue()


class XlsxExportTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = TemporaryDirectory()
        self.application_data_directory = Path(self.temporary_directory.name)
        with closing(connect_database(self.application_data_directory)) as connection:
            cursor = connection.execute(
                "INSERT INTO market_projects (keyword, normalized_keyword) VALUES (?, ?)",
                ("苹果15手机壳", "苹果15手机壳"),
            )
            connection.commit()
            self.project_id = cursor.lastrowid
            self.snapshot_id = save_search_snapshot(
                connection,
                self.project_id,
                "苹果15手机壳",
                "all",
                10,
                "2026-08-06T12:00:00+08:00",
                "raw/search.json",
                [{
                    "item_id": "739189137255",
                    "sku_id": "5102288369848",
                    "title": "适用苹果15手机壳透明防摔款",
                    "shop_name": "佰蓝旗舰店",
                    "display_price": "8.9",
                    "product_url": "https://detail.tmall.com/item.htm?id=739189137255",
                    "shop_url": "https://store.taobao.com/example-one",
                    "image_url": "https://img.alicdn.com/739189137255.jpg",
                    "platform_type": "tmall",
                    "suspected_ad": None,
                    "payment_text": "6000+人付款",
                    "origin_text": "浙江 杭州",
                    "promotion_text": "补贴后·官方立减4.8",
                    "logistics_text": "次日达",
                }],
            )

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_export_embeds_thumbnail_and_keeps_market_tags_as_filterable_columns(self):
        output_path = self.application_data_directory / "exports" / "snapshot.xlsx"
        with closing(connect_database(self.application_data_directory)) as connection:
            snapshot = read_search_snapshot(connection, self.snapshot_id, self.project_id)

        export_search_snapshot_xlsx(
            "苹果15手机壳",
            snapshot,
            output_path,
            image_fetcher=lambda _url: (png_bytes(), "image/png"),
        )

        workbook = load_workbook(output_path, data_only=False)
        worksheet = workbook["商品数据"]
        self.assertEqual("关键词市场搜索快照", worksheet["A1"].value)
        self.assertEqual(
            ["排名", "主图", "标题", "店铺", "展示价", "付款人数", "地区", "优惠标签", "物流/服务", "平台", "抓取时间"],
            [worksheet.cell(8, column).value for column in range(1, 12)],
        )
        self.assertEqual(1, worksheet["A9"].value)
        self.assertEqual("适用苹果15手机壳透明防摔款", worksheet["C9"].value)
        self.assertEqual("6000+人付款", worksheet["F9"].value)
        self.assertEqual("浙江 杭州", worksheet["G9"].value)
        self.assertEqual("补贴后·官方立减4.8", worksheet["H9"].value)
        self.assertEqual("次日达", worksheet["I9"].value)
        self.assertEqual(worksheet["C9"].hyperlink.target, "https://detail.tmall.com/item.htm?id=739189137255")
        self.assertEqual(1, len(worksheet._images))
        self.assertEqual("A8:K9", worksheet.auto_filter.ref)
        self.assertEqual("A9", worksheet.freeze_panes)
        workbook.close()

    def test_empty_snapshot_is_rejected(self):
        with closing(connect_database(self.application_data_directory)) as connection:
            empty_id = save_search_snapshot(connection, self.project_id, "苹果15手机壳", "all", 10, "2026-08-06T13:00:00+08:00", "raw/empty.json", [])
            snapshot = read_search_snapshot(connection, empty_id, self.project_id)
        with self.assertRaisesRegex(ValueError, f"snapshot_id={empty_id}"):
            export_search_snapshot_xlsx("苹果15手机壳", snapshot, self.application_data_directory / "empty.xlsx")

    def test_export_api_returns_reopenable_xlsx(self):
        previous = application.state.application_data_directory
        application.state.application_data_directory = self.application_data_directory
        try:
            with patch("app.fetch_product_image_payload", return_value=(png_bytes(), "image/png")):
                with TestClient(application) as client:
                    response = client.get(f"/api/projects/{self.project_id}/searches/{self.snapshot_id}/export.xlsx")
        finally:
            application.state.application_data_directory = previous
        self.assertEqual(200, response.status_code)
        workbook = load_workbook(BytesIO(response.content), read_only=False)
        self.assertEqual("6000+人付款", workbook["商品数据"]["F9"].value)
        self.assertEqual(1, len(workbook["商品数据"]._images))
        workbook.close()

    def test_homepage_only_exposes_data_export(self):
        with TestClient(application) as client:
            homepage = client.get("/")
            script = client.get("/static/app.js")
        self.assertIn('id="export-snapshot"', homepage.text)
        self.assertNotIn("导出市场报告", homepage.text)
        self.assertIn("export.xlsx", script.text)


if __name__ == "__main__":
    unittest.main()
