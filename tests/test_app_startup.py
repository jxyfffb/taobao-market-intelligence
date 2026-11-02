from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import (
    APPLICATION_PORT_CANDIDATES,
    ApplicationStartupError,
    application,
    main,
    select_application_port,
    start_application,
)
from src import PRODUCT_KEY, PRODUCT_NAME, PRODUCT_VERSION


class AppStartupTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(application)

    def test_health_returns_product_identity_and_version(self):
        response = self.client.get("/api/health")

        self.assertEqual(200, response.status_code)
        self.assertEqual(
            {
                "product_key": PRODUCT_KEY,
                "product_name": PRODUCT_NAME,
                "version": PRODUCT_VERSION,
            },
            response.json(),
        )

    def test_homepage_opens(self):
        response = self.client.get("/")

        self.assertEqual(200, response.status_code)
        self.assertIn("text/html", response.headers["content-type"])
        self.assertIn(PRODUCT_NAME, response.text)

    @patch("app.uvicorn.run")
    @patch("app.find_running_product", return_value=None)
    @patch("app.select_application_port", return_value=8765)
    def test_first_start_listens_only_on_loopback(
        self,
        select_port,
        find_running_product,
        run_uvicorn,
    ):
        exit_code = start_application()

        self.assertEqual(0, exit_code)
        select_port.assert_called_once_with()
        run_uvicorn.assert_called_once_with(
            application,
            host="127.0.0.1",
            port=8765,
            log_level="info",
        )

    @patch("app.open_application_in_browser")
    @patch("app.uvicorn.run")
    @patch("app.find_running_product", return_value=(18765, PRODUCT_VERSION))
    @patch("app.select_application_port")
    def test_repeated_start_on_fallback_port_opens_existing_server(
        self,
        select_port,
        find_running_product,
        run_uvicorn,
        open_browser,
    ):
        with patch("app.sys.frozen", True, create=True):
            exit_code = start_application()

        self.assertEqual(0, exit_code)
        open_browser.assert_called_once_with(18765)
        select_port.assert_not_called()
        run_uvicorn.assert_not_called()

    @patch("app.open_application_in_browser")
    @patch("app.uvicorn.run")
    @patch("app.find_running_product", return_value=(8765, PRODUCT_VERSION))
    def test_source_shortcut_opens_existing_server(
        self,
        find_running_product,
        run_uvicorn,
        open_browser,
    ):
        exit_code = start_application(open_browser=True)

        self.assertEqual(0, exit_code)
        open_browser.assert_called_once_with(8765)
        run_uvicorn.assert_not_called()

    @patch("app.schedule_browser_open")
    @patch("app.uvicorn.run")
    @patch("app.find_running_product", return_value=None)
    @patch("app.select_application_port", return_value=8765)
    def test_source_shortcut_opens_browser_after_starting_server(
        self,
        select_port,
        find_running_product,
        run_uvicorn,
        schedule_browser,
    ):
        exit_code = start_application(open_browser=True)

        self.assertEqual(0, exit_code)
        schedule_browser.assert_called_once_with(8765)
        run_uvicorn.assert_called_once()

    @patch("app.start_application", return_value=0)
    def test_main_open_browser_flag_starts_source_launcher(self, start):
        exit_code = main(["--open-browser"])

        self.assertEqual(0, exit_code)
        start.assert_called_once_with(open_browser=True)

    @patch("app.schedule_packaged_browser_open")
    @patch("app.uvicorn.run")
    @patch("app.find_running_product", return_value=None)
    @patch("app.select_application_port", return_value=18765)
    def test_packaged_start_uses_fallback_port_and_disables_console_logging(
        self,
        select_port,
        find_running_product,
        run_uvicorn,
        schedule_browser,
    ):
        with patch("app.sys.frozen", True, create=True):
            exit_code = start_application()

        self.assertEqual(0, exit_code)
        schedule_browser.assert_called_once_with(18765)
        run_uvicorn.assert_called_once_with(
            application,
            host="127.0.0.1",
            port=18765,
            log_level="info",
            log_config=None,
            access_log=False,
        )

    @patch("app.ensure_listen_address_available")
    def test_port_selection_falls_back_after_windows_permission_error(self, ensure_address):
        ensure_address.side_effect = [
            RuntimeError(
                "Listen address unavailable: host=127.0.0.1 port=8765 "
                "error=[WinError 10013] permission denied"
            ),
            None,
        ]

        selected = select_application_port(ports=(8765, 18765))

        self.assertEqual(18765, selected)
        self.assertEqual(
            [
                unittest.mock.call("127.0.0.1", 8765),
                unittest.mock.call("127.0.0.1", 18765),
            ],
            ensure_address.call_args_list,
        )

    @patch("app.ensure_listen_address_available")
    def test_all_candidate_ports_raise_friendly_startup_error(self, ensure_address):
        ensure_address.side_effect = RuntimeError("[WinError 10013] permission denied")

        with self.assertRaisesRegex(ApplicationStartupError, "无法启动本地服务"):
            select_application_port(ports=APPLICATION_PORT_CANDIDATES)

    @patch("app.show_startup_error")
    @patch("app.start_application")
    def test_main_converts_startup_error_to_message_without_traceback(
        self, start, show_error
    ):
        start.side_effect = ApplicationStartupError("无法启动本地服务，请重启电脑后再试。")

        exit_code = main([])

        self.assertEqual(1, exit_code)
        show_error.assert_called_once_with("无法启动本地服务，请重启电脑后再试。")


if __name__ == "__main__":
    unittest.main()
