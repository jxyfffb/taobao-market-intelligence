import os
from pathlib import Path
import sys
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class LatestLauncherTests(unittest.TestCase):
    def test_latest_launcher_reuses_packaged_application_data(self):
        try:
            from launch_latest import configure_shared_application_data
        except ModuleNotFoundError:
            self.fail("latest source launcher is missing")

        environment = {"LOCALAPPDATA": "C:\\Users\\Test\\AppData\\Local"}

        resolved_directory = configure_shared_application_data(environment)

        expected_directory = Path(
            "C:/Users/Test/AppData/Local/LaobingMarketIntelligence/data"
        )
        self.assertEqual(expected_directory, resolved_directory)
        self.assertEqual(
            str(expected_directory),
            environment["TAOBAO_MARKET_DATA_DIRECTORY"],
        )

    def test_latest_launcher_rejects_missing_local_app_data(self):
        try:
            from launch_latest import configure_shared_application_data
        except ModuleNotFoundError:
            self.fail("latest source launcher is missing")

        with self.assertRaisesRegex(ValueError, "LOCALAPPDATA"):
            configure_shared_application_data({})


if __name__ == "__main__":
    unittest.main()
