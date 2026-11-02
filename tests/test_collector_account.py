from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


from src.browser_search_collector import (
    clear_collector_login_profile,
    open_collector_account_browser,
)


class CollectorAccountTests(unittest.TestCase):
    @patch("src.browser_search_collector._launch_search_browser")
    @patch("src.browser_search_collector._cdp_ready", return_value=False)
    def test_account_browser_can_open_without_starting_a_collection(
        self,
        _ready,
        launch,
    ):
        with TemporaryDirectory() as temporary_directory:
            result = open_collector_account_browser(temporary_directory)

        self.assertEqual("opened", result["status"])
        launch.assert_called_once()
        self.assertIn("login.taobao.com", launch.call_args.args[1])

    @patch("src.browser_search_collector._cdp_ready", return_value=False)
    def test_clear_login_profile_only_removes_the_collector_profile(self, _ready):
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            profile = root / "browser" / "taobao-search-profile"
            profile.mkdir(parents=True)
            (profile / "Cookies").write_text("local session", encoding="utf-8")
            unrelated = root / "keep.txt"
            unrelated.write_text("keep", encoding="utf-8")

            result = clear_collector_login_profile(root)

            self.assertTrue(result["cleared"])
            self.assertFalse(profile.exists())
            self.assertEqual("keep", unrelated.read_text(encoding="utf-8"))

    @patch("src.browser_search_collector._cdp_ready", return_value=True)
    def test_clear_login_profile_requires_collector_browser_to_be_closed(self, _ready):
        with TemporaryDirectory() as temporary_directory:
            with self.assertRaisesRegex(RuntimeError, "关闭专属采集浏览器"):
                clear_collector_login_profile(temporary_directory)


if __name__ == "__main__":
    unittest.main()
