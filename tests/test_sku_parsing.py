import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.competitor_analysis import parse_sku_dimensions
from src.collector import scan_product_sku_dimensions


FIXTURE_PATH = PROJECT_ROOT / "tests" / "fixtures" / "product_sku_elements.json"


class SkuParsingTests(unittest.TestCase):
    @patch("src.collector.subprocess.run")
    def test_runtime_scan_uses_current_page_and_preserves_raw_result(self, run_command):
        with TemporaryDirectory() as directory:
            temporary_root = Path(directory)
            command_path = temporary_root / "taobao-native.cmd"
            command_path.write_text("@echo off\n", encoding="ascii")
            result_path = temporary_root / "raw" / "sku-dimensions.json"

            def write_result(command, **arguments):
                request_path = Path(command[command.index("--request") + 1])
                output_path = Path(command[command.index("-o") + 1])
                request = json.loads(request_path.read_text(encoding="utf-8"))
                self.assertEqual("scan_page_elements", request["tool"])
                self.assertEqual(
                    "taobao-market-intelligence",
                    request["arguments"]["sourceApp"],
                )
                self.assertNotIn("filter", request["arguments"])
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(FIXTURE_PATH.read_bytes())
                return subprocess.CompletedProcess(command, 0, "saved", "")

            run_command.side_effect = write_result
            parsed = scan_product_sku_dimensions(
                temporary_root / "requests",
                result_path,
                command_path=command_path,
            )

        self.assertEqual(["适用手机型号", "颜色分类"], [item["label"] for item in parsed["dimensions"]])
        self.assertEqual(str(result_path), parsed["raw_source_ref"])

    def test_extracts_dimensions_with_first_exact_index_and_raw_text(self):
        response = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

        parsed = parse_sku_dimensions(response, FIXTURE_PATH)

        self.assertEqual(139, parsed["total_elements"])
        self.assertEqual(
            ["适用手机型号", "颜色分类"],
            [dimension["label"] for dimension in parsed["dimensions"]],
        )
        self.assertEqual(
            [
                {"value": "iPhone 15", "index": 96, "raw_text": "iPhone 15"},
                {"value": "iPhone 15 Pro", "index": 100, "raw_text": "iPhone 15 Pro"},
            ],
            parsed["dimensions"][0]["options"],
        )
        self.assertEqual(
            [
                {
                    "value": "旗舰款【石墨黑】送钢化膜",
                    "index": 115,
                    "raw_text": "旗舰款【石墨黑】送钢化膜近期热销",
                },
                {
                    "value": "旗舰款【远峰蓝】送钢化膜",
                    "index": 123,
                    "raw_text": "旗舰款【远峰蓝】送钢化膜",
                },
            ],
            parsed["dimensions"][1]["options"],
        )

    def test_discards_empty_and_standalone_promotional_nodes(self):
        response = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

        parsed = parse_sku_dimensions(response, FIXTURE_PATH)
        all_values = [
            option["value"]
            for dimension in parsed["dimensions"]
            for option in dimension["options"]
        ]

        self.assertNotIn("", all_values)
        self.assertNotIn("推荐", all_values)
        self.assertNotIn("近期热销", all_values)
        self.assertEqual(len(all_values), len(set(all_values)))

    def test_rejects_invalid_response_and_conflicting_duplicate_index(self):
        invalid_responses = (
            ({"result": {"dom": [], "totalElements": 1}}, "dom"),
            ({"result": {"dom": "颜色分类", "totalElements": -1}}, "totalElements"),
            (
                {
                    "result": {
                        "dom": (
                            "颜色分类\n"
                            "[10] <span>黑色</span>\n"
                            "[10] <span>白色</span>\n"
                            "[20] <button><span>加入购物车</span></button>"
                        ),
                        "totalElements": 21,
                    }
                },
                "duplicate element index.*10",
            ),
        )
        for response, expected_message in invalid_responses:
            with self.subTest(expected_message=expected_message):
                with self.assertRaisesRegex(ValueError, expected_message):
                    parse_sku_dimensions(response, FIXTURE_PATH)

    def test_valid_scan_without_sku_dimensions_returns_explicit_empty_list(self):
        response = {
            "result": {
                "dom": "[1] <span>商品标题</span>\n[2] <button>立即购买</button>",
                "totalElements": 3,
            }
        }

        parsed = parse_sku_dimensions(response, FIXTURE_PATH)

        self.assertEqual([], parsed["dimensions"])


if __name__ == "__main__":
    unittest.main()
