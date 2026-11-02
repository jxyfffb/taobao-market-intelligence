from pathlib import Path
import sys
import unittest

from fastapi.testclient import TestClient


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import application


class WorkspaceShellTests(unittest.TestCase):
    def test_homepage_is_a_low_clutter_collection_workspace(self):
        with TestClient(application) as client:
            homepage = client.get("/")
        for expected in (
            'class="app-shell"',
            'id="search-workspace"',
            'id="results-section"',
            'id="history-section"',
            'id="result-pagination"',
            "市场搜索",
            "竞品采集",
            "监控中心",
            "设置",
            'id="settings-workspace"',
            'id="license-request-code"',
            'id="license-activation-code"',
            'id="submit-license-code"',
            'id="ai-api-key"',
        ):
            self.assertIn(expected, homepage.text)
        for removed in ("市场分析", "完整市场分析", "报告资产", "我的产品", "竞品分析报告"):
            self.assertNotIn(removed, homepage.text)

    def test_competitor_workspace_only_collects_and_exports_raw_data(self):
        with TestClient(application) as client:
            homepage = client.get("/")
            script = client.get("/static/app.js")
        for expected in (
            'href="#competitor-workspace"',
            'id="competitor-workspace"',
            'id="competitor-url-form"',
            'id="competitor-record-list"',
            'id="competitor-sku-form"',
            'id="export-competitor-package"',
            'type="text" autocomplete="off" placeholder="粘贴商品链接或整段分享内容"',
            "已采集竞品",
            "导出竞品资料包 ZIP",
        ):
            self.assertIn(expected, homepage.text)
        for expected in (
            'fetch("/api/competitors")',
            "/api/competitors/prepare",
            "/capture",
            "/export.zip",
            '"DELETE"',
            "renderCompetitorArchive",
        ):
            self.assertIn(expected, script.text)
        self.assertNotIn("请先搜索一个关键词", script.text)
        for removed in ("competitor-analysis", "own-product", "report.html"):
            self.assertNotIn(removed, homepage.text + script.text)

    def test_top_level_views_have_copyable_hash_routes(self):
        with TestClient(application) as client:
            homepage = client.get("/")
            script = client.get("/static/app.js")

        for view_hash in (
            "#search-workspace",
            "#competitor-workspace",
            "#monitor-workspace",
            "#settings-workspace",
        ):
            self.assertIn(view_hash, homepage.text)
            self.assertIn(view_hash, script.text)
        self.assertIn('window.addEventListener("hashchange", showViewFromHash)', script.text)
        self.assertIn("showViewFromHash();", script.text)
        self.assertIn("20261102-open-source-v1", homepage.text)
        self.assertNotIn("开发预览版", homepage.text)

    def test_monitor_workspace_separates_shop_dynamics_and_same_product_pricing(self):
        with TestClient(application) as client:
            homepage = client.get("/")

        for expected in (
            "竞店动态",
            "跟踪店铺上新、下架与商品结构变化",
            "同品价盘",
            "同款与分销链接按可比 SKU 分开看价",
        ):
            self.assertIn(expected, homepage.text)

    def test_product_list_supports_filter_pagination_and_detail_capture(self):
        with TestClient(application) as client:
            homepage = client.get("/")
            script = client.get("/static/app.js")
        self.assertIn('id="result-pagination"', homepage.text)
        self.assertIn("RESULTS_PER_PAGE = 20", script.text)
        self.assertIn('collect.textContent = "采集详情"', script.text)
        self.assertIn('id="export-snapshot"', homepage.text)
        self.assertNotIn("export-market-report", homepage.text + script.text)


if __name__ == "__main__":
    unittest.main()
