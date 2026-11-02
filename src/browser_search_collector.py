import base64
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import struct
import subprocess
import time
from urllib import parse, request
from uuid import uuid4


SEARCH_BROWSER_PORT = 9341
SEARCH_PAGE_SIZE = 48
PRODUCT_REVIEW_LIMIT = 60
PRODUCT_QUESTION_LIMIT = 20
SEARCH_SOURCE_APP = "taobao-market-intelligence"
TAOBAO_SEARCH_HOSTS = {
    "s.taobao.com",
    "item.taobao.com",
    "detail.tmall.com",
    "login.taobao.com",
    "login.tmall.com",
    "passport.taobao.com",
    "sec.taobao.com",
}
LOGIN_MESSAGE = "请在弹出的采集浏览器中完成淘宝扫码登录，然后再次点击采集下一页。"
FIRST_PAGE_LOGIN_MESSAGE = "请在弹出的采集浏览器中完成淘宝扫码登录，然后重新点击开始搜索。"
BLOCKED_MESSAGE = "淘宝页面出现安全验证，本次已停止采集。请在采集浏览器中完成验证后重试。"
PRODUCT_LOGIN_MESSAGE = "请在弹出的采集浏览器中完成淘宝扫码登录，然后再次点击“抓取商品信息”。"
SHOP_LOGIN_MESSAGE = "请在弹出的采集浏览器中完成淘宝扫码登录，然后再次执行店铺监控。"


def _is_taobao_page_host(hostname):
    hostname = str(hostname or "").casefold()
    return any(
        hostname == suffix or hostname.endswith("." + suffix)
        for suffix in ("taobao.com", "tmall.com")
    )


def build_taobao_search_url(keyword, page_number):
    normalized_keyword = str(keyword or "").strip()
    if not normalized_keyword:
        raise ValueError(f"keyword must be non-empty text: actual={keyword!r}")
    if not isinstance(page_number, int) or isinstance(page_number, bool) or page_number < 1:
        raise ValueError(f"page_number must be a positive integer: actual={page_number!r}")
    query = parse.urlencode(
        {
            "q": normalized_keyword,
            "s": (page_number - 1) * SEARCH_PAGE_SIZE,
        }
    )
    return f"https://s.taobao.com/search?{query}"


def _optional_text(value):
    if value is None:
        return None
    normalized = re.sub(r"\s+", " ", str(value)).strip()
    return normalized or None


def _canonical_product_url(product_url, item_id):
    item_id = str(item_id or "").strip()
    if not item_id.isdigit() or int(item_id) <= 0:
        return None, "unknown"
    parsed_url = parse.urlparse(str(product_url or "").strip())
    hostname = (parsed_url.hostname or "").casefold()
    platform_type = "tmall" if hostname == "detail.tmall.com" else "taobao"
    if hostname not in {"detail.tmall.com", "item.taobao.com"}:
        platform_type = "taobao"
    host = "detail.tmall.com" if platform_type == "tmall" else "item.taobao.com"
    return f"https://{host}/item.htm?id={item_id}", platform_type


def _clean_image_url(image_url):
    value = _optional_text(image_url)
    if value is None:
        return None
    if value.startswith("//"):
        value = "https:" + value
    value = re.sub(
        r"(\.(?:jpe?g|png|gif))(?:_(?:\d+x\d+)?q\d+\.(?:jpe?g|webp))(?=\?|$)",
        r"\1",
        value,
        flags=re.I,
    )
    value = re.sub(r"_\.webp(?:\?.*)?$", "", value, flags=re.I)
    value = re.sub(
        r"(\.(?:jpe?g|png|gif))_(?:\d+x\d+)?q\d+\.(?:jpe?g|webp)(?=\?|$)",
        r"\1",
        value,
        flags=re.I,
    )
    value = re.sub(
        r"(\.(?:jpe?g|png|gif))_\d+x\d+\.(?:jpe?g|webp)(?=\?|$)",
        r"\1",
        value,
        flags=re.I,
    )
    return value if value.startswith("https://") else None


def _clean_shop_url(shop_url):
    value = _optional_text(shop_url)
    if value is None:
        return None
    parsed = parse.urlparse(value)
    hostname = (parsed.hostname or "").casefold()
    if parsed.scheme != "https" or not any(
        hostname == suffix or hostname.endswith("." + suffix)
        for suffix in ("taobao.com", "tmall.com")
    ):
        return None
    return value[:2000]


def validate_shop_url(shop_url):
    """Return a safe public Taobao/Tmall shop URL for local browser capture."""
    value = _clean_shop_url(shop_url)
    if value is None:
        raise ValueError("店铺链接必须是 HTTPS 淘宝或天猫店铺链接")
    parsed = parse.urlparse(value)
    hostname = (parsed.hostname or "").casefold()
    if hostname in {
        "s.taobao.com", "item.taobao.com", "detail.tmall.com",
        "login.taobao.com", "login.tmall.com", "passport.taobao.com", "sec.taobao.com",
    }:
        raise ValueError("请输入店铺首页或店铺商品列表链接，不要使用搜索页或商品详情链接")
    functional_query_names = {"appuid", "user_number_id", "shop_id", "sellerid"}
    cleaned_query = parse.urlencode(
        [
            (name, value)
            for name, value in parse.parse_qsl(parsed.query, keep_blank_values=False)
            if name.casefold() in functional_query_names
        ]
    )
    return parse.urlunparse(("https", parsed.netloc, parsed.path or "/", parsed.params, cleaned_query, ""))


def normalize_browser_shop_capture(payload, *, expected_shop_url, expected_shop_name=None):
    if not isinstance(payload, dict):
        raise ValueError(f"browser shop capture must be an object: actual={payload!r}")
    page_url = _optional_text(payload.get("url")) or ""
    page_host = (parse.urlparse(page_url).hostname or "").casefold()
    title = _optional_text(payload.get("title")) or ""
    if payload.get("needsLogin") is True or page_host.startswith("login.") or title == "登录":
        return {"status": "login_required", "message": SHOP_LOGIN_MESSAGE, "products": []}
    if payload.get("blocked") is True or page_host in {"passport.taobao.com", "sec.taobao.com"}:
        return {"status": "blocked", "message": BLOCKED_MESSAGE, "products": []}
    if not _is_taobao_page_host(page_host):
        return {"status": "failed", "message": "采集浏览器没有停留在淘宝/天猫店铺页面。", "products": []}
    products = []
    seen = set()
    for raw_product in payload.get("products") or []:
        if not isinstance(raw_product, dict):
            continue
        item_id = str(raw_product.get("itemId") or "").strip()
        if not item_id.isdigit() or item_id in seen:
            continue
        product_url, _ = _canonical_product_url(raw_product.get("productUrl"), item_id)
        product_title = _optional_text(raw_product.get("title"))
        if not product_url or not product_title:
            continue
        seen.add(item_id)
        products.append({
            "item_id": item_id,
            "title": product_title,
            "product_url": product_url,
            "image_url": _clean_image_url(raw_product.get("image")),
            "price_text": _optional_text(raw_product.get("price")),
            "payment_text": _optional_text(raw_product.get("paymentText")),
        })
    if not products:
        return {
            "status": "failed",
            "message": "店铺页面已打开，但没有读取到商品。请切换到“全部宝贝”后重试。",
            "products": [],
        }
    shop_name = _optional_text(expected_shop_name) or re.sub(r"[-_｜|].*$", "", title).strip()
    return {
        "status": "success",
        "shop_url": validate_shop_url(expected_shop_url),
        "shop_name": shop_name or "淘宝店铺",
        "products": products,
        "result_count": len(products),
        "message": f"店铺商品清单读取完成，共 {len(products)} 件。",
    }


def _normalized_browser_reviews(payload):
    raw_reviews = payload if isinstance(payload, dict) else {}
    total_text = _optional_text(raw_reviews.get("totalText"))
    if total_text is not None:
        total_text = total_text[:80]

    tags = []
    seen_tags = set()
    for raw_tag in raw_reviews.get("tags") or []:
        tag_text = _optional_text(
            raw_tag.get("label") if isinstance(raw_tag, dict) else raw_tag
        )
        if tag_text is None or len(tag_text) > 40 or tag_text in seen_tags:
            continue
        seen_tags.add(tag_text)
        tags.append(tag_text)
        if len(tags) >= 20:
            break

    items = []
    seen_items = set()
    for raw_item in raw_reviews.get("items") or []:
        if not isinstance(raw_item, dict):
            continue
        content = _optional_text(raw_item.get("content"))
        if content is None or len(content) < 4:
            continue
        content = content[:1000]
        sku_text = _optional_text(raw_item.get("sku"))
        date_text = _optional_text(raw_item.get("date"))
        identity = (content, sku_text, date_text)
        if identity in seen_items:
            continue
        seen_items.add(identity)
        review_images = []
        for raw_url in raw_item.get("images") or []:
            image_url = _clean_image_url(raw_url)
            image_host = (parse.urlparse(image_url or "").hostname or "").casefold()
            if image_url and (
                image_host == "alicdn.com" or image_host.endswith(".alicdn.com")
            ):
                review_images.append(image_url)
            if len(review_images) >= 9:
                break
        items.append(
            {
                "content": content,
                "sku": sku_text,
                "date": date_text,
                "images": list(dict.fromkeys(review_images)),
            }
        )
        if len(items) >= PRODUCT_REVIEW_LIMIT:
            break
    return {
        "status": "captured" if total_text or tags or items else "not_exposed",
        "total_text": total_text,
        "tags": tags,
        "items": items,
        "next_page": (
            raw_reviews.get("nextPage")
            if isinstance(raw_reviews.get("nextPage"), int)
            and raw_reviews.get("nextPage") > 0
            else None
        ),
    }


def _normalized_text_list(values, *, limit, maximum_length=120):
    normalized = []
    seen = set()
    for raw_value in values or []:
        value = _optional_text(
            raw_value.get("label") if isinstance(raw_value, dict) else raw_value
        )
        if value is None or len(value) > maximum_length or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
        if len(normalized) >= limit:
            break
    return normalized


def _normalized_browser_product_fields(payload):
    raw_fields = payload if isinstance(payload, dict) else {}
    fields = {
        "title": _optional_text(raw_fields.get("title")),
        "subtitle": _optional_text(raw_fields.get("subtitle")),
        "price_text": _optional_text(raw_fields.get("priceText")),
        "original_price_text": _optional_text(raw_fields.get("originalPriceText")),
        "shop_name": _optional_text(raw_fields.get("shopName")),
        "sold_text": _optional_text(raw_fields.get("soldText")),
        "payment_text": _optional_text(raw_fields.get("paymentText")),
        "origin_text": _optional_text(raw_fields.get("originText")),
        "attributes_text": _optional_text(raw_fields.get("attributesText")),
        "promotions": _normalized_text_list(raw_fields.get("promotions"), limit=20),
        "services": _normalized_text_list(raw_fields.get("services"), limit=30),
        "logistics": _normalized_text_list(raw_fields.get("logistics"), limit=20),
    }
    for field_name in (
        "title",
        "subtitle",
        "price_text",
        "original_price_text",
        "shop_name",
        "sold_text",
        "payment_text",
        "origin_text",
    ):
        value = fields[field_name]
        if value is not None:
            fields[field_name] = value[:240]
    if fields["attributes_text"] is not None:
        fields["attributes_text"] = fields["attributes_text"][:8000]
    fields["status"] = (
        "captured"
        if any(value for key, value in fields.items() if key != "status")
        else "not_exposed"
    )
    return fields


def _normalized_browser_sku_catalog(payload):
    raw_catalog = payload if isinstance(payload, dict) else {}
    dimensions = []
    seen_labels = set()
    for raw_dimension in raw_catalog.get("dimensions") or []:
        if not isinstance(raw_dimension, dict):
            continue
        label = _optional_text(raw_dimension.get("label"))
        if label is None or len(label) > 80 or label in seen_labels:
            continue
        options = []
        seen_options = set()
        for raw_option in raw_dimension.get("options") or []:
            if not isinstance(raw_option, dict):
                continue
            value = _optional_text(raw_option.get("value"))
            if value is None or len(value) > 240 or value in seen_options:
                continue
            seen_options.add(value)
            options.append(
                {
                    "value": value,
                    "value_id": _optional_text(raw_option.get("valueId")),
                    "available": raw_option.get("available") is not False,
                    "selected": raw_option.get("selected") is True,
                    "image_url": _clean_image_url(raw_option.get("image")),
                    "price_text": _optional_text(raw_option.get("priceText")),
                }
            )
            if len(options) >= 200:
                break
        if not options:
            continue
        seen_labels.add(label)
        dimensions.append({"label": label, "options": options})
        if len(dimensions) >= 12:
            break
    has_sku = bool(dimensions)
    explicit_has_sku = raw_catalog.get("hasSku")
    return {
        "status": (
            "captured"
            if has_sku
            else "no_sku" if explicit_has_sku is False else "not_exposed"
        ),
        "has_sku": has_sku,
        "dimensions": dimensions,
        "selected_sku_id": _optional_text(raw_catalog.get("selectedSkuId")),
        "selected_price_text": _optional_text(raw_catalog.get("selectedPriceText")),
        "source": "browser_page",
    }


def _normalized_browser_questions(payload):
    raw_questions = payload if isinstance(payload, dict) else {}
    total_text = _optional_text(raw_questions.get("totalText"))
    items = []
    seen_questions = set()
    for raw_item in raw_questions.get("items") or []:
        if not isinstance(raw_item, dict):
            continue
        question = _optional_text(raw_item.get("question"))
        if question is None or len(question) < 2 or question in seen_questions:
            continue
        answers = []
        for raw_answer in raw_item.get("answers") or []:
            answer = _optional_text(
                raw_answer.get("content") if isinstance(raw_answer, dict) else raw_answer
            )
            if answer is not None and len(answer) >= 2:
                answers.append(answer[:1000])
            if len(answers) >= 10:
                break
        seen_questions.add(question)
        items.append(
            {
                "question": question[:500],
                "answer_count": _optional_text(raw_item.get("answerCount")),
                "answers": list(dict.fromkeys(answers)),
                "date": _optional_text(raw_item.get("date")),
            }
        )
        if len(items) >= PRODUCT_QUESTION_LIMIT:
            break
    return {
        "status": "captured" if total_text or items else "not_exposed",
        "total_text": total_text[:80] if total_text else None,
        "items": items,
    }


def _normalized_browser_videos(payload):
    videos = []
    seen_urls = set()
    for raw_video in payload or []:
        if not isinstance(raw_video, dict):
            continue
        video_url = _optional_text(raw_video.get("url"))
        poster_url = _clean_image_url(raw_video.get("poster"))
        parsed_video = parse.urlparse(video_url or "")
        video_host = (parsed_video.hostname or "").casefold()
        if (
            not video_url
            or parsed_video.scheme != "https"
            or not any(
                video_host == suffix or video_host.endswith("." + suffix)
                for suffix in ("taobao.com", "tmall.com", "alicdn.com", "tbcdn.cn")
            )
            or video_url in seen_urls
        ):
            continue
        seen_urls.add(video_url)
        videos.append({"url": video_url, "poster_url": poster_url})
        if len(videos) >= 10:
            break
    return videos


def normalize_browser_search_capture(payload, *, expected_keyword, expected_page_number):
    if not isinstance(payload, dict):
        raise ValueError(f"browser search capture must be an object: actual={payload!r}")
    page_url = _optional_text(payload.get("url")) or ""
    page_host = (parse.urlparse(page_url).hostname or "").casefold()
    title = _optional_text(payload.get("title")) or ""
    if payload.get("needsLogin") is True or page_host.startswith("login.") or title == "登录":
        return {
            "status": "login_required",
            "message": (
                FIRST_PAGE_LOGIN_MESSAGE
                if expected_page_number == 1
                else LOGIN_MESSAGE
            ),
        }
    if payload.get("blocked") is True or page_host in {"passport.taobao.com", "sec.taobao.com"}:
        return {"status": "blocked", "message": BLOCKED_MESSAGE}
    if page_host != "s.taobao.com":
        return {
            "status": "failed",
            "message": "采集浏览器没有停留在淘宝搜索结果页，请关闭其他采集页后重试。",
        }

    raw_current_page = payload.get("currentPage")
    if raw_current_page is not None and int(raw_current_page) != expected_page_number:
        return {
            "status": "failed",
            "message": f"淘宝返回的页码与请求不一致，期望第{expected_page_number}页，已停止保存。",
        }

    products = []
    seen_item_ids = set()
    for raw_product in payload.get("products") or []:
        if not isinstance(raw_product, dict):
            continue
        item_id = str(raw_product.get("itemId") or "").strip()
        if not item_id.isdigit() or int(item_id) <= 0 or item_id in seen_item_ids:
            continue
        product_url, platform_type = _canonical_product_url(
            raw_product.get("productUrl"), item_id
        )
        title_text = _optional_text(raw_product.get("title"))
        if product_url is None or title_text is None:
            continue
        seen_item_ids.add(item_id)
        products.append(
            {
                "item_id": item_id,
                "sku_id": _optional_text(raw_product.get("skuId")),
                "title": title_text,
                "shop_name": _optional_text(raw_product.get("shopName")),
                "display_price": _optional_text(raw_product.get("price")),
                "product_url": product_url,
                "shop_url": _clean_shop_url(raw_product.get("shopUrl")),
                "image_url": _clean_image_url(raw_product.get("image")),
                "platform_type": platform_type,
                "suspected_ad": (
                    1 if raw_product.get("suspectedAd") is True else None
                ),
                "payment_text": _optional_text(raw_product.get("paymentText")),
                "origin_text": _optional_text(raw_product.get("originText")),
                "promotion_text": _optional_text(raw_product.get("promotionText")),
                "logistics_text": _optional_text(raw_product.get("logisticsText")),
                "card_text": _optional_text(raw_product.get("cardText")),
            }
        )

    has_next_page = bool(payload.get("hasNextPage"))
    if not products:
        return {
            "status": "exhausted" if not has_next_page else "failed",
            "page_number": expected_page_number,
            "message": (
                "已经到淘宝搜索结果的最后一页。"
                if not has_next_page
                else "淘宝页面没有读取到有效商品，本次未保存，请稍后重试。"
            ),
            "products": [],
            "has_next_page": False,
        }
    return {
        "status": "success",
        "page_number": expected_page_number,
        "keyword": str(expected_keyword).strip(),
        "products": products,
        "has_next_page": has_next_page,
        "message": f"淘宝第{expected_page_number}页读取完成。",
    }


def normalize_browser_product_capture(payload, *, expected_item_id):
    """Validate and normalize the public archive captured from one product page."""
    if not isinstance(payload, dict):
        raise ValueError(f"browser product capture must be an object: actual={payload!r}")
    expected_item_id = str(expected_item_id or "").strip()
    if not expected_item_id.isdigit() or int(expected_item_id) <= 0:
        raise ValueError(f"expected_item_id must be numeric: actual={expected_item_id!r}")

    page_url = _optional_text(payload.get("url")) or ""
    parsed_page = parse.urlparse(page_url)
    page_host = (parsed_page.hostname or "").casefold()
    if payload.get("needsLogin") is True or page_host in {"login.taobao.com", "login.tmall.com"}:
        return {
            "status": "login_required",
            "message": PRODUCT_LOGIN_MESSAGE,
            "images": [],
        }
    if payload.get("blocked") is True or page_host == "sec.taobao.com":
        return {"status": "blocked", "message": BLOCKED_MESSAGE, "images": []}

    actual_item_id = (parse.parse_qs(parsed_page.query).get("id") or [""])[0]
    if page_host not in {"item.taobao.com", "detail.tmall.com"} or actual_item_id != expected_item_id:
        return {
            "status": "failed",
            "message": "采集页不是当前选择的商品，已停止保存图片。",
            "images": [],
        }

    source_kinds = {
        "structured_main": "main",
        "structured_gallery": "main",
        "dom_gallery": "main",
        "picture_gallery": "main",
        "css_gallery": "main",
        "structured_sku": "sku",
        "dom_sku": "sku",
        "detail_api": "detail",
        "dom_detail": "detail",
    }
    images = []
    # A picture may legitimately be both a top-gallery image and an SKU image.
    # Deduplicate inside each semantic group instead of allowing an earlier SKU
    # classification to hide a real main image.
    seen_urls_by_kind = {"main": set(), "sku": set(), "detail": set()}
    # The product hero is the top "图集" and is intentionally capped at five
    # images.  Keeping this boundary here prevents detail/review artwork from
    # leaking into the main-image group when Taobao changes CSS class names.
    image_limits = {"main": 5, "sku": 160, "detail": 120}
    image_counts = {"main": 0, "sku": 0, "detail": 0}
    for raw_image in payload.get("images") or []:
        if not isinstance(raw_image, dict):
            continue
        image_url = _clean_image_url(raw_image.get("url"))
        if image_url is None:
            continue
        image_host = (parse.urlparse(image_url).hostname or "").casefold()
        if not any(
            image_host == suffix or image_host.endswith("." + suffix)
            for suffix in ("alicdn.com", "tbcdn.cn", "taobaocdn.com")
        ):
            continue
        if re.search(
            r"(?:placeholder|loading|transparent|sprite|atmosphere|badge|icon|logo|"
            r"/sns_logo/|-ggpersonal|"
            r"-rate(?:\.|_)|[/-]\d+[-_]tps[-_]|[/-]tps[-_])",
            image_url,
            re.I,
        ):
            continue
        source = str(raw_image.get("source") or "").casefold()
        kind = source_kinds.get(source)
        if kind is None:
            continue
        width = raw_image.get("width")
        height = raw_image.get("height")
        if source in {"dom_gallery", "picture_gallery", "css_gallery"}:
            if not all(
                isinstance(value, (int, float)) and value >= 70
                for value in (width, height)
            ):
                continue
            aspect_ratio = width / max(height, 1)
            if aspect_ratio < 0.45 or aspect_ratio > 2.2:
                continue
        if source == "dom_sku" and any(
            isinstance(value, (int, float)) and value < 36 for value in (width, height)
        ):
            continue
        if source == "dom_detail":
            if not all(
                isinstance(value, (int, float)) and value >= 300
                for value in (width, height)
            ):
                continue
        if image_url in seen_urls_by_kind[kind]:
            continue
        if image_counts[kind] >= image_limits[kind]:
            continue
        seen_urls_by_kind[kind].add(image_url)
        images.append({"url": image_url, "kind": kind})
        image_counts[kind] += 1

    product_fields = _normalized_browser_product_fields(payload.get("product"))
    reviews = _normalized_browser_reviews(payload.get("reviews"))
    sku_catalog = _normalized_browser_sku_catalog(payload.get("skuCatalog"))
    questions = _normalized_browser_questions(payload.get("questions"))
    videos = _normalized_browser_videos(payload.get("videos"))
    has_archive_data = any(
        (
            images,
            product_fields["status"] == "captured",
            reviews["status"] == "captured",
            sku_catalog["status"] in {"captured", "no_sku"},
            questions["status"] == "captured",
            videos,
        )
    )
    if not has_archive_data:
        return {
            "status": "failed",
            "message": "商品页已打开，但没有读取到可用详情数据；已保留原有采集结果。",
            "images": [],
        }
    captured_modules = sum(
        bool(value)
        for value in (
            images,
            product_fields["status"] == "captured",
            reviews["status"] == "captured",
            sku_catalog["status"] in {"captured", "no_sku"},
            questions["status"] == "captured",
            videos,
        )
    )
    return {
        "status": "success",
        "message": f"已读取 {captured_modules} 个商品数据模块、{len(images)} 张商品图片。",
        "title": _optional_text(payload.get("title")),
        "images": images,
        "product_fields": product_fields,
        "sku_catalog": sku_catalog,
        "reviews": reviews,
        "questions": questions,
        "videos": videos,
        "coverage": {
            "basic": product_fields["status"],
            "images": "captured" if images else "not_exposed",
            "sku": sku_catalog["status"],
            "reviews": reviews["status"],
            "questions": questions["status"],
            "videos": "captured" if videos else "not_exposed",
        },
    }


def _chrome_candidates():
    paths = []
    for environment_name in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        base = os.environ.get(environment_name)
        if not base:
            continue
        paths.extend(
            [
                Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe",
                Path(base) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
            ]
        )
    return paths


def installed_browser_executable():
    executable = next((path for path in _chrome_candidates() if path.is_file()), None)
    if executable is None:
        raise RuntimeError("未检测到 Google Chrome 或 Microsoft Edge，请先安装其中一个浏览器。")
    return executable


def _cdp_json(path, timeout=1.5):
    with request.urlopen(
        f"http://127.0.0.1:{SEARCH_BROWSER_PORT}{path}", timeout=timeout
    ) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def _cdp_ready():
    try:
        payload = _cdp_json("/json/version")
        return isinstance(payload, dict) and bool(payload.get("webSocketDebuggerUrl"))
    except Exception:
        return False


def _page_targets():
    try:
        payload = _cdp_json("/json/list", timeout=2.0)
    except Exception:
        return []
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict) and item.get("type") == "page"]


def _target_for_search_browser():
    pages = _page_targets()
    allowed = []
    for page in pages:
        hostname = (parse.urlparse(str(page.get("url") or "")).hostname or "").casefold()
        if hostname in TAOBAO_SEARCH_HOSTS or _is_taobao_page_host(hostname):
            allowed.append(page)
    if allowed:
        host_priority = {
            "s.taobao.com": 0,
            "login.taobao.com": 1,
            "login.tmall.com": 1,
            "passport.taobao.com": 1,
            "sec.taobao.com": 1,
            "item.taobao.com": 2,
            "detail.tmall.com": 2,
        }
        return min(
            allowed,
            key=lambda page: host_priority.get(
                (parse.urlparse(str(page.get("url") or "")).hostname or "").casefold(),
                9,
            ),
        )
    return pages[0] if len(pages) == 1 else None


def _launch_search_browser(application_data_directory, target_url):
    executable = installed_browser_executable()
    profile_directory = Path(application_data_directory) / "browser" / "taobao-search-profile"
    profile_directory.mkdir(parents=True, exist_ok=True)
    command = [
        str(executable),
        f"--remote-debugging-port={SEARCH_BROWSER_PORT}",
        "--remote-debugging-address=127.0.0.1",
        f"--user-data-dir={profile_directory}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-sync",
        "--new-window",
        target_url,
    ]
    options = {
        "cwd": str(Path(application_data_directory)),
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if os.name == "nt":
        options["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    subprocess.Popen(command, **options)
    for _ in range(30):
        if _cdp_ready():
            return
        time.sleep(0.25)
    raise RuntimeError("采集浏览器已经打开，但本机安全连接未能建立，请关闭采集窗口后重试。")


def _collector_profile_directory(application_data_directory):
    root = Path(application_data_directory).resolve()
    profile = (root / "browser" / "taobao-search-profile").resolve()
    if root not in profile.parents:
        raise RuntimeError("采集浏览器目录超出应用数据范围，已停止操作。")
    return profile


def open_collector_account_browser(application_data_directory):
    login_url = "https://login.taobao.com/member/login.jhtml"
    if not _cdp_ready() or _target_for_search_browser() is None:
        _launch_search_browser(application_data_directory, login_url)
    else:
        target = _target_for_search_browser()
        _activate_target(target)
        current_host = (
            parse.urlparse(str(target.get("url") or "")).hostname or ""
        ).casefold()
        if current_host not in {
            "login.taobao.com",
            "login.tmall.com",
            "passport.taobao.com",
        }:
            _navigate_target(target, login_url)
    return {
        "status": "opened",
        "message": "采集账号浏览器已打开。请在淘宝官方页面查看当前账号、退出或登录其他账号。",
    }


def clear_collector_login_profile(application_data_directory):
    if _cdp_ready():
        raise RuntimeError("请先关闭专属采集浏览器，再清除本工具登录状态。")
    profile = _collector_profile_directory(application_data_directory)
    if profile.exists():
        shutil.rmtree(profile)
    return {
        "cleared": True,
        "message": "本工具的淘宝采集登录状态已清除；其他浏览器和淘宝客户端不受影响。",
    }


def _websocket_client_frame(payload, opcode=0x1):
    payload = payload if isinstance(payload, bytes) else str(payload).encode("utf-8")
    mask = os.urandom(4)
    length = len(payload)
    if length < 126:
        header = bytes((0x80 | opcode, 0x80 | length))
    elif length <= 0xFFFF:
        header = bytes((0x80 | opcode, 0x80 | 126)) + struct.pack("!H", length)
    else:
        header = bytes((0x80 | opcode, 0x80 | 127)) + struct.pack("!Q", length)
    masked = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
    return header + mask + masked


def _receive_exact(connection, length):
    chunks = []
    remaining = length
    while remaining:
        chunk = connection.recv(remaining)
        if not chunk:
            raise RuntimeError("采集浏览器提前断开了连接。")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _receive_frame(connection, max_payload=16 * 1024 * 1024):
    first, second = _receive_exact(connection, 2)
    final = bool(first & 0x80)
    opcode = first & 0x0F
    masked = bool(second & 0x80)
    length = second & 0x7F
    if length == 126:
        length = struct.unpack("!H", _receive_exact(connection, 2))[0]
    elif length == 127:
        length = struct.unpack("!Q", _receive_exact(connection, 8))[0]
    if length > max_payload:
        raise RuntimeError("淘宝页面返回的数据过大，本次已停止读取。")
    mask = _receive_exact(connection, 4) if masked else b""
    payload = _receive_exact(connection, length)
    if mask:
        payload = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
    return final, opcode, payload


def _cdp_evaluate(target, expression, timeout=20):
    websocket_url = str(target.get("webSocketDebuggerUrl") or "")
    if not websocket_url:
        raise RuntimeError("无法建立采集页读取连接，请关闭采集窗口后重试。")
    parsed_url = parse.urlparse(websocket_url)
    host = parsed_url.hostname or "127.0.0.1"
    port = parsed_url.port or 80
    path = parsed_url.path or "/"
    if parsed_url.query:
        path += "?" + parsed_url.query
    key = base64.b64encode(os.urandom(16)).decode("ascii")
    expected_accept = base64.b64encode(
        hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")).digest()
    ).decode("ascii")
    handshake = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n\r\n"
    ).encode("ascii")
    with socket.create_connection((host, port), timeout=timeout) as connection:
        connection.settimeout(timeout)
        connection.sendall(handshake)
        response = b""
        while b"\r\n\r\n" not in response and len(response) < 65536:
            response += _receive_exact(connection, 1)
        header_text = response.decode("iso-8859-1", errors="replace")
        if not header_text.startswith("HTTP/1.1 101") or expected_accept.casefold() not in header_text.casefold():
            raise RuntimeError("采集浏览器拒绝了本机读取连接。")
        command = json.dumps(
            {
                "id": 1,
                "method": "Runtime.evaluate",
                "params": {
                    "expression": expression,
                    "awaitPromise": True,
                    "returnByValue": True,
                },
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        connection.sendall(_websocket_client_frame(command))
        fragments = bytearray()
        text_opcode = None
        while True:
            final, opcode, payload = _receive_frame(connection)
            if opcode == 0x9:
                connection.sendall(_websocket_client_frame(payload, opcode=0xA))
                continue
            if opcode == 0x8:
                raise RuntimeError("采集浏览器在返回结果前关闭了连接。")
            if opcode in {0x1, 0x2}:
                text_opcode = opcode
                fragments = bytearray(payload)
            elif opcode == 0x0 and text_opcode is not None:
                fragments.extend(payload)
            else:
                continue
            if not final:
                continue
            if text_opcode != 0x1:
                fragments = bytearray()
                text_opcode = None
                continue
            message = json.loads(bytes(fragments).decode("utf-8", errors="replace"))
            fragments = bytearray()
            text_opcode = None
            if message.get("id") != 1:
                continue
            result = message.get("result") or {}
            if message.get("error") or result.get("exceptionDetails"):
                raise RuntimeError("淘宝页面读取脚本执行失败。")
            return (result.get("result") or {}).get("value")


def _navigate_target(target, target_url):
    encoded_url = json.dumps(target_url, ensure_ascii=False)
    try:
        _cdp_evaluate(target, f"location.assign({encoded_url}); true", timeout=5)
        return
    except (RuntimeError, OSError, socket.timeout) as navigation_error:
        # A successful location.assign can tear down the old execution context
        # before CDP returns its value. Confirm the new public URL before treating
        # that expected disconnect as a failed navigation.
        expected = parse.urlparse(target_url)
        expected_query = parse.parse_qs(expected.query)
        for _ in range(24):
            time.sleep(0.25)
            current = _target_for_search_browser()
            if not current:
                continue
            actual = parse.urlparse(str(current.get("url") or ""))
            actual_host = (actual.hostname or "").casefold()
            if actual_host in {
                "login.taobao.com",
                "login.tmall.com",
                "passport.taobao.com",
                "sec.taobao.com",
            }:
                return
            actual_query = parse.parse_qs(actual.query)
            if (expected.hostname or "").casefold() == "s.taobao.com":
                if (
                    actual_host == "s.taobao.com"
                    and actual_query.get("q") == expected_query.get("q")
                    and actual_query.get("s", ["0"]) == expected_query.get("s", ["0"])
                ):
                    return
            elif (
                actual_host in {"item.taobao.com", "detail.tmall.com"}
                and actual_query.get("id") == expected_query.get("id")
            ):
                return
            elif (
                _is_taobao_page_host(actual_host)
                and actual_host == (expected.hostname or "").casefold()
                and actual.path.rstrip("/") == expected.path.rstrip("/")
            ):
                return
        raise navigation_error


def _visible_search_item_ids(target):
    """Read current search-card ids without scrolling or exporting browser state."""
    expression = r"""
(() => {
  const ids = [];
  const seen = new Set();
  for (const anchor of document.querySelectorAll("a[href]")) {
    const href = String(anchor.href || "");
    if (!/(item\.taobao\.com\/item\.htm|detail\.tmall\.com\/item\.htm|click\.simba\.taobao\.com)/i.test(href)) continue;
    let itemId = "";
    try {
      const parsed = new URL(href, location.href);
      itemId = parsed.searchParams.get("id") || parsed.searchParams.get("itemId") || "";
      if (!/^\d+$/.test(itemId)) {
        const match = decodeURIComponent(href).match(/[?&](?:id|itemId)=(\d+)/i);
        itemId = match ? match[1] : "";
      }
    } catch (_) {}
    if (itemId && !seen.has(itemId)) {
      seen.add(itemId);
      ids.push(itemId);
    }
  }
  return ids.slice(0, 100);
})()
"""
    value = _cdp_evaluate(target, expression, timeout=5)
    if not isinstance(value, list):
        return set()
    return {
        str(item_id).strip()
        for item_id in value
        if str(item_id).strip().isdigit()
    }


def _click_search_page_control(target, page_number):
    encoded_page = json.dumps(str(page_number))
    expression = rf"""
(() => {{
  const wanted = {encoded_page};
  const norm = (value) => String(value || "").replace(/\s+/g, " ").trim();
  const controls = Array.from(document.querySelectorAll("a,button,[role='button']"));
  const numeric = controls.find((node) => (
    norm(node.innerText || node.getAttribute("aria-label")) === wanted
    && /pagination|pager|page/i.test(String(node.className || ""))
  ));
  const target = numeric || controls.find((node) => (
    norm(node.innerText || node.getAttribute("aria-label")) === wanted
  ));
  if (!target) return false;
  const disabled = target.disabled
    || target.getAttribute("aria-disabled") === "true"
    || /disabled/.test(String(target.className || ""));
  if (disabled) return false;
  target.scrollIntoView({{ block: "center", inline: "center" }});
  target.click();
  return true;
}})()
"""
    return _cdp_evaluate(target, expression, timeout=5) is True


def _capture_expression():
    return r"""
(async () => {
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const norm = (value) => String(value || "").replace(/\s+/g, " ").trim();
  const bodyText = norm(document.body ? document.body.innerText : "");
  const lowerUrl = location.href.toLowerCase();
  const loginPattern = /(扫码登录|密码登录|短信登录|请登录|login\.taobao|login\.tmall)/i;
  const blockedPattern = /(安全验证|身份验证|访问受限|验证码|滑块|captcha|sec\.taobao|passport\.taobao)/i;
  if (loginPattern.test(bodyText) || lowerUrl.includes("login.taobao") || lowerUrl.includes("login.tmall")) {
    return { url: location.href, title: document.title, needsLogin: true, products: [] };
  }
  if (blockedPattern.test(bodyText) || lowerUrl.includes("sec.taobao")) {
    return { url: location.href, title: document.title, blocked: true, products: [] };
  }
  let stableRounds = 0;
  let previousHeight = 0;
  for (let step = 0; step < 12; step += 1) {
    const root = document.scrollingElement || document.documentElement;
    const height = Math.max(root.scrollHeight, document.body ? document.body.scrollHeight : 0);
    window.scrollTo(0, Math.min(height, (step + 1) * Math.max(window.innerHeight * 0.85, 700)));
    await sleep(180);
    stableRounds = height === previousHeight ? stableRounds + 1 : 0;
    previousHeight = height;
    if (stableRounds >= 2 && window.scrollY + window.innerHeight >= height - 40) break;
  }
  await sleep(500);
  const itemIdFromUrl = (href) => {
    try {
      const parsed = new URL(href, location.href);
      const direct = parsed.searchParams.get("id") || parsed.searchParams.get("itemId");
      if (direct && /^\d+$/.test(direct)) return direct;
      const decoded = decodeURIComponent(href);
      const match = decoded.match(/[?&](?:id|itemId)=(\d+)/i);
      return match ? match[1] : "";
    } catch (_) {
      return "";
    }
  };
  const priceFromText = (text) => {
    const match = norm(text).match(/(?:￥|¥)\s*(\d{1,7})(?:\s*\.\s*(\d{1,2}))?/);
    if (!match) return "";
    return match[2] ? `${match[1]}.${match[2]}` : match[1];
  };
  const firstMatch = (text, pattern) => {
    const match = norm(text).match(pattern);
    return match ? norm(match[1] || match[0]) : "";
  };
  const allMatches = (text, pattern) => Array.from(norm(text).matchAll(pattern))
    .map((match) => norm(match[1] || match[0]))
    .filter((value, index, values) => value && values.indexOf(value) === index)
    .join(" · ");
  const shopNameFromCard = (shopLink, cardText) => {
    const linkedText = shopLink ? norm(shopLink.innerText || shopLink.textContent) : "";
    const trailingShop = (linkedText || cardText).match(
      /([A-Za-z0-9\u4e00-\u9fa5·（）()\-]{2,40}(?:旗舰店|专卖店|专营店|官方店|品牌店|企业店|工厂店))\s*$/,
    );
    if (trailingShop) return norm(trailingShop[1]);
    return linkedText
      .replace(/^(?:(?:回头客\s*\d+(?:\.\d+)?万?|\d+年老店)\s*)+/, "")
      .trim();
  };
  const titleFromCard = (anchor, titleNode, image, cardText) => {
    const cleanTitle = (text) => norm(text)
      .split(/(?:￥|¥|补贴后|优惠后|券后|\d+(?:\.\d+)?万?\+?人付款|已售\s*\d+)/)[0]
      .replace(/^(?:广告|天猫|淘宝)\s*/, "")
      .trim();
    const candidates = [
      anchor.getAttribute("title"),
      titleNode && (titleNode.getAttribute("title") || titleNode.innerText),
      image && image.getAttribute("alt"),
    ].map(cleanTitle).filter((text) => text.length >= 6 && text.length <= 180);
    if (candidates.length) return candidates[0];
    const fallback = cleanTitle(anchor.innerText || cardText);
    return fallback.length >= 6 && fallback.length <= 180 ? fallback : "";
  };
  const productImageFromCard = (card, anchor, itemId) => {
    const candidates = Array.from(new Set([
      ...Array.from(card.querySelectorAll("img")),
      ...Array.from(anchor.querySelectorAll("img")),
    ]));
    let best = null;
    for (const image of candidates) {
      const url = String(
        image.currentSrc
        || image.src
        || image.dataset?.src
        || image.dataset?.lazyload
        || image.getAttribute("data-ks-lazyload")
        || image.getAttribute("data-original")
        || ""
      ).trim();
      if (!/^https?:\/\//i.test(url)) continue;
      const rectangle = image.getBoundingClientRect();
      const displayWidth = Math.max(Number(rectangle.width || 0), Number(image.width || 0));
      const displayHeight = Math.max(Number(rectangle.height || 0), Number(image.height || 0));
      const naturalWidth = Number(image.naturalWidth || 0);
      const naturalHeight = Number(image.naturalHeight || 0);
      const effectiveWidth = Math.max(displayWidth, naturalWidth);
      const effectiveHeight = Math.max(displayHeight, naturalHeight);
      if (Math.min(effectiveWidth, effectiveHeight) < 56) continue;
      const ratio = effectiveWidth / Math.max(effectiveHeight, 1);
      const lowerUrl = url.toLowerCase();
      let score = 0;
      if (Math.min(displayWidth, displayHeight) >= 100) score += 110;
      else if (Math.min(displayWidth, displayHeight) >= 72) score += 45;
      if (Math.min(naturalWidth, naturalHeight) >= 300) score += 65;
      else if (Math.min(naturalWidth, naturalHeight) >= 160) score += 30;
      if (ratio >= 0.68 && ratio <= 1.45) score += 80;
      else if (ratio < 0.45 || ratio > 2.2) score -= 180;
      const imageAnchor = image.closest("a[href]");
      if (imageAnchor && itemIdFromUrl(imageAnchor.href) === itemId) score += 100;
      if (/\.(?:jpe?g|webp)(?:_|\?|$)/i.test(lowerUrl)) score += 20;
      if (/(?:\/bao\/uploaded\/|\/imgextra\/)/i.test(lowerUrl)) score += 15;
      if (/(?:atmosphere|[-_/]tps[-_/]|sprite|badge|icon|logo)/i.test(lowerUrl)) score -= 260;
      if (best === null || score > best.score) best = { image, url, score };
    }
    return best && best.score >= 80 ? best : null;
  };
  const productLinks = Array.from(document.querySelectorAll("a[href]"))
    .filter((anchor) => /(item\.taobao\.com\/item\.htm|detail\.tmall\.com\/item\.htm|click\.simba\.taobao\.com)/i.test(anchor.href));
  const products = [];
  const seen = new Set();
  for (const anchor of productLinks) {
    const itemId = itemIdFromUrl(anchor.href);
    if (!itemId || seen.has(itemId)) continue;
    const card = anchor.closest("[class*='Card--'],[class*='doubleCard'],[class*='item-card'],[class*='ItemCard'],[data-index]")
      || anchor.parentElement?.parentElement?.parentElement || anchor.parentElement;
    if (!card) continue;
    const productImage = productImageFromCard(card, anchor, itemId);
    const image = productImage?.image || null;
    const titleNode = card.querySelector("[class*='title'],[class*='Title'],[title]");
    const cardText = norm(card.innerText);
    const title = titleFromCard(anchor, titleNode, image, cardText);
    if (!title) continue;
    const shopLink = card.querySelector("a[href*='shop.taobao.com'],a[href*='store.taobao.com'],a[href*='tmall.com/shop'],a[href*='shop'],a[href*='store']");
    const imageUrl = productImage?.url || "";
    const paymentText = firstMatch(
      cardText,
      /(\d+(?:\.\d+)?(?:万|千)?\+?\s*人(?:付款|收货)|已售\s*\d+(?:\.\d+)?(?:万|千)?\+?)/i,
    );
    const originText = firstMatch(
      cardText,
      /(?:^|\s)((?:北京|上海|天津|重庆|河北|山西|辽宁|吉林|黑龙江|江苏|浙江|安徽|福建|江西|山东|河南|湖北|湖南|广东|海南|四川|贵州|云南|陕西|甘肃|青海|内蒙古|广西|西藏|宁夏|新疆|香港|澳门|台湾)(?:\s+[\u4e00-\u9fa5]{1,8})?)(?=\s|$)/,
    );
    const promotionText = allMatches(
      cardText,
      /((?:补贴后|优惠后|券后|满减|官方立减\s*\d+(?:\.\d+)?%?|国家补贴|热销爆款))/g,
    );
    const logisticsText = allMatches(
      cardText,
      /((?:次日达|当日达|包邮|\d+小时内发|退货宝))/g,
    );
    const shopName = shopNameFromCard(shopLink, cardText);
    seen.add(itemId);
    products.push({
      itemId,
      skuId: (() => { try { return new URL(anchor.href, location.href).searchParams.get("skuId") || ""; } catch (_) { return ""; } })(),
      title,
      shopName,
      shopUrl: shopLink ? shopLink.href : "",
      price: priceFromText(cardText),
      productUrl: anchor.href,
      image: imageUrl,
      suspectedAd: anchor.href.includes("click.simba.taobao.com"),
      paymentText,
      originText,
      promotionText,
      logisticsText,
      cardText: cardText.slice(0, 800),
    });
  }
  const nextControls = Array.from(document.querySelectorAll("a,button,[role='button']"))
    .filter((node) => /^(下一页|下一頁|下页|>)$/.test(norm(node.innerText || node.getAttribute("aria-label"))));
  const hasNextPage = nextControls.some((node) => {
    const disabled = node.disabled || node.getAttribute("aria-disabled") === "true" || /disabled/.test(String(node.className || ""));
    return !disabled;
  });
  const activePageControl = Array.from(document.querySelectorAll("a,button,[role='button']"))
    .find((node) => {
      const className = String(node.className || "");
      const text = norm(node.innerText || node.getAttribute("aria-label"));
      return /^\d+$/.test(text) && /(?:next-current|is-current|active|selected)/i.test(className);
    });
  const activePageNumber = activePageControl
    ? Number(norm(activePageControl.innerText || activePageControl.getAttribute("aria-label")))
    : 0;
  const offset = Number(new URL(location.href).searchParams.get("s") || 0);
  const offsetPageNumber = Math.floor(offset / 48) + 1;
  window.scrollTo(0, 0);
  return {
    url: location.href,
    title: document.title,
    currentPage: offset > 0 ? offsetPageNumber : (activePageNumber || offsetPageNumber),
    needsLogin: false,
    blocked: false,
    hasNextPage: hasNextPage || products.length >= 20,
    products: products.slice(0, 80),
  };
})()
"""


def _product_image_capture_expression(review_start_page=1):
    # This deliberately runs inside the logged-in, user-visible Taobao page. It reads
    # public page state only and never exports cookies or browser credentials.
    if (
        not isinstance(review_start_page, int)
        or isinstance(review_start_page, bool)
        or review_start_page < 1
    ):
        raise ValueError(
            f"review_start_page must be a positive integer: actual={review_start_page!r}"
        )
    expression = r"""
(async () => {
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const norm = (value) => String(value || "").replace(/\s+/g, " ").trim();
  const bodyText = norm(document.body ? document.body.innerText : "");
  const lowerUrl = location.href.toLowerCase();
  const loginPattern = /(扫码登录|密码登录|短信登录|请登录|login\.taobao|login\.tmall)/i;
  const blockedPattern = /(安全验证|访问受限|验证码|滑块|captcha|sec\.taobao)/i;
  if (loginPattern.test(bodyText) || lowerUrl.includes("login.taobao") || lowerUrl.includes("login.tmall")) {
    return { url: location.href, title: document.title, needsLogin: true, images: [] };
  }
  if (blockedPattern.test(bodyText) || lowerUrl.includes("sec.taobao")) {
    return { url: location.href, title: document.title, blocked: true, images: [] };
  }

  const images = [];
  const seen = new Set();
  const clean = (value) => {
    let url = String(value || "").trim();
    if (url.startsWith("//")) url = "https:" + url;
    return url;
  };
  const add = (url, source, node = null) => {
    url = clean(url);
    const role = /(?:main|gallery)/i.test(source) ? "main"
      : /sku/i.test(source) ? "sku"
      : /detail/i.test(source) ? "detail"
      : "unknown";
    const identity = `${role}:${url}`;
    if (source === "dom_unknown" || !/^https:\/\//i.test(url) || seen.has(identity)) return;
    seen.add(identity);
    images.push({
      url,
      source,
      width: Number(node?.naturalWidth || node?.width || 0),
      height: Number(node?.naturalHeight || node?.height || 0),
      alt: norm(node?.alt || ""),
    });
  };

  const appData = window.__ICE_APP_CONTEXT__?.loaderData?.home?.data?.res
    || window.__ICE_APP_CONTEXT__?.loaderData?.home?.data
    || null;
  const structuredRoots = [appData, appData?.data, appData?.data?.data].filter(Boolean);
  const readPath = (root, path) => path.split(".").reduce((value, key) => value?.[key], root);
  const firstStructured = (paths) => {
    for (const root of structuredRoots) {
      for (const path of paths) {
        const value = readPath(root, path);
        if (value !== undefined && value !== null && norm(value)) return norm(value);
      }
    }
    return "";
  };
  const firstDomText = (selectors) => {
    for (const selector of selectors) {
      const node = document.querySelector(selector);
      const value = norm(node?.innerText || node?.textContent || node?.getAttribute?.("content"));
      if (value) return value;
    }
    return "";
  };
  const skuCatalog = { hasSku: null, dimensions: [], selectedSkuId: "", selectedPriceText: "" };
  const seenSkuLabels = new Set();
  for (const taobaoData of structuredRoots) {
    for (const image of (taobaoData?.item?.images || [])) {
      add(typeof image === "string" ? image : (image?.url || image?.image), "structured_main");
    }
    for (const path of [
      "item.gallery", "item.picList", "item.imageList", "item.imageInfos",
      "gallery.images", "gallery.picList", "gallery",
    ]) {
      const gallery = readPath(taobaoData, path);
      if (!Array.isArray(gallery)) continue;
      for (const image of gallery) {
        add(
          typeof image === "string"
            ? image
            : (image?.url || image?.image || image?.picUrl || image?.imageUrl || image?.src),
          "structured_gallery",
        );
      }
    }
    for (const prop of (taobaoData?.skuBase?.props || [])) {
      const label = norm(prop?.name || prop?.label || prop?.propName || "");
      const options = [];
      const seenValues = new Set();
      for (const value of (prop?.values || [])) {
        add(value?.image, "structured_sku");
        const optionName = norm(value?.name || value?.value || value?.text || value?.label || "");
        if (!optionName || seenValues.has(optionName)) continue;
        seenValues.add(optionName);
        options.push({
          value: optionName,
          valueId: norm(value?.vid || value?.valueId || value?.id || ""),
          image: value?.image || "",
          available: value?.disabled !== true && value?.status !== "disabled",
          selected: value?.selected === true,
          priceText: norm(value?.priceText || value?.price || ""),
        });
      }
      if (label && options.length && !seenSkuLabels.has(label)) {
        seenSkuLabels.add(label);
        skuCatalog.dimensions.push({ label, options });
      }
    }
    if (skuCatalog.dimensions.length) skuCatalog.hasSku = true;
    const skuId = new URL(location.href).searchParams.get("skuId") || "";
    if (skuId) {
      skuCatalog.selectedSkuId = skuId;
      const skuInfo = taobaoData?.skuCore?.sku2info?.[skuId]
        || taobaoData?.skuCore?.sku2Info?.[skuId]
        || null;
      skuCatalog.selectedPriceText = norm(
        skuInfo?.price?.priceText || skuInfo?.price?.price || skuInfo?.priceText || "",
      );
    }
  }

  const gallerySelector = [
    "[class*='gallery']", "[class*='Gallery']",
    "[class*='album']", "[class*='Album']",
    "[class*='thumb']", "[class*='Thumb']",
    "[class*='preview']", "[class*='Preview']",
    "[class*='carousel']", "[class*='Carousel']",
    "[class*='swiper']", "[class*='Swiper']",
    "[class*='magnifier']", "[class*='Magnifier']",
    "[id*='gallery']", "[id*='Gallery']",
  ].join(",");
  const heroGalleryRoots = Array.from(document.querySelectorAll(gallerySelector))
    .filter((node) => {
      const rectangle = node.getBoundingClientRect();
      const imageCount = node.querySelectorAll("img,picture").length;
      const nearProductHero = rectangle.bottom >= 0
        && rectangle.top <= Math.max(window.innerHeight * 1.6, 1200);
      return imageCount >= 2
        && nearProductHero
        && Math.max(rectangle.width, rectangle.height) >= 120;
    });

  // Taobao's newer product pages do not always expose semantic gallery class
  // names.  Capture the visible hero and its thumbnail rail before scrolling.
  // A candidate must either live in a gallery-like ancestor or share a compact
  // image cluster with at least two peers; this excludes shop avatars/logos.
  const topGalleryImages = Array.from(document.images || [])
    .map((image) => {
      const rectangle = image.getBoundingClientRect();
      const ancestor = image.closest(gallerySelector);
      let cluster = image.parentElement;
      for (let level = 0; level < 4 && cluster; level += 1) {
        if (cluster.querySelectorAll("img").length >= 3) break;
        cluster = cluster.parentElement;
      }
      const clusterImages = cluster ? cluster.querySelectorAll("img").length : 0;
      return { image, rectangle, ancestor, clusterImages };
    })
    .filter(({ image, rectangle, ancestor, clusterImages }) => {
      const width = Number(image.naturalWidth || rectangle.width || 0);
      const height = Number(image.naturalHeight || rectangle.height || 0);
      const ratio = width / Math.max(height, 1);
      const top = rectangle.top + window.scrollY;
      const text = norm([image.alt, image.className, image.parentElement?.className].join(" "));
      return top >= 60 && top <= 1250
        && width >= 60 && height >= 60
        && ratio >= 0.45 && ratio <= 2.2
        && (ancestor || clusterImages >= 3)
        && !/(logo|avatar|店铺|客服|二维码|icon|图标)/i.test(text);
    })
    .sort((left, right) => {
      const areaDifference = (right.rectangle.width * right.rectangle.height)
        - (left.rectangle.width * left.rectangle.height);
      if (Math.abs(areaDifference) > 5000) return areaDifference;
      return left.rectangle.top - right.rectangle.top || left.rectangle.left - right.rectangle.left;
    })
    .map(({ image }) => image);

  for (const image of topGalleryImages) {
    const candidates = [
      image.currentSrc,
      image.src,
      image.dataset?.src,
      image.dataset?.lazyload,
      image.getAttribute?.("data-ks-lazyload"),
      image.getAttribute?.("data-original"),
      image.getAttribute?.("data-image"),
      image.getAttribute?.("data-url"),
    ];
    for (const candidate of candidates) add(candidate, "dom_gallery", image);
  }

  const root = document.scrollingElement || document.documentElement;
  let previousHeight = 0;
  let stableRounds = 0;
  for (let step = 0; step < 18; step += 1) {
    const height = Math.max(root.scrollHeight, document.body ? document.body.scrollHeight : 0);
    window.scrollTo(0, Math.min(height, (step + 1) * Math.max(window.innerHeight * 0.9, 720)));
    await sleep(170);
    stableRounds = height === previousHeight ? stableRounds + 1 : 0;
    previousHeight = height;
    if (stableRounds >= 3 && window.scrollY + window.innerHeight >= height - 60) break;
  }
  await sleep(450);

  const classifyDomSource = (node) => {
    const context = norm([
      node?.className,
      node?.id,
      node?.closest?.("[class*='sku'],[class*='Sku'],[class*='prop'],[class*='Prop'],[class*='detail'],[class*='Detail'],[class*='desc'],[class*='gallery'],[class*='Gallery'],[class*='thumb'],[class*='Thumb'],[class*='preview'],[class*='Preview'],[class*='carousel'],[class*='Carousel'],[class*='swiper'],[class*='Swiper'],[id*='detail'],[id*='desc'],[id*='gallery']")?.className,
      node?.parentElement?.className,
    ].join(" ")).toLowerCase();
    if (heroGalleryRoots.some((rootNode) => rootNode === node || rootNode.contains(node))) return "dom_gallery";
    if (/(sku|sale.?prop|sku.?prop|spec|颜色分类|规格值)/i.test(context)) return "dom_sku";
    if (/(detail|description|desc.?content|图文详情)/i.test(context)) return "dom_detail";
    return "dom_unknown";
  };
  const srcsetUrls = (value) => String(value || "")
    .split(",")
    .map((part) => part.trim().split(/\s+/)[0])
    .filter(Boolean);
  for (const image of Array.from(document.images || [])) {
    const source = classifyDomSource(image);
    const candidates = [
      image.currentSrc,
      image.src,
      image.dataset?.src,
      image.dataset?.lazyload,
      image.getAttribute?.("data-ks-lazyload"),
      image.getAttribute?.("data-original"),
      image.getAttribute?.("data-image"),
      image.getAttribute?.("data-url"),
      ...srcsetUrls(image.srcset),
    ];
    for (const candidate of candidates) add(candidate, source, image);
  }

  // Some page revisions omit SKU data from the structured state but still
  // render image-backed colour/style options. Preserve those options with the
  // exact picture that appeared beside them instead of substituting a main or
  // detail image.
  if (!skuCatalog.dimensions.length) {
    const options = [];
    const seenDomOptions = new Set();
    for (const image of Array.from(document.images || [])) {
      if (classifyDomSource(image) !== "dom_sku") continue;
      const optionNode = image.closest("button,[role='radio'],li,[class*='value'],[class*='Value'],[class*='option'],[class*='Option']")
        || image.parentElement;
      let value = norm(
        optionNode?.getAttribute?.("aria-label")
        || optionNode?.getAttribute?.("title")
        || optionNode?.innerText
        || image.alt,
      );
      if (!value || value.length > 120) value = norm(image.alt);
      const imageUrl = clean(
        image.currentSrc || image.src || image.dataset?.src
        || image.getAttribute?.("data-original") || "",
      );
      if (!value || !imageUrl || seenDomOptions.has(value)) continue;
      seenDomOptions.add(value);
      options.push({
        value,
        valueId: norm(optionNode?.dataset?.valueId || optionNode?.dataset?.vid || ""),
        image: imageUrl,
        available: optionNode?.getAttribute?.("aria-disabled") !== "true",
        selected: optionNode?.getAttribute?.("aria-checked") === "true"
          || /selected|active/i.test(String(optionNode?.className || "")),
        priceText: "",
      });
      if (options.length >= 80) break;
    }
    if (options.length) {
      skuCatalog.hasSku = true;
      skuCatalog.dimensions.push({ label: "颜色/款式", options });
    }
  }
  for (const sourceNode of Array.from(document.querySelectorAll("picture source[srcset]"))) {
    const picture = sourceNode.closest("picture");
    const image = picture?.querySelector("img") || picture;
    const source = classifyDomSource(image);
    if (source !== "dom_gallery") continue;
    for (const candidate of srcsetUrls(sourceNode.getAttribute("srcset"))) {
      add(candidate, "picture_gallery", image);
    }
  }
  for (const node of heroGalleryRoots) {
    const background = String(getComputedStyle(node).backgroundImage || "");
    for (const match of background.matchAll(/url\(["']?([^"')]+)["']?\)/g)) {
      add(match[1], "css_gallery", node);
    }
  }

  const currentBodyText = norm(document.body ? document.body.innerText : "");
  const firstBodyMatch = (pattern) => {
    const match = currentBodyText.match(pattern);
    return match ? norm(match[1] || match[0]) : "";
  };
  const knownTerms = (terms) => terms.filter((term) => currentBodyText.includes(term));
  const sectionText = (labels) => {
    const candidates = Array.from(document.querySelectorAll("h1,h2,h3,h4,h5,strong,dt,div,span"));
    for (const node of candidates) {
      const ownText = norm(node.childElementCount ? "" : (node.innerText || node.textContent || ""));
      if (!labels.some((label) => ownText === label || ownText.startsWith(label))) continue;
      const container = node.closest("section,article,[class*='param'],[class*='Param'],[class*='attribute'],[class*='Attribute']")
        || node.parentElement?.parentElement || node.parentElement;
      const value = norm(container?.innerText || container?.textContent || "");
      if (value.length >= ownText.length + 4) return value.slice(0, 8000);
    }
    return "";
  };
  const titleText = firstStructured(["item.title", "item.itemTitle", "item.basicInfo.title"])
    || firstDomText(["h1", "[class*='Title--']", "[class*='ItemTitle']"])
    || norm(document.title).replace(/-(?:tmall\.com天猫|淘宝网)$/i, "");
  const priceText = firstStructured([
    "price.price.priceText",
    "price.priceText",
    "item.priceText",
    "item.price",
  ]) || firstDomText([
    "[class*='Price--']",
    "[class*='priceText']",
    "[class*='PriceText']",
  ]) || firstBodyMatch(/(?:￥|¥)\s*(\d{1,8}(?:\.\d{1,2})?)/);
  const originalPriceText = firstDomText([
    "[class*='OriginPrice']",
    "[class*='originalPrice']",
    "del",
  ]);
  const shopName = firstStructured([
    "seller.shopName",
    "seller.sellerNick",
    "shop.shopName",
    "shop.name",
  ]) || firstDomText([
    "[class*='ShopHeader'] [class*='name']",
    "[class*='ShopName']",
    "a[href*='shop.taobao.com']",
    "a[href*='shop.tmall.com']",
  ]);
  const soldText = firstBodyMatch(/((?:已售|月销)\s*\d+(?:\.\d+)?(?:万|千)?\+?)/);
  const paymentText = firstBodyMatch(/(\d+(?:\.\d+)?(?:万|千)?\+?\s*人(?:付款|收货))/);
  const originText = firstBodyMatch(/(?:发货地|产地)\s*[:：]?\s*([^\s]{2,18})/);
  const product = {
    title: titleText,
    subtitle: firstStructured(["item.subtitle", "item.subTitle", "item.sellPoint"]),
    priceText,
    originalPriceText,
    shopName,
    soldText,
    paymentText,
    originText,
    promotions: knownTerms(["补贴后", "优惠后", "券后", "官方立减", "跨店满减", "国家补贴"]),
    services: knownTerms(["包邮", "退货宝", "7天无理由退换", "极速退款", "假一赔四", "可开发票", "信用卡支付", "运费险"]),
    logistics: knownTerms(["当日达", "次日达", "24小时内发", "48小时内发", "送货入户", "上门安装"]),
    attributesText: sectionText(["参数信息", "商品参数", "规格参数", "产品参数"]),
  };

  const videos = [];
  const seenVideos = new Set();
  for (const video of Array.from(document.querySelectorAll("video"))) {
    const url = clean(video.currentSrc || video.src || video.querySelector("source")?.src || "");
    if (!/^https:\/\//i.test(url) || seenVideos.has(url)) continue;
    seenVideos.add(url);
    videos.push({ url, poster: clean(video.poster || "") });
  }

  const questions = { totalText: "", items: [] };
  const questionNodes = Array.from(document.querySelectorAll(
    "[class*='question-item'],[class*='QuestionItem'],[class*='ask-item'],[class*='AskItem'],[class*='questionCard']",
  ));
  for (const node of questionNodes) {
    const lines = String(node.innerText || node.textContent || "")
      .split(/\r?\n/).map(norm).filter(Boolean);
    const question = lines.find((line) => /[?？]$/.test(line)) || lines[0] || "";
    if (question.length < 2 || question.length > 500) continue;
    const answerCountMatch = norm(node.innerText).match(/(\d+\s*个?回答)/);
    const answers = lines.filter((line) => line !== question && line.length >= 2).slice(0, 10);
    questions.items.push({
      question,
      answerCount: answerCountMatch ? answerCountMatch[1] : "",
      answers,
      date: "",
    });
    if (questions.items.length >= 20) break;
  }
  const questionTotalMatch = currentBodyText.match(/问大家\s*\(?\s*(\d+)\s*\)?/);
  if (questionTotalMatch) questions.totalText = `${questionTotalMatch[1]} 个问题`;

  const reviewStartPage = __REVIEW_START_PAGE__;
  const reviewLimit = __REVIEW_LIMIT__;
  const reviews = { totalText: "", tags: [], items: [], nextPage: reviewStartPage };
  try {
    const itemId = new URL(location.href).searchParams.get("id");
    if (itemId && window.lib?.mtop?.request) {
      const response = await Promise.race([
        window.lib.mtop.request({
          api: "mtop.taobao.detail.getdesc",
          v: "6.0",
          data: { id: itemId, itemId, type: "1" },
        }),
        new Promise((_, reject) => setTimeout(() => reject(new Error("timeout")), 5000)),
      ]);
      const html = response?.data?.pcDescContent || response?.data?.desc || "";
      if (html) {
        const doc = new DOMParser().parseFromString(String(html), "text/html");
        for (const image of Array.from(doc.images || [])) {
          add(
            image.src || image.getAttribute("data-src") || image.getAttribute("data-ks-lazyload"),
            "detail_api",
            image,
          );
        }
      }
    }
  } catch (_) {}

  try {
    const itemId = new URL(location.href).searchParams.get("id");
    if (itemId && window.lib?.mtop?.request) {
      const reviewImageUrls = (value) => {
        const found = [];
        const imageKeys = /^(pics|images|photos|picList|appendPics|feedbackPics|ratePics)$/i;
        const walkImages = (item, depth = 0, insideImageField = false) => {
          if (!item || depth > 5 || found.length >= 18) return;
          if (typeof item === "string") {
            if (insideImageField && /(?:alicdn|tbcdn|taobaocdn)/i.test(item)) found.push(item);
            return;
          }
          if (Array.isArray(item)) {
            for (const child of item) walkImages(child, depth + 1, insideImageField);
            return;
          }
          if (typeof item !== "object") return;
          if (insideImageField) {
            const direct = item.url || item.picUrl || item.imageUrl || item.src || item.thumbnail;
            if (direct) walkImages(direct, depth + 1, true);
          }
          for (const [key, child] of Object.entries(item)) {
            if (imageKeys.test(key)) walkImages(child, depth + 1, true);
          }
        };
        walkImages(value);
        return [...new Set(found)].slice(0, 9);
      };
      const visit = (value, depth = 0) => {
        if (!value || depth > 6) return;
        if (Array.isArray(value)) {
          for (const item of value) visit(item, depth + 1);
          return;
        }
        if (typeof value !== "object") return;
        const content = norm(value.feedback || value.rateContent || value.content || value.reviewContent || "");
        if (content.length >= 4 && content.length <= 1000 && reviews.items.length < reviewLimit) {
          reviews.items.push({
            content,
            sku: norm(value.auctionSku || value.skuInfo || value.sku || ""),
            date: norm(value.feedbackDate || value.rateDate || value.date || ""),
            images: reviewImageUrls(value),
          });
        }
        for (const [key, child] of Object.entries(value)) {
          if (/^(keywords|tags|impress|impressions)$/i.test(key) && Array.isArray(child)) {
            for (const tag of child) {
              const label = norm(typeof tag === "string" ? tag : (tag?.title || tag?.label || tag?.word || ""));
              if (label) reviews.tags.push(label);
            }
          }
          if (!reviews.totalText && /^(totalCount|rateCount|total|totalNum)$/i.test(key)) {
            const total = norm(child);
            if (/^\d+$/.test(total)) reviews.totalText = `${total} 条评价`;
          }
          visit(child, depth + 1);
        }
      };
      for (let pageNo = reviewStartPage; pageNo < reviewStartPage + 3 && reviews.items.length < reviewLimit; pageNo += 1) {
        const response = await Promise.race([
          window.lib.mtop.request({
            api: "mtop.taobao.rate.detaillist.get",
            v: "6.0",
            data: {
              itemId,
              auctionNumId: itemId,
              pageNo,
              pageSize: 20,
              orderType: "sort_weight",
              rateType: "",
            },
          }),
          new Promise((_, reject) => setTimeout(() => reject(new Error("timeout")), 5000)),
        ]);
        const beforeCount = reviews.items.length;
        visit(response?.data || {});
        if (reviews.items.length === beforeCount) break;
        reviews.nextPage = pageNo + 1;
        if (pageNo < reviewStartPage + 2) await sleep(260);
      }
    }
  } catch (_) {}

  if (!reviews.items.length) {
    const reviewNodes = Array.from(document.querySelectorAll(
      "[class*='review-item'],[class*='ReviewItem'],[class*='rate-item'],[class*='RateItem'],[class*='comment-item']"
    ));
    for (const node of reviewNodes) {
      const content = norm(node.innerText || node.textContent || "");
      if (content.length < 4 || content.length > 1000) continue;
      reviews.items.push({ content, sku: "", date: "", images: [] });
      if (reviews.items.length >= reviewLimit) break;
    }
  }
  if (!reviews.totalText) {
    const totalMatch = bodyText.match(/(?:累计)?\s*(\d{1,9})\s*(?:条)?评价/);
    if (totalMatch) reviews.totalText = `${totalMatch[1]} 条评价`;
  }

  window.scrollTo(0, 0);
  return {
    url: location.href,
    title: document.title,
    needsLogin: false,
    blocked: false,
    product,
    skuCatalog,
    images: images.slice(0, 120),
    videos,
    reviews,
    questions,
  };
})()
"""
    return (
        expression.replace("__REVIEW_START_PAGE__", str(review_start_page))
        .replace("__REVIEW_LIMIT__", str(PRODUCT_REVIEW_LIMIT))
    )


def _atomic_write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f"Browser search result already exists: path={path}")
    partial = path.parent / f".{path.name}.{uuid4().hex}.partial"
    try:
        partial.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(partial, path)
    finally:
        if partial.exists():
            partial.unlink()


def _close_target(target):
    target_id = str(target.get("id") or "")
    if not target_id:
        return
    try:
        _cdp_json(f"/json/close/{parse.quote(target_id, safe='')}", timeout=2.0)
    except Exception:
        pass


def _activate_target(target):
    """Bring an existing CDP page to the front without creating another browser."""
    target_id = str(target.get("id") or "")
    if not target_id:
        return
    try:
        _cdp_json(f"/json/activate/{parse.quote(target_id, safe='')}", timeout=2.0)
    except Exception:
        # Activation is convenience only. The login gate must still be returned even
        # when the desktop window manager refuses foreground focus.
        pass


def capture_search_page(
    application_data_directory,
    keyword,
    page_number,
    raw_result_path,
):
    target_url = build_taobao_search_url(keyword, page_number)
    if not _cdp_ready() or _target_for_search_browser() is None:
        _launch_search_browser(application_data_directory, target_url)

    target = None
    for _ in range(30):
        target = _target_for_search_browser()
        if target:
            break
        time.sleep(0.2)
    if target is None:
        raise RuntimeError("没有找到专属淘宝采集页面，请关闭采集浏览器后重试。")

    current_url = str(target.get("url") or "")
    current_host = (parse.urlparse(current_url).hostname or "").casefold()
    authentication_hosts = {
        "login.taobao.com",
        "login.tmall.com",
        "passport.taobao.com",
        "sec.taobao.com",
    }
    previous_item_ids = set()
    if current_host not in authentication_hosts:
        if page_number == 1:
            _navigate_target(target, target_url)
            time.sleep(0.8)
        else:
            current_query = (parse.parse_qs(parse.urlparse(current_url).query).get("q") or [""])[0]
            if current_host != "s.taobao.com" or current_query.strip() != str(keyword).strip():
                _navigate_target(target, build_taobao_search_url(keyword, 1))
                time.sleep(1.0)
                target = _target_for_search_browser() or target
            try:
                previous_item_ids = _visible_search_item_ids(target)
                _navigate_target(target, target_url)
            except (RuntimeError, OSError, socket.timeout):
                return {
                    "status": "failed",
                    "message": (
                        f"淘宝第{page_number}页打开失败，本次没有保存。"
                        "请确认采集浏览器中的淘宝页面可以正常访问后重试。"
                    ),
                }
            time.sleep(0.8)

    raw_payload = None
    stale_page_detected = False
    for _ in range(50):
        time.sleep(0.25)
        target = _target_for_search_browser() or target
        try:
            candidate = _cdp_evaluate(target, _capture_expression(), timeout=12)
        except (RuntimeError, OSError, socket.timeout):
            continue
        if not isinstance(candidate, dict):
            continue
        raw_payload = candidate
        if candidate.get("needsLogin") or candidate.get("blocked"):
            break
        if not candidate.get("products"):
            continue
        if candidate.get("currentPage") != page_number:
            continue
        candidate_item_ids = {
            str(product.get("itemId") or "").strip()
            for product in candidate.get("products") or []
            if isinstance(product, dict)
        }
        if (
            page_number > 1
            and previous_item_ids
            and candidate_item_ids
            and candidate_item_ids == previous_item_ids
        ):
            stale_page_detected = True
            continue
        break
    if raw_payload is None:
        _close_target(target)
        raise RuntimeError("淘宝搜索页加载超时，本次没有保存任何新商品。")
    if stale_page_detected:
        raw_item_ids = {
            str(product.get("itemId") or "").strip()
            for product in raw_payload.get("products") or []
            if isinstance(product, dict)
        }
        if raw_item_ids == previous_item_ids:
            return {
                "status": "failed",
                "message": (
                    f"淘宝第{page_number}页没有完成翻页，读取结果仍与上一页相同。"
                    "本次没有保存，请重新点击采集下一页。"
                ),
            }

    normalized = normalize_browser_search_capture(
        raw_payload,
        expected_keyword=keyword,
        expected_page_number=page_number,
    )
    if normalized["status"] in {"login_required", "blocked"}:
        _activate_target(target)
    else:
        _atomic_write_json(raw_result_path, raw_payload)
        normalized["raw_source_ref"] = str(raw_result_path)
        normalized["captured_at"] = datetime.now().astimezone().isoformat(timespec="microseconds")
    return normalized


def capture_next_search_page(
    application_data_directory,
    keyword,
    page_number,
    raw_result_path,
):
    return capture_search_page(
        application_data_directory,
        keyword,
        page_number,
        raw_result_path,
    )


def capture_shop_listing(application_data_directory, shop_url, shop_name, raw_result_path):
    """Capture the currently visible shop item list in the dedicated logged-in browser."""
    target_url = validate_shop_url(shop_url)
    if not _cdp_ready() or _target_for_search_browser() is None:
        _launch_search_browser(application_data_directory, target_url)
    target = None
    for _ in range(30):
        target = _target_for_search_browser()
        if target:
            break
        time.sleep(0.2)
    if target is None:
        raise RuntimeError("没有找到专属淘宝采集页面，请关闭采集浏览器后重试。")
    current_host = (parse.urlparse(str(target.get("url") or "")).hostname or "").casefold()
    if current_host not in {"login.taobao.com", "login.tmall.com", "passport.taobao.com", "sec.taobao.com"}:
        _navigate_target(target, target_url)
        time.sleep(0.8)
    raw_payload = None
    for _ in range(50):
        time.sleep(0.25)
        target = _target_for_search_browser() or target
        try:
            candidate = _cdp_evaluate(target, _capture_expression(), timeout=12)
        except (RuntimeError, OSError, socket.timeout):
            continue
        if not isinstance(candidate, dict):
            continue
        raw_payload = candidate
        if candidate.get("needsLogin") or candidate.get("blocked") or candidate.get("products"):
            break
    if raw_payload is None:
        raise RuntimeError("店铺页面加载超时，本次没有保存快照。")
    normalized = normalize_browser_shop_capture(
        raw_payload, expected_shop_url=target_url, expected_shop_name=shop_name
    )
    if normalized["status"] in {"login_required", "blocked"}:
        _activate_target(target)
    elif normalized["status"] == "success":
        _atomic_write_json(raw_result_path, raw_payload)
        normalized["raw_source_ref"] = str(raw_result_path)
        normalized["captured_at"] = datetime.now().astimezone().isoformat(timespec="microseconds")
    return normalized


def capture_product_images(
    application_data_directory,
    product_url,
    expected_item_id,
    raw_result_path,
    *,
    review_start_page=1,
):
    """Capture main, SKU, and detail images using the dedicated logged-in browser."""
    if not _cdp_ready() or _target_for_search_browser() is None:
        _launch_search_browser(application_data_directory, product_url)

    target = None
    for _ in range(30):
        target = _target_for_search_browser()
        if target:
            break
        time.sleep(0.2)
    if target is None:
        raise RuntimeError("没有找到专属淘宝采集页面，请关闭采集浏览器后重试。")

    current_url = str(target.get("url") or "")
    current_host = (parse.urlparse(current_url).hostname or "").casefold()
    if current_host not in {"login.taobao.com", "login.tmall.com"} and current_url != product_url:
        _navigate_target(target, product_url)

    raw_payload = None
    best_payload_score = -1
    matching_capture_passes = 0
    capture_deadline = time.monotonic() + 90
    while time.monotonic() < capture_deadline:
        time.sleep(0.25)
        target = _target_for_search_browser() or target
        try:
            candidate = _cdp_evaluate(
                target,
                _product_image_capture_expression(review_start_page),
                timeout=22,
            )
        except (RuntimeError, OSError, socket.timeout):
            continue
        if not isinstance(candidate, dict):
            continue
        if candidate.get("needsLogin") or candidate.get("blocked"):
            raw_payload = candidate
            break
        candidate_url = str(candidate.get("url") or "")
        candidate_item_id = (
            parse.parse_qs(parse.urlparse(candidate_url).query).get("id") or [""]
        )[0]
        if candidate_item_id != str(expected_item_id):
            continue
        matching_capture_passes += 1
        candidate_images = candidate.get("images") or []
        candidate_reviews = ((candidate.get("reviews") or {}).get("items") or [])
        candidate_sources = {
            str(image.get("source") or "").casefold()
            for image in candidate_images
            if isinstance(image, dict)
        }
        candidate_score = len(candidate_images) + (2 * len(candidate_reviews))
        if candidate_score > best_payload_score:
            raw_payload = candidate
            best_payload_score = candidate_score
        has_loaded_archive = bool(
            len(candidate_images) >= 3
            or candidate_reviews
            or candidate_sources.intersection(
                {"structured_sku", "dom_sku", "detail_api", "dom_detail"}
            )
        )
        if has_loaded_archive or matching_capture_passes >= 3:
            break
    if raw_payload is None:
        _close_target(target)
        raise RuntimeError("淘宝商品页加载超时；已保留原有文本采集结果。")

    normalized = normalize_browser_product_capture(
        raw_payload,
        expected_item_id=expected_item_id,
    )
    if normalized["status"] in {"login_required", "blocked"}:
        _activate_target(target)
    else:
        _atomic_write_json(raw_result_path, raw_payload)
        normalized["raw_source_ref"] = str(raw_result_path)
        normalized["captured_at"] = datetime.now().astimezone().isoformat(timespec="microseconds")
        _close_target(target)
    return normalized
