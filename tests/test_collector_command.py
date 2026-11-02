import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

FIXTURE_PATH = PROJECT_ROOT / "tests" / "fixtures" / "search_products_response.json"

from src.collector import resolve_taobao_native_command, run_search_products


class CollectorCommandTests(unittest.TestCase):
    def test_resolves_utf8_install_location(self):
        with TemporaryDirectory() as directory:
            temporary_root = Path(directory)
            install_root = temporary_root / "淘宝桌面版" / "taobao"
            command_path = install_root / "bin" / "taobao-native.cmd"
            command_path.parent.mkdir(parents=True)
            command_path.write_text("@echo off\n", encoding="ascii")
            location_file = temporary_root / "install-location.txt"
            location_file.write_text(str(install_root), encoding="utf-8")

            resolved_command = resolve_taobao_native_command(location_file)

            self.assertEqual(command_path, resolved_command)

    def test_resolves_current_gbk_install_location_format(self):
        with TemporaryDirectory() as directory:
            temporary_root = Path(directory)
            install_root = temporary_root / "淘宝桌面版" / "taobao"
            command_path = install_root / "bin" / "taobao-native.cmd"
            command_path.parent.mkdir(parents=True)
            command_path.write_text("@echo off\n", encoding="ascii")
            location_file = temporary_root / "install-location.txt"
            location_file.write_bytes(str(install_root).encode("gb18030"))

            resolved_command = resolve_taobao_native_command(location_file)

            self.assertEqual(command_path, resolved_command)

    def test_missing_command_fails_with_received_path(self):
        with TemporaryDirectory() as directory:
            temporary_root = Path(directory)
            install_root = temporary_root / "missing-install"
            location_file = temporary_root / "install-location.txt"
            location_file.write_text(str(install_root), encoding="utf-8")
            expected_command = install_root / "bin" / "taobao-native.cmd"

            with self.assertRaisesRegex(FileNotFoundError, str(expected_command).replace("\\", "\\\\")):
                resolve_taobao_native_command(location_file)

    @patch("src.collector.subprocess.run")
    def test_search_uses_utf8_request_output_file_and_fixed_source_app(self, run_command):
        with TemporaryDirectory() as directory:
            temporary_root = Path(directory)
            command_path = temporary_root / "taobao-native.cmd"
            command_path.write_text("@echo off\n", encoding="ascii")
            request_path = temporary_root / "搜索请求.json"
            result_path = temporary_root / "搜索结果.json"

            def write_fixture(command, **arguments):
                result_path.write_bytes(FIXTURE_PATH.read_bytes())
                return subprocess.CompletedProcess(command, 0, "saved", "")

            run_command.side_effect = write_fixture

            response = run_search_products(
                "苹果15手机壳",
                request_path,
                result_path,
                command_path=command_path,
            )

            self.assertEqual(2, response["result"]["count"])
            command = run_command.call_args.args[0]
            self.assertEqual(
                [str(command_path), "--request", str(request_path), "-o", str(result_path)],
                command,
            )
            self.assertNotIn("--args", command)
            request_bytes = request_path.read_bytes()
            self.assertNotEqual(b"\xef\xbb\xbf", request_bytes[:3])
            request_payload = json.loads(request_bytes.decode("utf-8"))
            self.assertEqual("search_products", request_payload["tool"])
            self.assertEqual("苹果15手机壳", request_payload["arguments"]["keyword"])
            self.assertEqual(
                "taobao-market-intelligence",
                request_payload["arguments"]["sourceApp"],
            )
            self.assertEqual("utf-8", run_command.call_args.kwargs["encoding"])

    @patch("src.collector.subprocess.run")
    def test_nonzero_exit_fails_with_exit_code_and_stderr(self, run_command):
        run_command.return_value = subprocess.CompletedProcess(
            ["taobao-native.cmd"],
            9,
            "",
            "需要登录",
        )
        with TemporaryDirectory() as directory:
            temporary_root = Path(directory)
            command_path = temporary_root / "taobao-native.cmd"
            command_path.write_text("@echo off\n", encoding="ascii")

            with self.assertRaisesRegex(RuntimeError, "exit_code=9.*需要登录"):
                run_search_products(
                    "苹果15手机壳",
                    temporary_root / "request.json",
                    temporary_root / "result.json",
                    command_path=command_path,
                )

    @patch("src.collector.subprocess.run")
    def test_nonzero_exit_includes_login_reason_from_stdout(self, run_command):
        run_command.return_value = subprocess.CompletedProcess(
            ["taobao-native.cmd"],
            1,
            '{"error":"未登录，请先登录淘宝账号"}',
            "",
        )
        with TemporaryDirectory() as directory:
            temporary_root = Path(directory)
            command_path = temporary_root / "taobao-native.cmd"
            command_path.write_text("@echo off\n", encoding="ascii")

            with self.assertRaisesRegex(RuntimeError, "exit_code=1.*未登录"):
                run_search_products(
                    "苹果15手机壳",
                    temporary_root / "request.json",
                    temporary_root / "result.json",
                    command_path=command_path,
                )

    @patch("src.collector.subprocess.run")
    def test_missing_result_file_fails_with_expected_path(self, run_command):
        run_command.return_value = subprocess.CompletedProcess([], 0, "saved", "")
        with TemporaryDirectory() as directory:
            temporary_root = Path(directory)
            command_path = temporary_root / "taobao-native.cmd"
            command_path.write_text("@echo off\n", encoding="ascii")
            result_path = temporary_root / "missing-result.json"

            with self.assertRaisesRegex(FileNotFoundError, "missing-result.json"):
                run_search_products(
                    "苹果15手机壳",
                    temporary_root / "request.json",
                    result_path,
                    command_path=command_path,
                )

    @patch("src.collector.subprocess.run")
    def test_invalid_json_fails_with_result_path(self, run_command):
        with TemporaryDirectory() as directory:
            temporary_root = Path(directory)
            command_path = temporary_root / "taobao-native.cmd"
            command_path.write_text("@echo off\n", encoding="ascii")
            result_path = temporary_root / "invalid.json"

            def write_invalid_json(command, **arguments):
                result_path.write_text("{broken", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, "saved", "")

            run_command.side_effect = write_invalid_json

            with self.assertRaisesRegex(RuntimeError, "invalid.json"):
                run_search_products(
                    "苹果15手机壳",
                    temporary_root / "request.json",
                    result_path,
                    command_path=command_path,
                )

    @patch("src.collector.subprocess.run")
    def test_invalid_response_structure_fails_with_received_value(self, run_command):
        with TemporaryDirectory() as directory:
            temporary_root = Path(directory)
            command_path = temporary_root / "taobao-native.cmd"
            command_path.write_text("@echo off\n", encoding="ascii")
            result_path = temporary_root / "invalid-structure.json"

            def write_invalid_structure(command, **arguments):
                result_path.write_text(
                    json.dumps(
                        {
                            "result": {
                                "keyword": "苹果15手机壳",
                                "count": 1,
                                "products": "not-a-list",
                            }
                        }
                    ),
                    encoding="utf-8",
                )
                return subprocess.CompletedProcess(command, 0, "saved", "")

            run_command.side_effect = write_invalid_structure

            with self.assertRaisesRegex(ValueError, "products.*not-a-list"):
                run_search_products(
                    "苹果15手机壳",
                    temporary_root / "request.json",
                    result_path,
                    command_path=command_path,
                )

    def test_empty_keyword_fails_with_received_value(self):
        with self.assertRaisesRegex(ValueError, "keyword='   '"):
            run_search_products("   ", "request.json", "result.json")


if __name__ == "__main__":
    unittest.main()
