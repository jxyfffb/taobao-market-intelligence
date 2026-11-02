from io import BytesIO
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from fastapi.testclient import TestClient
from openpyxl import load_workbook
from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import application
from src.reports import export_competitor_package_zip


def png_bytes(color="#214d37"):
    output = BytesIO()
    Image.new("RGB", (160, 120), color).save(output, format="PNG")
    return output.getvalue()


def saved_snapshot():
    return {
        "product_snapshot_id": 8,
        "captured_at": "2026-08-14T10:00:00+08:00",
        "page_url": "https://item.taobao.com/item.htm?id=739189137255",
        "title": "男士纯棉短袖",
        "main_image_url": "https://img.alicdn.com/main.png",
        "visible_price_text": "68",
        "shop_name": "品牌旗舰店",
        "shop_rating_text": "4.9",
        "shop_positive_rate_text": "98%",
        "shop_shipping_text": "48小时内发",
        "shop_refund_text": "极速退款",
        "sold_text": "7000+人付款",
        "repeat_buyer_text": "回头客500+",
        "cart_text": "1000+人加购",
        "review_count_text": "200条评价",
        "review_preview_text": "面料舒服",
        "services": ["退货宝"],
        "attributes_text": "材质 纯棉",
        "completeness_percent": 100,
        "raw_source_ref": "raw/detail.json",
        "sku": {
            "selected_options": [{"dimension": "颜色", "value": "白色"}],
            "display_price_text": "68",
            "sku_price_text": "69",
            "price_status": "captured",
            "raw_source_ref": "raw/sku.json",
        },
        "archive": {
            "product_fields": {
                "price_text": "68",
                "payment_text": "7000+人付款",
                "origin_text": "江苏 无锡",
                "promotions": ["补贴后"],
                "services": ["次日达"],
                "attributes_text": "材质 纯棉",
            },
            "images": [
                {"url": "https://img.alicdn.com/main.png", "kind": "main", "source": "gallery"},
                {"url": "https://img.alicdn.com/sku.png", "kind": "sku", "source": "sku"},
                {"url": "https://img.alicdn.com/detail.png", "kind": "detail", "source": "detail"},
            ],
            "sku_catalog": {
                "dimensions": [{"label": "颜色", "options": [{"value": "白色", "value_id": "1", "available": True, "image_url": "https://img.alicdn.com/sku.png"}]}]
            },
            "reviews": {
                "total_text": "200条评价",
                "tags": ["面料舒服"],
                "items": [{"content": "面料舒服，尺码合适", "sku": "白色 L", "date": "2026-08-01", "images": ["https://img.alicdn.com/review.png"]}],
            },
            "questions": {"items": [{"question": "会不会透？", "answer_count": "3个回答", "answers": ["白色略透"]}]},
            "videos": [],
            "coverage": {"images": "captured", "reviews": "captured"},
            "capture_status": {"browser": "success"},
            "raw_source_refs": {"browser": "raw/browser.json"},
        },
    }


class CompetitorPackageTests(unittest.TestCase):
    def test_zip_contains_workbook_original_images_and_lossless_json(self):
        with TemporaryDirectory() as directory:
            output = Path(directory) / "competitor.zip"
            export_competitor_package_zip(
                "739189137255",
                saved_snapshot(),
                output,
                image_fetcher=lambda _url: (png_bytes(), "image/png"),
            )
            with ZipFile(output) as archive:
                names = set(archive.namelist())
                self.assertIn("商品信息.xlsx", names)
                self.assertIn("评价与问大家.xlsx", names)
                self.assertIn("原始数据.json", names)
                self.assertIn("主图/主图-001.png", names)
                self.assertIn("SKU图/SKU图-001.png", names)
                self.assertIn("详情图/详情图-001.png", names)
                self.assertIn("评价图/评价图-001.png", names)
                payload = json.loads(archive.read("原始数据.json"))
                self.assertEqual("739189137255", payload["item_id"])
                workbook = load_workbook(BytesIO(archive.read("商品信息.xlsx")))
                self.assertEqual(
                    ["商品概览", "图片目录", "SKU数据", "采集说明"],
                    workbook.sheetnames,
                )
                self.assertEqual("7000+人付款", workbook["商品概览"]["B6"].value)
                self.assertEqual(4, len(workbook["图片目录"]._images))
                workbook.close()
                review_workbook = load_workbook(BytesIO(archive.read("评价与问大家.xlsx")))
                self.assertEqual(["评价与问大家"], review_workbook.sheetnames)
                review_workbook.close()

    def test_export_api_returns_zip_and_frontend_has_one_export_action(self):
        with TemporaryDirectory() as directory:
            with patch(
                "app._saved_competitor_snapshot",
                return_value=(Path(directory), saved_snapshot()),
            ):
                with patch("app.fetch_product_image_payload", return_value=(png_bytes(), "image/png")):
                    with TestClient(application) as client:
                        response = client.get("/api/projects/1/competitors/739189137255/export.zip")
                        independent_response = client.get("/api/competitors/739189137255/export.zip")
                        homepage = client.get("/")
                        script = client.get("/static/app.js")
        self.assertEqual(200, response.status_code)
        self.assertEqual(200, independent_response.status_code)
        self.assertEqual("application/zip", response.headers["content-type"])
        self.assertEqual("application/zip", independent_response.headers["content-type"])
        self.assertIn('id="export-competitor-package"', homepage.text)
        self.assertIn("export.zip", script.text)
        self.assertNotIn("导出竞品分析报告", homepage.text)

    def test_export_removes_excel_illegal_characters_but_preserves_raw_json(self):
        snapshot = saved_snapshot()
        snapshot["archive"]["reviews"]["items"][0]["content"] = "符合预期\x02满意\x01"
        snapshot["archive"]["questions"]["items"][0]["question"] = "会不会\x0b透？"
        with TemporaryDirectory() as directory:
            output = Path(directory) / "competitor.zip"
            export_competitor_package_zip(
                "739189137255",
                snapshot,
                output,
                image_fetcher=lambda _url: (png_bytes(), "image/png"),
            )
            with ZipFile(output) as archive:
                review_workbook = load_workbook(BytesIO(archive.read("评价与问大家.xlsx")))
                review_sheet = review_workbook["评价与问大家"]
                self.assertEqual("符合预期满意", review_sheet["C2"].value)
                self.assertEqual("会不会透？", review_sheet["C3"].value)
                review_workbook.close()
                payload = json.loads(archive.read("原始数据.json"))
                self.assertEqual(
                    "符合预期\x02满意\x01",
                    payload["exported_snapshot"]["archive"]["reviews"]["items"][0]["content"],
                )


if __name__ == "__main__":
    unittest.main()
