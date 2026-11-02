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

from src.collector import capture_selected_sku_price
from src.competitor_analysis import parse_sku_price_scan


def selected_options():
    return [
        {"dimension": "适用手机型号", "value": "iPhone 15", "index": 96},
        {
            "dimension": "颜色分类",
            "value": "旗舰款【石墨黑】进口材质★强抗指纹★送钢化膜",
            "index": 115,
        },
    ]


class SkuPriceCaptureTests(unittest.TestCase):
    def test_parses_one_refreshed_price_and_rejects_ambiguous_prices(self):
        single_price = parse_sku_price_scan(
            {"result": {"dom": "优惠促销\n￥\n8.9", "totalElements": 170}},
            "price.json",
        )
        self.assertEqual(
            {
                "sku_price_text": "8.9",
                "price_status": "captured",
                "raw_price_evidence": "优惠促销\n￥\n8.9",
            },
            single_price,
        )

        ambiguous_price = parse_sku_price_scan(
            {"result": {"dom": "活动价 ￥8.9\n划线价 ￥19.9", "totalElements": 170}},
            "price.json",
        )
        self.assertIsNone(ambiguous_price["sku_price_text"])
        self.assertEqual("ambiguous_after_refresh", ambiguous_price["price_status"])

    @patch("src.collector.time.sleep")
    @patch("src.collector.subprocess.run")
    def test_clicks_each_dimension_by_index_then_waits_three_seconds_and_scans_price(
        self,
        run_command,
        sleep,
    ):
        with TemporaryDirectory() as directory:
            temporary_root = Path(directory)
            command_path = temporary_root / "taobao-native.cmd"
            command_path.write_text("@echo off\n", encoding="ascii")
            request_directory = temporary_root / "sku-requests"
            price_result_path = temporary_root / "raw" / "sku-price.json"
            call_order = []

            def write_command_result(command, **arguments):
                request_path = Path(command[command.index("--request") + 1])
                output_path = Path(command[command.index("-o") + 1])
                output_path.parent.mkdir(parents=True, exist_ok=True)
                request_payload = json.loads(request_path.read_text(encoding="utf-8"))
                if request_payload["tool"] == "click_element":
                    element_index = request_payload["arguments"]["index"]
                    call_order.append(f"click:{element_index}")
                    output_path.write_text(
                        json.dumps(
                            {
                                "result": {
                                    "success": True,
                                    "clicked": f"option-{element_index}",
                                    "index": element_index,
                                }
                            }
                        ),
                        encoding="utf-8",
                    )
                else:
                    call_order.append("scan-price")
                    output_path.write_text(
                        json.dumps(
                            {
                                "result": {
                                    "dom": "优惠促销\n￥\n8.9",
                                    "totalElements": 170,
                                }
                            }
                        ),
                        encoding="utf-8",
                    )
                return subprocess.CompletedProcess(command, 0, "saved", "")

            def record_sleep(seconds):
                call_order.append(f"sleep:{seconds}")

            run_command.side_effect = write_command_result
            sleep.side_effect = record_sleep

            captured_price = capture_selected_sku_price(
                selected_options(),
                "8.9起",
                request_directory,
                price_result_path,
                command_path=command_path,
            )

            self.assertEqual(
                ["click:96", "click:115", "sleep:3.0", "scan-price"],
                call_order,
            )
            sleep.assert_called_once_with(3.0)
            self.assertEqual("8.9起", captured_price["display_price_text"])
            self.assertEqual("8.9", captured_price["sku_price_text"])
            self.assertEqual("captured", captured_price["price_status"])
            self.assertEqual(selected_options(), captured_price["selected_options"])

            for request_path in sorted(request_directory.glob("click-sku-*.json")):
                request_payload = json.loads(request_path.read_text(encoding="utf-8"))
                arguments = request_payload["arguments"]
                self.assertIn("index", arguments)
                self.assertNotIn("text", arguments)
                self.assertEqual(
                    "taobao-market-intelligence",
                    arguments["sourceApp"],
                )
            price_request = json.loads(
                (request_directory / "scan-sku-price.json").read_text(encoding="utf-8")
            )
            self.assertEqual("scan_page_elements", price_request["tool"])
            self.assertEqual("￥", price_request["arguments"]["filter"])

    @patch("src.collector.time.sleep")
    @patch("src.collector.subprocess.run")
    def test_missing_refreshed_price_never_falls_back_to_display_price(
        self,
        run_command,
        sleep,
    ):
        with TemporaryDirectory() as directory:
            temporary_root = Path(directory)
            command_path = temporary_root / "taobao-native.cmd"
            command_path.write_text("@echo off\n", encoding="ascii")

            def write_command_result(command, **arguments):
                request_path = Path(command[command.index("--request") + 1])
                output_path = Path(command[command.index("-o") + 1])
                output_path.parent.mkdir(parents=True, exist_ok=True)
                request_payload = json.loads(request_path.read_text(encoding="utf-8"))
                if request_payload["tool"] == "click_element":
                    element_index = request_payload["arguments"]["index"]
                    payload = {
                        "result": {
                            "success": True,
                            "clicked": "option",
                            "index": element_index,
                        }
                    }
                else:
                    payload = {"result": {"dom": "价格尚未刷新", "totalElements": 170}}
                output_path.write_text(json.dumps(payload), encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, "saved", "")

            run_command.side_effect = write_command_result

            captured_price = capture_selected_sku_price(
                [selected_options()[0]],
                "99起",
                temporary_root / "requests",
                temporary_root / "price.json",
                command_path=command_path,
            )

        self.assertEqual("99起", captured_price["display_price_text"])
        self.assertIsNone(captured_price["sku_price_text"])
        self.assertEqual("missing_after_refresh", captured_price["price_status"])
        sleep.assert_called_once_with(3.0)

    @patch("src.collector.subprocess.run")
    def test_invalid_selection_or_failed_click_stops_before_price_scan(self, run_command):
        invalid_selections = (
            [],
            [{"dimension": "颜色", "value": "黑色", "index": "115"}],
            [
                {"dimension": "颜色", "value": "黑色", "index": 115},
                {"dimension": "颜色", "value": "白色", "index": 119},
            ],
        )
        for selections in invalid_selections:
            with self.subTest(selections=selections):
                with self.assertRaises(ValueError):
                    capture_selected_sku_price(
                        selections,
                        "8.9起",
                        "requests",
                        "price.json",
                        command_path=PROJECT_ROOT / "missing-command.cmd",
                    )
        run_command.assert_not_called()

        with TemporaryDirectory() as directory:
            temporary_root = Path(directory)
            command_path = temporary_root / "taobao-native.cmd"
            command_path.write_text("@echo off\n", encoding="ascii")

            def write_failed_click(command, **arguments):
                output_path = Path(command[command.index("-o") + 1])
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(
                    json.dumps(
                        {
                            "result": {
                                "success": False,
                                "disabled": True,
                                "index": 96,
                            }
                        }
                    ),
                    encoding="utf-8",
                )
                return subprocess.CompletedProcess(command, 0, "saved", "")

            run_command.side_effect = write_failed_click
            with self.assertRaisesRegex(RuntimeError, "disabled.*index=96"):
                capture_selected_sku_price(
                    [selected_options()[0]],
                    "8.9起",
                    temporary_root / "requests",
                    temporary_root / "price.json",
                    command_path=command_path,
                )

        self.assertEqual(1, run_command.call_count)


if __name__ == "__main__":
    unittest.main()
