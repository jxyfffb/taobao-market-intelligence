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

from src.collector import (
    canonicalize_search_product_url,
    capture_product_sku_catalog,
    parse_product_sku_catalog_response,
    parse_product_detail_response,
    run_product_detail,
    validate_product_detail_url,
)
from src.browser_search_collector import (
    _product_image_capture_expression,
    capture_product_images,
    normalize_browser_product_capture,
)
from app import _apply_search_product_fallback, _browser_product_detail


FIXTURE_PATH = PROJECT_ROOT / "tests" / "fixtures" / "product_detail_response.json"


class ProductDetailTests(unittest.TestCase):
    def test_browser_capture_rejects_navigation_labels_and_uses_page_title(self):
        detail = _browser_product_detail(
            {
                "title": "真维斯纯棉短袖-tmall.com天猫",
                "product_fields": {
                    "title": "参数",
                    "shop_name": "免费开店",
                    "price_text": "29.9",
                },
                "images": [],
            },
            "https://detail.tmall.com/item.htm?id=1048625064896",
            "1048625064896",
        )
        sources = _apply_search_product_fallback(
            detail,
            {"shop_name": "真维斯服饰旗舰店"},
            source="previous_product_snapshot_fallback",
        )

        self.assertEqual("真维斯纯棉短袖", detail["product"]["page_title"])
        self.assertEqual("真维斯服饰旗舰店", detail["shop"]["name"])
        self.assertEqual(
            "previous_product_snapshot_fallback",
            sources["shop_name"],
        )

    def test_normalizes_browser_product_images_by_kind_and_rejects_noise(self):
        payload = {
            "url": "https://item.taobao.com/item.htm?id=739189137255",
            "title": "商品详情",
            "images": [
                {"url": "//img.alicdn.com/main.jpg_q50.jpg_.webp", "source": "structured_main"},
                {"url": "https://img.alicdn.com/main.jpg", "source": "dom_main"},
                {"url": "https://gw.alicdn.com/sku-white.jpg_.webp", "source": "structured_sku"},
                {"url": "https://img.alicdn.com/detail-1.jpg", "source": "detail_api"},
                {"url": "https://gw.alicdn.com/platform-logo.png", "source": "dom_unknown", "width": 210, "height": 210},
                {"url": "https://gw.alicdn.com/tiny-service-2-tps-84-82.jpg", "source": "dom_detail", "width": 84, "height": 82},
                {"url": "https://gw.alicdn.com/placeholder-2-tps-2-2.png", "source": "structured_sku"},
                {"url": "https://evil.example/tracker.jpg", "source": "detail_api"},
            ],
            "reviews": {
                "totalText": "累计评价 39",
                "tags": ["印刷清晰", "尺码合适", "印刷清晰"],
                "items": [
                    {"content": "衣服质量不错，印刷也很清楚。", "sku": "黑色 XL", "date": "2026-08-08"},
                    {"content": "衣服质量不错，印刷也很清楚。", "sku": "黑色 XL", "date": "2026-08-08"},
                    {"content": "好", "sku": "白色 L"},
                ],
            },
        }

        normalized = normalize_browser_product_capture(
            payload,
            expected_item_id="739189137255",
        )

        self.assertEqual("success", normalized["status"])
        self.assertEqual(
            [
                {"url": "https://img.alicdn.com/main.jpg", "kind": "main"},
                {"url": "https://gw.alicdn.com/sku-white.jpg", "kind": "sku"},
                {"url": "https://img.alicdn.com/detail-1.jpg", "kind": "detail"},
            ],
            normalized["images"],
        )
        self.assertEqual("累计评价 39", normalized["reviews"]["total_text"])
        self.assertEqual(["印刷清晰", "尺码合适"], normalized["reviews"]["tags"])
        self.assertEqual(1, len(normalized["reviews"]["items"]))
        self.assertEqual("衣服质量不错，印刷也很清楚。", normalized["reviews"]["items"][0]["content"])

    def test_normalizes_browser_product_business_sku_question_and_video_modules(self):
        payload = {
            "url": "https://detail.tmall.com/item.htm?id=739189137255",
            "title": "男士短袖",
            "product": {
                "title": "男士纯棉短袖",
                "priceText": "68",
                "shopName": "品牌旗舰店",
                "paymentText": "7000+人付款",
                "originText": "江苏 无锡",
                "promotions": ["补贴后", "补贴后"],
                "services": ["退货宝", "48小时内发"],
                "attributesText": "材质 纯棉 版型 宽松",
            },
            "skuCatalog": {
                "hasSku": True,
                "selectedSkuId": "88",
                "selectedPriceText": "69",
                "dimensions": [
                    {
                        "label": "颜色分类",
                        "options": [
                            {
                                "value": "白色",
                                "valueId": "1",
                                "image": "https://img.alicdn.com/white.jpg_.webp",
                            }
                        ],
                    }
                ],
            },
            "images": [
                {"url": "https://img.alicdn.com/main.jpg", "source": "structured_main"}
            ],
            "reviews": {
                "totalText": "200 条评价",
                "items": [
                    {"content": f"这是第 {index} 条有效评价内容", "sku": "白色 L"}
                    for index in range(65)
                ],
            },
            "questions": {
                "totalText": "30 个问题",
                "items": [
                    {
                        "question": "面料会不会透？",
                        "answerCount": "3个回答",
                        "answers": ["白色略透，建议浅色内搭。"],
                    }
                ],
            },
            "videos": [
                {
                    "url": "https://video.taobao.com/product.mp4",
                    "poster": "https://img.alicdn.com/poster.jpg",
                }
            ],
        }

        normalized = normalize_browser_product_capture(
            payload,
            expected_item_id="739189137255",
        )

        self.assertEqual("success", normalized["status"])
        self.assertEqual("68", normalized["product_fields"]["price_text"])
        self.assertEqual("7000+人付款", normalized["product_fields"]["payment_text"])
        self.assertEqual("江苏 无锡", normalized["product_fields"]["origin_text"])
        self.assertEqual("白色", normalized["sku_catalog"]["dimensions"][0]["options"][0]["value"])
        self.assertEqual(60, len(normalized["reviews"]["items"]))
        self.assertEqual("面料会不会透？", normalized["questions"]["items"][0]["question"])
        self.assertEqual(1, len(normalized["videos"]))
        self.assertEqual("captured", normalized["coverage"]["questions"])

    def test_browser_product_image_filter_never_promotes_detail_assets_to_main(self):
        normalized = normalize_browser_product_capture(
            {
                "url": "https://detail.tmall.com/item.htm?id=739189137255",
                "images": [
                    {
                        "url": "https://img.alicdn.com/imgextra/i2/221/O1CN-main.jpg_760x760q30.jpg_.webp",
                        "source": "dom_detail",
                        "width": 60,
                        "height": 60,
                    },
                    {
                        "url": "https://gw.alicdn.com/bao/uploaded/i3/review-0-rate.jpg_960x960.jpg_.webp",
                        "source": "dom_detail",
                        "width": 540,
                        "height": 960,
                    },
                    {
                        "url": "https://img.alicdn.com/sns_logo/i2/avatar-0-ggpersonal.jpg_.webp",
                        "source": "dom_detail",
                        "width": 800,
                        "height": 800,
                    },
                    {
                        "url": "https://img.alicdn.com/imgextra/i3/banner-2-tps-384-80.png",
                        "source": "dom_sku",
                        "width": 384,
                        "height": 80,
                    },
                    {
                        "url": "https://gw.alicdn.com/bao/uploaded/i3/221/sku-red.jpg_.webp",
                        "source": "dom_sku",
                        "width": 800,
                        "height": 800,
                    },
                    {
                        "url": "https://gw.alicdn.com/imgextra/i1/banner-0-tps-750-128.jpg",
                        "source": "detail_api",
                    },
                    {
                        "url": "https://img.alicdn.com/imgextra/i1/221/detail-1.jpg",
                        "source": "detail_api",
                    },
                ],
            },
            expected_item_id="739189137255",
        )

        self.assertEqual(
            [
                {"url": "https://gw.alicdn.com/bao/uploaded/i3/221/sku-red.jpg", "kind": "sku"},
                {"url": "https://img.alicdn.com/imgextra/i1/221/detail-1.jpg", "kind": "detail"},
            ],
            normalized["images"],
        )

    def test_browser_product_gallery_sources_preserve_main_image_order(self):
        normalized = normalize_browser_product_capture(
            {
                "url": "https://item.taobao.com/item.htm?id=904813506032",
                "product": {"title": "百搭休闲短袖", "shopName": "万高纯棉工厂"},
                "images": [
                    {
                        "url": "https://img.alicdn.com/imgextra/i1/221/main-1.jpg_80x80.jpg_.webp",
                        "source": "dom_gallery",
                        "width": 80,
                        "height": 80,
                    },
                    {
                        "url": "https://img.alicdn.com/imgextra/i2/221/main-2.jpg_80x80.jpg_.webp",
                        "source": "picture_gallery",
                        "width": 80,
                        "height": 80,
                    },
                    {
                        "url": "https://img.alicdn.com/placeholder-2-tps-2-2.png",
                        "source": "css_gallery",
                        "width": 2,
                        "height": 2,
                    },
                    {
                        "url": "https://img.alicdn.com/imgextra/i3/221/detail-1.jpg",
                        "source": "detail_api",
                    },
                ],
            },
            expected_item_id="904813506032",
        )

        self.assertEqual(
            [
                {
                    "url": "https://img.alicdn.com/imgextra/i1/221/main-1.jpg",
                    "kind": "main",
                },
                {
                    "url": "https://img.alicdn.com/imgextra/i2/221/main-2.jpg",
                    "kind": "main",
                },
                {
                    "url": "https://img.alicdn.com/imgextra/i3/221/detail-1.jpg",
                    "kind": "detail",
                },
            ],
            normalized["images"],
        )

    def test_same_picture_can_be_preserved_as_sku_and_main_gallery_image(self):
        shared_url = "https://img.alicdn.com/imgextra/i1/221/shared-product.jpg"
        normalized = normalize_browser_product_capture(
            {
                "url": "https://item.taobao.com/item.htm?id=904813506032",
                "product": {"title": "百搭休闲短袖"},
                "images": [
                    {"url": shared_url, "source": "structured_sku"},
                    {
                        "url": shared_url,
                        "source": "dom_gallery",
                        "width": 80,
                        "height": 80,
                    },
                ],
            },
            expected_item_id="904813506032",
        )

        self.assertIn({"url": shared_url, "kind": "sku"}, normalized["images"])
        self.assertIn({"url": shared_url, "kind": "main"}, normalized["images"])

    def test_browser_capture_expression_uses_configured_review_batch_limit(self):
        expression = _product_image_capture_expression(review_start_page=4)

        self.assertIn("const reviewStartPage = 4", expression)
        self.assertIn("const reviewLimit = 60", expression)
        self.assertNotIn("__REVIEW_LIMIT__", expression)

    def test_large_sku_catalog_does_not_crowd_out_detail_images(self):
        normalized = normalize_browser_product_capture(
            {
                "url": "https://item.taobao.com/item.htm?id=904813506032",
                "product": {"title": "百搭休闲短袖"},
                "images": [
                    {
                        "url": f"https://img.alicdn.com/sku-{index}.jpg",
                        "source": "structured_sku",
                    }
                    for index in range(170)
                ]
                + [
                    {
                        "url": "https://img.alicdn.com/detail-1.jpg",
                        "source": "detail_api",
                    },
                    {
                        "url": "https://img.alicdn.com/detail-2.jpg",
                        "source": "detail_api",
                    },
                ],
            },
            expected_item_id="904813506032",
        )

        self.assertEqual(160, sum(image["kind"] == "sku" for image in normalized["images"]))
        self.assertEqual(2, sum(image["kind"] == "detail" for image in normalized["images"]))

    def test_browser_product_capture_caps_main_gallery_and_keeps_small_sku_thumbnails(self):
        normalized = normalize_browser_product_capture(
            {
                "url": "https://item.taobao.com/item.htm?id=904813506032",
                "product": {"title": "百搭休闲短袖"},
                "images": [
                    {
                        "url": f"https://img.alicdn.com/main-{index}.jpg",
                        "source": "dom_gallery",
                        "width": 80,
                        "height": 80,
                    }
                    for index in range(1, 8)
                ]
                + [
                    {
                        "url": "https://img.alicdn.com/sku-red.jpg",
                        "source": "dom_sku",
                        "width": 48,
                        "height": 48,
                    }
                ],
            },
            expected_item_id="904813506032",
        )

        self.assertEqual(5, sum(image["kind"] == "main" for image in normalized["images"]))
        self.assertIn(
            {"url": "https://img.alicdn.com/sku-red.jpg", "kind": "sku"},
            normalized["images"],
        )

    def test_browser_product_capture_requires_expected_product_and_preserves_login_gate(self):
        wrong_product = normalize_browser_product_capture(
            {
                "url": "https://detail.tmall.com/item.htm?id=888888888888",
                "images": [{"url": "https://img.alicdn.com/wrong.jpg", "kind": "main"}],
            },
            expected_item_id="739189137255",
        )
        login = normalize_browser_product_capture(
            {
                "url": "https://login.taobao.com/member/login.jhtml",
                "needsLogin": True,
                "images": [],
            },
            expected_item_id="739189137255",
        )

        self.assertEqual("failed", wrong_product["status"])
        self.assertEqual([], wrong_product["images"])
        self.assertEqual("login_required", login["status"])
        self.assertNotIn("url", login)

    @patch("src.browser_search_collector._close_target")
    @patch("src.browser_search_collector._cdp_evaluate")
    @patch("src.browser_search_collector._target_for_search_browser")
    @patch("src.browser_search_collector._cdp_ready", return_value=True)
    def test_browser_product_capture_saves_successful_raw_evidence(
        self,
        _ready,
        target_for_browser,
        evaluate,
        close_target,
    ):
        target = {
            "id": "product-page",
            "url": "https://item.taobao.com/item.htm?id=739189137255",
            "webSocketDebuggerUrl": "ws://127.0.0.1/devtools/page/product-page",
        }
        target_for_browser.return_value = target
        evaluate.return_value = {
            "url": target["url"],
            "images": [{"url": "https://img.alicdn.com/main.jpg", "source": "structured_main"}],
            "reviews": {"totalText": "39条评价", "tags": [], "items": []},
        }
        with TemporaryDirectory() as directory:
            raw_path = Path(directory) / "raw" / "browser-images.json"

            result = capture_product_images(
                directory,
                target["url"],
                "739189137255",
                raw_path,
            )

            self.assertEqual("success", result["status"])
            self.assertTrue(raw_path.is_file())
            self.assertEqual(str(raw_path), result["raw_source_ref"])
        close_target.assert_called_once_with(target)

    @patch("src.browser_search_collector._activate_target", create=True)
    @patch("src.browser_search_collector._close_target")
    @patch("src.browser_search_collector._cdp_evaluate")
    @patch("src.browser_search_collector._target_for_search_browser")
    @patch("src.browser_search_collector._cdp_ready", return_value=True)
    def test_browser_product_login_gate_activates_existing_window(
        self,
        _ready,
        target_for_browser,
        evaluate,
        close_target,
        activate_target,
    ):
        target = {
            "id": "login-page",
            "url": "https://login.taobao.com/member/login.jhtml",
            "webSocketDebuggerUrl": "ws://127.0.0.1/devtools/page/login-page",
        }
        target_for_browser.return_value = target
        evaluate.return_value = {
            "url": target["url"],
            "needsLogin": True,
            "images": [],
        }
        with TemporaryDirectory() as directory:
            result = capture_product_images(
                directory,
                "https://item.taobao.com/item.htm?id=739189137255",
                "739189137255",
                Path(directory) / "raw" / "browser-images.json",
            )

        self.assertEqual("login_required", result["status"])
        activate_target.assert_called_once_with(target)
        close_target.assert_not_called()

    def test_extracts_all_tagged_product_images_and_cleans_marketplace_title(self):
        response = {
            "result": {
                "url": "https://detail.tmall.com/item.htm?id=969963629588",
                "title": "西昊C300人体工学椅-tmall.com天猫",
                "content": (
                    "[商品id] 969963629588\n"
                    "[商品主图] https://gw.alicdn.com/main.jpg_.webp\n"
                    "[商品图] https://img.alicdn.com/gallery-1.jpg_.webp\n"
                    "[商品图] https://img.alicdn.com/gallery-1.jpg_.webp\n"
                    "[商品图] https://img.alicdn.com/gallery-2.jpg\n"
                    "图文详情 ￥1380起"
                ),
                "offset": 0,
                "remainingLength": 0,
                "truncated": False,
            }
        }

        detail = parse_product_detail_response(response, "live-detail.json")

        self.assertEqual("西昊C300人体工学椅", detail["product"]["page_title"])
        self.assertEqual(
            [
                {"url": "https://gw.alicdn.com/main.jpg", "kind": "main"},
                {"url": "https://img.alicdn.com/gallery-1.jpg", "kind": "gallery"},
                {"url": "https://img.alicdn.com/gallery-2.jpg", "kind": "gallery"},
            ],
            detail["product"]["images"],
        )

    def test_normalizes_sku_catalog_text_images_and_duplicate_nodes(self):
        response = {
            "result": {
                "success": True,
                "hasSku": True,
                "availableSkus": [
                    {
                        "label": "颜色分类切换大图模式",
                        "selectedValue": None,
                        "options": [
                            {
                                "text": "云白+脚踏",
                                "disabled": False,
                                "selected": False,
                                "image": "https://gw.alicdn.com/white.jpg_.webp",
                            },
                            {"text": "", "disabled": False},
                            {"text": "云白+脚踏", "disabled": False},
                            {
                                "text": "曜黑+脚踏",
                                "disabled": True,
                                "image": "https://gw.alicdn.com/placeholder-2-tps-2-2.png",
                            },
                        ],
                    }
                ],
            }
        }

        catalog = parse_product_sku_catalog_response(response, "sku-catalog.json")

        self.assertTrue(catalog["has_sku"])
        self.assertEqual("颜色分类", catalog["dimensions"][0]["label"])
        self.assertEqual(
            [
                {
                    "value": "云白+脚踏",
                    "available": True,
                    "selected": False,
                    "image_url": "https://gw.alicdn.com/white.jpg",
                },
                {
                    "value": "曜黑+脚踏",
                    "available": False,
                    "selected": False,
                    "image_url": None,
                },
            ],
            catalog["dimensions"][0]["options"],
        )

    @patch("src.collector.subprocess.run")
    def test_captures_sku_catalog_with_item_id_and_utf8_evidence(self, run_command):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            command_path = root / "taobao-native.cmd"
            command_path.write_text("@echo off\n", encoding="ascii")
            result_path = root / "raw" / "sku-catalog.json"

            def write_catalog(command, **arguments):
                output_path = Path(command[command.index("-o") + 1])
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(
                    json.dumps(
                        {
                            "result": {
                                "success": True,
                                "hasSku": False,
                                "availableSkus": [],
                            }
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
                return subprocess.CompletedProcess(command, 0, "saved", "")

            run_command.side_effect = write_catalog
            captured = capture_product_sku_catalog(
                "969963629588",
                root / "requests",
                result_path,
                command_path=command_path,
            )

            request = json.loads(
                (root / "requests" / "get-product-skus.json").read_text(encoding="utf-8")
            )
            self.assertEqual("get_product_skus", request["tool"])
            self.assertEqual("969963629588", request["arguments"]["itemId"])
            self.assertEqual("taobao-market-intelligence", request["arguments"]["sourceApp"])
            self.assertFalse(captured["has_sku"])
            self.assertEqual(str(result_path), captured["raw_source_ref"])

    def test_competitor_capture_frontend_contains_intelligence_dashboard(self):
        script = (PROJECT_ROOT / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn("renderCompetitorIntelligence", script)
        self.assertIn("renderCompetitorPriceTrend", script)
        self.assertIn("renderSkuPriceHistory", script)
        self.assertIn("打开淘宝原页", script)
        self.assertIn("查看价格历史", script)
        self.assertIn("页面可见价", script)
        self.assertIn("export.zip", script)

    def test_competitor_workspace_contains_collector_account_recovery(self):
        homepage = (PROJECT_ROOT / "static" / "index.html").read_text(encoding="utf-8")
        script = (PROJECT_ROOT / "static" / "app.js").read_text(encoding="utf-8")
        for expected in (
            'id="open-collector-account"',
            'id="clear-collector-login"',
            "打开采集账号",
            "清除本工具登录状态",
        ):
            self.assertIn(expected, homepage)
        self.assertIn('/api/collector/account-browser', script)
        self.assertIn('/api/collector/login-profile', script)

    def test_canonicalizes_search_ad_link_using_the_trusted_item_id(self):
        advertising_url = (
            "https://click.simba.taobao.com/cc_im?p=encoded-ad-target"
            "&s=2049870895&k=2625&id=969963629588"
        )

        self.assertEqual(
            "https://item.taobao.com/item.htm?id=969963629588",
            canonicalize_search_product_url(advertising_url, "969963629588"),
        )
        self.assertEqual(
            "https://detail.tmall.com/item.htm?id=739189137255&skuId=88",
            canonicalize_search_product_url(
                "https://detail.tmall.com/item.htm?id=739189137255&skuId=88",
                "739189137255",
            ),
        )

    def test_accepts_only_https_taobao_and_tmall_item_links_with_numeric_id(self):
        valid_urls = (
            "https://item.taobao.com/item.htm?id=123456",
            "https://detail.tmall.com/item.htm?id=739189137255&skuId=88",
        )
        for product_url in valid_urls:
            with self.subTest(product_url=product_url):
                self.assertEqual(product_url, validate_product_detail_url(product_url))

        invalid_urls = (
            "http://item.taobao.com/item.htm?id=123456",
            "https://evil.example/item.htm?id=123456",
            "https://item.taobao.com/not-item.htm?id=123456",
            "https://detail.tmall.com/item.htm?id=not-numeric",
            "https://item.taobao.com/item.htm",
            "javascript:alert(1)",
            "   ",
        )
        for product_url in invalid_urls:
            with self.subTest(product_url=product_url):
                with self.assertRaisesRegex(ValueError, "product_url"):
                    validate_product_detail_url(product_url)

    @patch("src.collector.subprocess.run")
    def test_navigates_then_reads_complete_page_with_utf8_files(self, run_command):
        with TemporaryDirectory() as directory:
            temporary_root = Path(directory)
            command_path = temporary_root / "taobao-native.cmd"
            command_path.write_text("@echo off\n", encoding="ascii")
            request_directory = temporary_root / "请求"
            detail_result_path = temporary_root / "结果" / "商品详情.json"
            fixture_bytes = FIXTURE_PATH.read_bytes()

            def write_command_result(command, **arguments):
                output_path = Path(command[command.index("-o") + 1])
                output_path.parent.mkdir(parents=True, exist_ok=True)
                request_payload = json.loads(
                    Path(command[command.index("--request") + 1]).read_text(
                        encoding="utf-8"
                    )
                )
                if request_payload["tool"] == "navigate_to_url":
                    output_path.write_text(
                        json.dumps({"result": {"opened": True}}),
                        encoding="utf-8",
                    )
                else:
                    output_path.write_bytes(fixture_bytes)
                return subprocess.CompletedProcess(command, 0, "saved", "")

            run_command.side_effect = write_command_result

            detail = run_product_detail(
                "https://detail.tmall.com/item.htm?id=739189137255",
                request_directory,
                detail_result_path,
                command_path=command_path,
            )

            self.assertEqual(2, run_command.call_count)
            navigate_command = run_command.call_args_list[0].args[0]
            detail_command = run_command.call_args_list[1].args[0]
            self.assertEqual(str(command_path), navigate_command[0])
            self.assertEqual(str(command_path), detail_command[0])
            self.assertEqual(str(detail_result_path), detail_command[-1])
            self.assertEqual(fixture_bytes, detail_result_path.read_bytes())
            self.assertEqual("utf-8", run_command.call_args_list[0].kwargs["encoding"])
            self.assertEqual("utf-8", run_command.call_args_list[1].kwargs["encoding"])

            navigate_request = json.loads(
                (request_directory / "navigate-product.json").read_text(encoding="utf-8")
            )
            detail_request = json.loads(
                (request_directory / "read-product-detail.json").read_text(encoding="utf-8")
            )
            self.assertEqual("navigate_to_url", navigate_request["tool"])
            self.assertEqual(
                "https://detail.tmall.com/item.htm?id=739189137255",
                navigate_request["arguments"]["url"],
            )
            self.assertEqual(
                "taobao-market-intelligence",
                navigate_request["arguments"]["sourceApp"],
            )
            self.assertEqual("read_page_content", detail_request["tool"])
            self.assertEqual(200000, detail_request["arguments"]["maxLength"])
            self.assertEqual(0, detail_request["arguments"]["offset"])
            self.assertEqual(
                "taobao-market-intelligence",
                detail_request["arguments"]["sourceApp"],
            )
            self.assertEqual("739189137255", detail["product"]["item_id"])

    def test_extracts_product_shop_sales_reviews_services_and_attributes(self):
        response = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

        detail = parse_product_detail_response(response, FIXTURE_PATH)

        self.assertEqual("739189137255", detail["product"]["item_id"])
        self.assertIn("苹果15手机壳", detail["product"]["page_title"])
        self.assertEqual(
            "https://img.alicdn.com/imgextra/item.jpg",
            detail["product"]["main_image_url"],
        )
        self.assertEqual("￥8.9起", detail["product"]["visible_price_text"])
        self.assertEqual("佰蓝旗舰店", detail["shop"]["name"])
        self.assertEqual("98%", detail["shop"]["positive_rate_text"])
        self.assertEqual("已售 3000+", detail["sales"]["sold_text"])
        self.assertEqual("回头客141人", detail["sales"]["repeat_buyer_text"])
        self.assertEqual("超500人加购", detail["sales"]["cart_text"])
        self.assertEqual("115人评价", detail["reviews"]["count_text"])
        self.assertIn("配合度很好", detail["reviews"]["preview_text"])
        self.assertIn("磨砂工艺", detail["attributes"]["visible_text"])
        self.assertIn("Apple/苹果", detail["attributes"]["visible_text"])
        for service_label in (
            "可开发票",
            "免运费",
            "7天无理由退换",
            "假一赔四",
            "极速退款",
            "信用卡支付",
        ):
            self.assertIn(service_label, detail["services"])

    @patch("src.collector.subprocess.run")
    def test_cli_failure_stops_before_next_step_and_includes_reason(self, run_command):
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

            with self.assertRaisesRegex(RuntimeError, "navigate_to_url.*exit_code=1.*未登录"):
                run_product_detail(
                    "https://item.taobao.com/item.htm?id=123456",
                    temporary_root / "requests",
                    temporary_root / "detail.json",
                    command_path=command_path,
                )

        self.assertEqual(1, run_command.call_count)

    def test_rejects_truncated_or_mismatched_detail_response(self):
        response = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        invalid_responses = (
            (
                {
                    **response,
                    "result": {
                        **response["result"],
                        "truncated": True,
                        "remainingLength": 50,
                    },
                },
                "truncated",
            ),
            (
                {
                    **response,
                    "result": {
                        **response["result"],
                        "url": "https://evil.example/item.htm?id=739189137255",
                    },
                },
                "url",
            ),
        )
        for invalid_response, expected_message in invalid_responses:
            with self.subTest(expected_message=expected_message):
                with self.assertRaisesRegex(ValueError, expected_message):
                    parse_product_detail_response(invalid_response, FIXTURE_PATH)

    @patch("src.collector.subprocess.run")
    def test_rejects_redirect_to_a_different_valid_product(self, run_command):
        with TemporaryDirectory() as directory:
            temporary_root = Path(directory)
            command_path = temporary_root / "taobao-native.cmd"
            command_path.write_text("@echo off\n", encoding="ascii")

            def write_command_result(command, **arguments):
                output_path = Path(command[command.index("-o") + 1])
                output_path.parent.mkdir(parents=True, exist_ok=True)
                request_payload = json.loads(
                    Path(command[command.index("--request") + 1]).read_text(
                        encoding="utf-8"
                    )
                )
                if request_payload["tool"] == "navigate_to_url":
                    output_path.write_text('{"result":{"opened":true}}', encoding="utf-8")
                else:
                    output_path.write_bytes(FIXTURE_PATH.read_bytes())
                return subprocess.CompletedProcess(command, 0, "saved", "")

            run_command.side_effect = write_command_result

            with self.assertRaisesRegex(
                ValueError,
                r"requested product.*123456.*actual.*739189137255",
            ):
                run_product_detail(
                    "https://item.taobao.com/item.htm?id=123456",
                    temporary_root / "requests",
                    temporary_root / "detail.json",
                    command_path=command_path,
                )


if __name__ == "__main__":
    unittest.main()
