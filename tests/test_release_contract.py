from pathlib import Path
import unittest

from src import PRODUCT_VERSION


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = PROJECT_ROOT / "packaging" / "taobao-market-intelligence.spec"
INSTALLER_PATH = PROJECT_ROOT / "packaging" / "taobao-market-intelligence.iss"
BUILD_SCRIPT_PATH = PROJECT_ROOT / "scripts" / "build-release.ps1"

if not (SPEC_PATH.exists() and INSTALLER_PATH.exists()):
    raise unittest.SkipTest("打包脚本不随开源仓库发布，跳过发布契约测试")


class ReleaseContractTests(unittest.TestCase):
    def test_release_version_is_v1_patch_1(self):
        self.assertEqual("1.0.1", PRODUCT_VERSION)

    def test_pyinstaller_excludes_source_only_entitlement_and_only_bundles_static(self):
        specification = SPEC_PATH.read_text(encoding="utf-8")
        self.assertIn('"src.development_entitlement"', specification)
        self.assertIn('datas=[(str(project_root / "static"), "static")]', specification)
        self.assertNotIn("tests /", specification)
        self.assertNotIn("private-key", specification.casefold())

    def test_installer_has_independent_identity_and_preserves_user_data(self):
        installer = INSTALLER_PATH.read_text(encoding="utf-8")
        self.assertIn("A34AC52A-94E6-4A49-99A0-59B42CB778F1", installer)
        self.assertIn("LaobingMarketIntelligence", installer)
        self.assertNotIn("Delete user data", installer)
        self.assertNotIn("{localappdata}\\LaobingMarketIntelligence\\data", installer)

    def test_build_scans_forbidden_content_before_creating_manifest(self):
        build_script = BUILD_SCRIPT_PATH.read_text(encoding="utf-8")
        for required in (
            "PRIVATE KEY",
            "taobao_market_license_issuer.py",
            "src.development_entitlement",
            "archive_viewer",
            "Get-FileHash",
        ):
            self.assertIn(required, build_script)
        self.assertIn("PRODUCT_VERSION", build_script)
        self.assertIn("$productVersion", build_script)

    def test_installer_version_matches_product_version(self):
        installer = INSTALLER_PATH.read_text(encoding="utf-8")
        self.assertIn(f'#define MyAppVersion "{PRODUCT_VERSION}"', installer)


if __name__ == "__main__":
    unittest.main()
