from pathlib import Path
import sys
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.product_link_resolver import resolve_product_link


class ProductLinkResolverTests(unittest.TestCase):
    def test_accepts_complete_taobao_and_tmall_links(self):
        taobao = resolve_product_link(
            "https://item.taobao.com/item.htm?id=123456&skuId=88"
        )
        tmall = resolve_product_link(
            "https://detail.tmall.com/item.htm?id=739189137255"
        )

        self.assertEqual("123456", taobao["item_id"])
        self.assertEqual(
            "https://item.taobao.com/item.htm?id=123456&skuId=88",
            taobao["resolved_url"],
        )
        self.assertEqual("739189137255", tmall["item_id"])

    def test_extracts_first_link_from_share_text(self):
        resolved = resolve_product_link(
            "复制这段内容打开淘宝：夏季男士Polo衫 https://item.taobao.com/item.htm?id=987654 ，限时优惠"
        )

        self.assertEqual("987654", resolved["item_id"])
        self.assertEqual(
            "https://item.taobao.com/item.htm?id=987654",
            resolved["source_url"],
        )

    def test_resolves_short_link_and_embedded_canonical_url(self):
        calls = []

        def fetch_short_url(url):
            calls.append(url)
            return {
                "final_url": "https://m.tb.cn/h.redirected",
                "content": (
                    '<meta content="https://detail.tmall.com/item.htm?id=246810" '
                    'property="og:url">'
                ),
            }

        resolved = resolve_product_link(
            "新品分享 https://e.tb.cn/h.example?tk=abc",
            fetch_short_url=fetch_short_url,
        )

        self.assertEqual(["https://e.tb.cn/h.example?tk=abc"], calls)
        self.assertEqual("246810", resolved["item_id"])
        self.assertEqual(
            "https://detail.tmall.com/item.htm?id=246810",
            resolved["resolved_url"],
        )

    def test_canonicalizes_trusted_mobile_item_link(self):
        resolved = resolve_product_link(
            "https://h5.m.taobao.com/awp/core/detail.htm?id=112233"
        )

        self.assertEqual("112233", resolved["item_id"])
        self.assertEqual(
            "https://item.taobao.com/item.htm?id=112233",
            resolved["resolved_url"],
        )

    def test_rejects_untrusted_or_incomplete_links(self):
        invalid_values = (
            "没有链接",
            "http://item.taobao.com/item.htm?id=123",
            "https://evil.example/item.htm?id=123",
            "https://item.taobao.com/item.htm?id=not-numeric",
            "javascript:alert(1)",
        )

        for value in invalid_values:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    resolve_product_link(value)


if __name__ == "__main__":
    unittest.main()
