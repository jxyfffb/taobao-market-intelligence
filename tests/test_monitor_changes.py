import unittest

from src.monitor_changes import (
    summarize_competitor_changes,
    summarize_keyword_changes,
    summarize_shop_changes,
)


class MonitorChangeSummaryTests(unittest.TestCase):
    def test_keyword_summary_filters_small_noise_and_keeps_actionable_changes(self):
        changes = summarize_keyword_changes(
            {
                "added": [
                    {"item_id": "new", "title": "新商品", "display_rank": 6, "product_url": "https://item.taobao.com/item.htm?id=1"},
                    {"item_id": "late", "title": "后排商品", "display_rank": 31},
                ],
                "removed": [],
                "rank_changes": [
                    {"item_id": "quiet", "title": "小波动", "old_rank": 12, "new_rank": 14},
                    {"item_id": "rank", "title": "大幅上升", "old_rank": 18, "new_rank": 8},
                ],
                "price_changes": [
                    {"item_id": "tiny", "title": "小改价", "old_price": "99", "new_price": "96"},
                    {"item_id": "price", "title": "明显降价", "old_price": "129", "new_price": "99"},
                ],
                "payment_changes": [
                    {"item_id": "sold", "title": "热度增长", "old_value": "1000+人付款", "new_value": "2000+人付款"}
                ],
            }
        )
        categories = [change["category"] for change in changes]
        self.assertEqual(4, len(changes))
        self.assertIn("新品进入", categories)
        self.assertIn("排名异动", categories)
        self.assertIn("价格变化", categories)
        self.assertIn("付款增长", categories)
        self.assertNotIn("小波动", [change["title"] for change in changes])
        self.assertNotIn("小改价", [change["title"] for change in changes])

    def test_competitor_summary_detects_price_main_image_sku_and_review_changes(self):
        older = {
            "item_id": "123",
            "title": "竞品",
            "page_url": "https://item.taobao.com/item.htm?id=123",
            "visible_price_text": "¥129",
            "shop_name": "店铺",
            "archive": {
                "product_fields": {"price_text": "129", "payment_text": "1000+人付款"},
                "images": [{"kind": "main", "url": "https://img.alicdn.com/a.jpg"}],
                "sku_catalog": {"dimensions": [{"label": "颜色", "options": [{"value": "白色", "available": True, "image_url": "https://img.alicdn.com/white.jpg"}]}]},
                "reviews": {"total_text": "100 条评价", "items": []},
            },
        }
        newer = {
            **older,
            "visible_price_text": "¥99",
            "archive": {
                "product_fields": {"price_text": "99", "payment_text": "2000+人付款"},
                "images": [{"kind": "main", "url": "https://img.alicdn.com/b.jpg"}],
                "sku_catalog": {"dimensions": [{"label": "颜色", "options": [
                    {"value": "白色", "available": False, "image_url": "https://img.alicdn.com/white-new.jpg"},
                    {"value": "黑色", "available": True, "image_url": "https://img.alicdn.com/black.jpg"},
                ]}]},
                "reviews": {"total_text": "125 条评价", "items": []},
            },
        }
        categories = {change["category"] for change in summarize_competitor_changes(older, newer)}
        self.assertTrue({"价格变化", "付款增长", "主图变化", "SKU 变化", "SKU 缺货", "SKU 图变化", "评价增长"} <= categories)

    def test_shop_summary_reports_new_immediately_and_removal_after_two_misses(self):
        old_item = {"item_id": "1", "title": "旧商品", "product_url": "https://item.taobao.com/item.htm?id=1"}
        new_item = {"item_id": "2", "title": "新品", "product_url": "https://item.taobao.com/item.htm?id=2"}
        self.assertEqual(
            ["店铺上新"],
            [change["category"] for change in summarize_shop_changes(
                {"products": [old_item, new_item]}, {"products": [old_item]}, None
            )],
        )
        self.assertEqual([], summarize_shop_changes({"products": []}, {"products": [old_item]}, None))
        removed = summarize_shop_changes(
            {"products": []}, {"products": []}, {"products": [old_item]}
        )
        self.assertEqual(["疑似下架"], [change["category"] for change in removed])


if __name__ == "__main__":
    unittest.main()
