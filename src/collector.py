import json
import os
from pathlib import Path
import re
import subprocess
import time
from datetime import datetime
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from contextlib import closing

from src.competitor_analysis import parse_sku_dimensions, parse_sku_price_scan
from src.database import connect_database, save_search_snapshot, search_result_response


SOURCE_APP = "taobao-market-intelligence"
TAOBAO_NATIVE_TIMEOUT_SECONDS = 20
INSTALL_LOCATION_RELATIVE_PATH = Path("taobao") / "install-location.txt"
COMMAND_RELATIVE_PATH = Path("bin") / "taobao-native.cmd"
PRODUCT_DETAIL_HOSTS = {"item.taobao.com", "detail.tmall.com"}
PRODUCT_DETAIL_PATH = "/item.htm"
TAOBAO_AD_CLICK_HOST = "click.simba.taobao.com"
TAOBAO_AD_CLICK_PATH = "/cc_im"
PRODUCT_DETAIL_MAX_LENGTH = 200000
TAOBAO_IMAGE_HOST_SUFFIXES = ("alicdn.com", "taobaocdn.com")
PRODUCT_SERVICE_LABELS = (
    "可开发票",
    "免运费",
    "7天无理由退换",
    "假一赔四",
    "极速退款",
    "信用卡支付",
)


def _decode_install_location(location_bytes, location_file):
    if location_bytes.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            return location_bytes.decode("utf-16").strip()
        except UnicodeDecodeError as exc:
            raise RuntimeError(
                f"Cannot decode taobao install location: path={location_file} "
                f"byte_prefix={location_bytes[:16].hex()}"
            ) from exc

    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return location_bytes.decode(encoding).strip()
        except UnicodeDecodeError:
            continue

    raise RuntimeError(
        f"Cannot decode taobao install location: path={location_file} "
        f"byte_prefix={location_bytes[:16].hex()}"
    )


def resolve_taobao_native_command(install_location_file=None):
    if install_location_file is None:
        app_data = os.environ.get("APPDATA")
        if not str(app_data or "").strip():
            raise ValueError(f"APPDATA is required: actual={app_data!r}")
        install_location_file = Path(app_data) / INSTALL_LOCATION_RELATIVE_PATH
    else:
        install_location_file = Path(install_location_file)

    if not install_location_file.is_file():
        raise FileNotFoundError(
            f"Taobao install location file does not exist: path={install_location_file}"
        )

    install_location = _decode_install_location(
        install_location_file.read_bytes(),
        install_location_file,
    )
    if not install_location:
        raise ValueError(
            f"Taobao install location is empty: path={install_location_file} actual={install_location!r}"
        )

    command_path = Path(install_location) / COMMAND_RELATIVE_PATH
    if not command_path.is_file():
        raise FileNotFoundError(
            f"taobao-native command does not exist: path={command_path}"
        )
    return command_path


def validate_product_detail_url(product_url):
    if not isinstance(product_url, str) or not product_url.strip():
        raise ValueError(
            f"product_url must be non-empty text: actual={product_url!r}"
        )
    normalized_url = product_url.strip()
    parsed_url = urlparse(normalized_url)
    hostname = (parsed_url.hostname or "").casefold()
    item_ids = parse_qs(parsed_url.query).get("id", [])
    valid_item_id = (
        len(item_ids) == 1
        and item_ids[0].isdigit()
        and int(item_ids[0]) > 0
    )
    try:
        port = parsed_url.port
    except ValueError as exc:
        raise ValueError(
            f"product_url contains invalid port: actual={product_url!r}"
        ) from exc
    if (
        parsed_url.scheme.casefold() != "https"
        or hostname not in PRODUCT_DETAIL_HOSTS
        or parsed_url.path != PRODUCT_DETAIL_PATH
        or parsed_url.username is not None
        or parsed_url.password is not None
        or port is not None
        or not valid_item_id
    ):
        raise ValueError(
            f"product_url must be an HTTPS Taobao/Tmall item link with numeric id: "
            f"actual={product_url!r}"
        )
    return normalized_url


def canonicalize_search_product_url(product_url, item_id):
    """Turn a trusted search-result ad click into a stable item detail URL.

    Manual detail URLs still pass through ``validate_product_detail_url`` and
    remain subject to its strict host/path checks.  This conversion is only for
    a search result whose numeric item id was parsed independently.
    """
    if not isinstance(product_url, str) or not product_url.strip():
        return product_url
    normalized_item_id = str(item_id or "").strip()
    if not normalized_item_id.isdigit() or int(normalized_item_id) <= 0:
        return product_url

    parsed_url = urlparse(product_url.strip())
    try:
        port = parsed_url.port
    except ValueError:
        return product_url
    if (
        parsed_url.scheme.casefold() == "https"
        and (parsed_url.hostname or "").casefold() == TAOBAO_AD_CLICK_HOST
        and parsed_url.path == TAOBAO_AD_CLICK_PATH
        and parsed_url.username is None
        and parsed_url.password is None
        and port is None
    ):
        return f"https://item.taobao.com/item.htm?id={normalized_item_id}"
    return product_url.strip()


def _response_result(response, result_path):
    if not isinstance(response, dict):
        raise ValueError(
            f"Product detail response must be an object: "
            f"path={result_path} actual={response!r}"
        )
    result = response.get("result")
    if not isinstance(result, dict):
        raise ValueError(
            f"Product detail response result must be an object: "
            f"path={result_path} actual={result!r}"
        )
    return result


def _first_match(pattern, content):
    match = re.search(pattern, content)
    return match.group(0) if match else None


def _shop_fields(content):
    shop_match = re.search(
        r"\n(?P<name>[^\n]+?)(?P<rating>\d+(?:\.\d+)?)VIP"
        r"好评率(?P<positive>[0-9.]+%)平均(?P<shipping>.+?发货)"
        r"平均(?P<refund>.+?退款)客服",
        content,
    )
    if shop_match is None:
        return {
            "name": None,
            "rating_text": None,
            "positive_rate_text": None,
            "shipping_text": None,
            "refund_text": None,
        }
    return {
        "name": shop_match.group("name").strip(),
        "rating_text": shop_match.group("rating"),
        "positive_rate_text": shop_match.group("positive"),
        "shipping_text": shop_match.group("shipping"),
        "refund_text": shop_match.group("refund"),
    }


def _review_preview(content):
    review_start = content.find("用户评价·")
    if review_start < 0:
        return None
    review_end = content.find("查看全部评价", review_start)
    if review_end < 0:
        return None
    preview_text = content[review_start:review_end].strip()
    return preview_text or None


def _attribute_text(content):
    details_start = content.rfind("图文详情")
    if details_start < 0:
        return None
    attributes_start = content.rfind("参数信息", 0, details_start)
    if attributes_start < 0:
        return None
    visible_text = content[attributes_start + len("参数信息"):details_start].strip()
    return visible_text or None


def _clean_marketplace_title(page_title):
    title = re.sub(r"\s+", " ", page_title or "").strip()
    return re.sub(
        r"\s*[-_]\s*(?:(?:tmall\.com)?天猫|淘宝网).*$",
        "",
        title,
        flags=re.IGNORECASE,
    ).strip()


def _normalized_taobao_image_url(image_url):
    if not isinstance(image_url, str) or not image_url.strip():
        return None
    normalized_url = image_url.strip()
    if normalized_url.startswith("//"):
        normalized_url = f"https:{normalized_url}"
    if normalized_url.endswith("_.webp"):
        normalized_url = normalized_url[:-6]
    parsed_url = urlparse(normalized_url)
    hostname = (parsed_url.hostname or "").casefold()
    if (
        parsed_url.scheme.casefold() != "https"
        or not any(
            hostname == suffix or hostname.endswith(f".{suffix}")
            for suffix in TAOBAO_IMAGE_HOST_SUFFIXES
        )
    ):
        return None
    return normalized_url


def _tagged_product_images(content):
    images = []
    seen_urls = set()
    for match in re.finditer(
        r"^\[(商品主图|商品图)\]\s*(https://\S+)",
        content,
        flags=re.MULTILINE,
    ):
        image_url = _normalized_taobao_image_url(match.group(2))
        if not image_url:
            continue
        deduplication_key = image_url.split("?", 1)[0]
        if deduplication_key in seen_urls:
            continue
        seen_urls.add(deduplication_key)
        images.append(
            {
                "url": image_url,
                "kind": "main" if match.group(1) == "商品主图" else "gallery",
            }
        )
    return images


def parse_product_detail_response(response, result_path):
    result = _response_result(response, result_path)
    page_url = result.get("url")
    validated_page_url = validate_product_detail_url(page_url)

    truncated = result.get("truncated")
    remaining_length = result.get("remainingLength")
    if truncated is not False or remaining_length != 0:
        raise ValueError(
            f"Product detail response is truncated: path={result_path} "
            f"truncated={truncated!r} remainingLength={remaining_length!r}"
        )
    if result.get("offset") != 0:
        raise ValueError(
            f"Product detail response must start at offset 0: "
            f"path={result_path} actual={result.get('offset')!r}"
        )

    page_title = result.get("title")
    if not isinstance(page_title, str) or not page_title.strip():
        raise ValueError(
            f"Product detail title must be non-empty text: "
            f"path={result_path} actual={page_title!r}"
        )
    content = result.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ValueError(
            f"Product detail content must be non-empty text: "
            f"path={result_path} actual={content!r}"
        )

    item_id_match = re.search(r"\[商品id\]\s*(\d+)", content)
    if item_id_match is None:
        raise ValueError(
            f"Product detail content is missing item id: path={result_path}"
        )
    item_id = item_id_match.group(1)
    page_item_id = parse_qs(urlparse(validated_page_url).query)["id"][0]
    if item_id != page_item_id:
        raise ValueError(
            f"Product detail item id does not match url: path={result_path} "
            f"content_item_id={item_id!r} url_item_id={page_item_id!r}"
        )

    images = _tagged_product_images(content)
    main_image = next(
        (image for image in images if image["kind"] == "main"),
        images[0] if images else None,
    )
    main_image_url = main_image["url"] if main_image else None

    return {
        "page_url": validated_page_url,
        "product": {
            "item_id": item_id,
            "page_title": _clean_marketplace_title(page_title),
            "main_image_url": main_image_url,
            "images": images,
            "visible_price_text": _first_match(
                r"￥\s*\d+(?:\.\d+)?(?:起)?",
                content,
            ),
        },
        "shop": _shop_fields(content),
        "sales": {
            "sold_text": _first_match(r"已售\s*[0-9.万+]+", content),
            "repeat_buyer_text": _first_match(r"回头客[0-9.万+]+人", content),
            "cart_text": _first_match(r"(?:超)?[0-9.万+]+人加购", content),
        },
        "reviews": {
            "count_text": _first_match(r"[0-9.万+]+人评价", content),
            "preview_text": _review_preview(content),
        },
        "services": [
            service_label
            for service_label in PRODUCT_SERVICE_LABELS
            if service_label in content
        ],
        "attributes": {"visible_text": _attribute_text(content)},
        "raw_result_path": str(result_path),
    }


def _validated_command_path(command_path):
    if command_path is None:
        return resolve_taobao_native_command()
    validated_path = Path(command_path)
    if not validated_path.is_file():
        raise FileNotFoundError(
            f"taobao-native command does not exist: path={validated_path}"
        )
    return validated_path


def _run_taobao_request(tool_name, command_path, request_path, result_path):
    if result_path.exists():
        raise FileExistsError(
            f"taobao-native result path already exists: path={result_path}"
        )
    command = [
        str(command_path),
        "--request",
        str(request_path),
        "-o",
        str(result_path),
    ]
    try:
        completed_command = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            timeout=TAOBAO_NATIVE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"taobao-native {tool_name} timed out after "
            f"{TAOBAO_NATIVE_TIMEOUT_SECONDS} seconds"
        ) from exc
    if completed_command.returncode != 0:
        raise RuntimeError(
            f"taobao-native {tool_name} failed: "
            f"exit_code={completed_command.returncode} "
            f"stdout={completed_command.stdout!r} "
            f"stderr={completed_command.stderr!r}"
        )
    if not result_path.is_file():
        raise FileNotFoundError(
            f"taobao-native {tool_name} did not create result: path={result_path}"
        )


def run_product_detail(
    product_url,
    request_directory,
    detail_result_path,
    *,
    command_path=None,
):
    validated_url = validate_product_detail_url(product_url)
    request_directory = Path(request_directory)
    detail_result_path = Path(detail_result_path)
    command_path = _validated_command_path(command_path)
    navigate_request_path = request_directory / "navigate-product.json"
    navigate_result_path = request_directory / "navigate-product-result.json"
    detail_request_path = request_directory / "read-product-detail.json"
    if detail_result_path.exists():
        raise FileExistsError(
            f"Product detail result path already exists: path={detail_result_path}"
        )
    request_directory.mkdir(parents=True, exist_ok=True)
    detail_result_path.parent.mkdir(parents=True, exist_ok=True)

    navigate_request_path.write_text(
        json.dumps(
            {
                "tool": "navigate_to_url",
                "arguments": {"url": validated_url, "sourceApp": SOURCE_APP},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    _run_taobao_request(
        "navigate_to_url",
        command_path,
        navigate_request_path,
        navigate_result_path,
    )

    detail_request_path.write_text(
        json.dumps(
            {
                "tool": "read_page_content",
                "arguments": {
                    "maxLength": PRODUCT_DETAIL_MAX_LENGTH,
                    "offset": 0,
                    "sourceApp": SOURCE_APP,
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    _run_taobao_request(
        "read_page_content",
        command_path,
        detail_request_path,
        detail_result_path,
    )
    try:
        response = json.loads(detail_result_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"Cannot read taobao product detail JSON: "
            f"path={detail_result_path} error={exc}"
        ) from exc
    detail = parse_product_detail_response(response, detail_result_path)
    requested_item_id = parse_qs(urlparse(validated_url).query)["id"][0]
    actual_item_id = detail["product"]["item_id"]
    if actual_item_id != requested_item_id:
        raise ValueError(
            f"Product detail does not match requested product: "
            f"requested_item_id={requested_item_id!r} "
            f"actual_item_id={actual_item_id!r} path={detail_result_path}"
        )
    return detail


def parse_product_sku_catalog_response(response, result_path):
    result = _response_result(response, result_path)
    if result.get("success") is not True:
        raise ValueError(
            f"Product SKU catalog response was not successful: "
            f"path={result_path} actual={result.get('success')!r}"
        )
    available_skus = result.get("availableSkus")
    if not isinstance(available_skus, list):
        raise ValueError(
            f"Product SKU catalog must contain availableSkus list: "
            f"path={result_path} actual={available_skus!r}"
        )

    dimensions = []
    seen_labels = set()
    for dimension_index, dimension in enumerate(available_skus):
        if not isinstance(dimension, dict):
            raise ValueError(
                f"Product SKU dimension must be an object: "
                f"path={result_path} index={dimension_index} actual={dimension!r}"
            )
        label = re.sub(
            r"\s*切换大图模式\s*$",
            "",
            str(dimension.get("label") or "").strip(),
        )
        if not label or label in seen_labels:
            continue
        raw_options = dimension.get("options")
        if not isinstance(raw_options, list):
            continue

        options_by_value = {}
        for raw_option in raw_options:
            if not isinstance(raw_option, dict):
                continue
            value = str(raw_option.get("text") or "").strip()
            if not value:
                continue
            image_url = _normalized_taobao_image_url(raw_option.get("image"))
            if image_url and "-2-tps-2-2.png" in image_url.casefold():
                image_url = None
            normalized_option = {
                "value": value,
                "available": raw_option.get("disabled") is not True,
                "selected": raw_option.get("selected") is True,
                "image_url": image_url,
            }
            existing = options_by_value.get(value)
            if existing is None:
                options_by_value[value] = normalized_option
            else:
                existing["available"] = existing["available"] or normalized_option["available"]
                existing["selected"] = existing["selected"] or normalized_option["selected"]
                existing["image_url"] = existing["image_url"] or normalized_option["image_url"]

        options = list(options_by_value.values())
        if not options:
            continue
        seen_labels.add(label)
        dimensions.append(
            {
                "label": label,
                "selected_value": str(dimension.get("selectedValue") or "").strip() or None,
                "options": options,
            }
        )
    return {
        "has_sku": bool(result.get("hasSku") or dimensions),
        "dimensions": dimensions,
        "message": str(result.get("message") or "").strip() or None,
    }


def capture_product_sku_catalog(
    item_id,
    request_directory,
    sku_catalog_result_path,
    *,
    command_path=None,
):
    normalized_item_id = str(item_id or "").strip()
    if not normalized_item_id.isdigit() or int(normalized_item_id) <= 0:
        raise ValueError(f"item_id must be numeric text: actual={item_id!r}")
    command_path = _validated_command_path(command_path)
    request_directory = Path(request_directory)
    sku_catalog_result_path = Path(sku_catalog_result_path)
    request_path = request_directory / "get-product-skus.json"
    if sku_catalog_result_path.exists():
        raise FileExistsError(
            f"SKU catalog result path already exists: path={sku_catalog_result_path}"
        )
    request_directory.mkdir(parents=True, exist_ok=True)
    sku_catalog_result_path.parent.mkdir(parents=True, exist_ok=True)
    request_path.write_text(
        json.dumps(
            {
                "tool": "get_product_skus",
                "arguments": {
                    "itemId": normalized_item_id,
                    "sourceApp": SOURCE_APP,
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    _run_taobao_request(
        "get_product_skus",
        command_path,
        request_path,
        sku_catalog_result_path,
    )
    response = _read_taobao_result(sku_catalog_result_path, "SKU catalog capture")
    return {
        **parse_product_sku_catalog_response(response, sku_catalog_result_path),
        "raw_source_ref": str(sku_catalog_result_path),
    }


def scan_product_sku_dimensions(
    request_directory,
    sku_result_path,
    *,
    item_id=None,
    sku_catalog_result_path=None,
    command_path=None,
):
    command_path = _validated_command_path(command_path)
    request_directory = Path(request_directory)
    sku_result_path = Path(sku_result_path)
    request_path = request_directory / "scan-sku-dimensions.json"
    if sku_result_path.exists():
        raise FileExistsError(
            f"SKU dimension result path already exists: path={sku_result_path}"
        )
    request_directory.mkdir(parents=True, exist_ok=True)
    sku_result_path.parent.mkdir(parents=True, exist_ok=True)
    sku_catalog = None
    if sku_catalog_result_path is not None:
        try:
            sku_catalog = capture_product_sku_catalog(
                item_id,
                request_directory,
                sku_catalog_result_path,
                command_path=command_path,
            )
        except (FileNotFoundError, RuntimeError, ValueError) as exc:
            sku_catalog = {
                "has_sku": False,
                "dimensions": [],
                "message": None,
                "raw_source_ref": None,
                "capture_error": str(exc),
            }
    request_path.write_text(
        json.dumps(
            {
                "tool": "scan_page_elements",
                "arguments": {"sourceApp": SOURCE_APP},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    _run_taobao_request(
        "scan_page_elements",
        command_path,
        request_path,
        sku_result_path,
    )
    response = _read_taobao_result(sku_result_path, "SKU dimension scan")
    parsed_dimensions = parse_sku_dimensions(response, sku_result_path)
    if sku_catalog is not None:
        parsed_dimensions["catalog"] = sku_catalog
    return parsed_dimensions


def _validated_sku_selections(selections):
    if not isinstance(selections, list) or not selections:
        raise ValueError(
            f"selected_options must be a non-empty list: actual={selections!r}"
        )
    validated = []
    seen_dimensions = set()
    seen_indices = set()
    for selection_index, selection in enumerate(selections):
        if not isinstance(selection, dict):
            raise ValueError(
                f"selected SKU option must be an object: "
                f"selection_index={selection_index} actual={selection!r}"
            )
        dimension = selection.get("dimension")
        value = selection.get("value")
        element_index = selection.get("index")
        if not isinstance(dimension, str) or not dimension.strip():
            raise ValueError(
                f"SKU dimension must be non-empty text: "
                f"selection_index={selection_index} actual={dimension!r}"
            )
        if not isinstance(value, str) or not value.strip():
            raise ValueError(
                f"SKU value must be non-empty text: "
                f"selection_index={selection_index} actual={value!r}"
            )
        if (
            not isinstance(element_index, int)
            or isinstance(element_index, bool)
            or element_index < 0
        ):
            raise ValueError(
                f"SKU element index must be a non-negative integer: "
                f"selection_index={selection_index} actual={element_index!r}"
            )
        normalized_dimension = dimension.strip()
        if normalized_dimension in seen_dimensions:
            raise ValueError(
                f"SKU dimension selected more than once: "
                f"actual={normalized_dimension!r}"
            )
        if element_index in seen_indices:
            raise ValueError(
                f"SKU element index selected more than once: actual={element_index}"
            )
        seen_dimensions.add(normalized_dimension)
        seen_indices.add(element_index)
        validated.append(
            {
                "dimension": normalized_dimension,
                "value": value.strip(),
                "index": element_index,
            }
        )
    return validated


def _read_taobao_result(result_path, operation_name):
    try:
        response = json.loads(result_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"Cannot read taobao {operation_name} JSON: "
            f"path={result_path} error={exc}"
        ) from exc
    if not isinstance(response, dict) or not isinstance(response.get("result"), dict):
        raise ValueError(
            f"taobao {operation_name} result must be an object: "
            f"path={result_path} actual={response!r}"
        )
    return response


def _validate_click_result(response, expected_index, result_path):
    result = response["result"]
    if result.get("disabled") is True:
        raise RuntimeError(
            f"SKU element is disabled: index={expected_index} path={result_path}"
        )
    if result.get("success") is not True:
        raise RuntimeError(
            f"SKU click did not succeed: index={expected_index} "
            f"path={result_path} actual={result!r}"
        )
    if result.get("index") != expected_index:
        raise RuntimeError(
            f"SKU click returned unexpected index: expected={expected_index} "
            f"actual={result.get('index')!r} path={result_path}"
        )


def capture_selected_sku_price(
    selected_options,
    display_price_text,
    request_directory,
    price_result_path,
    *,
    command_path=None,
):
    validated_options = _validated_sku_selections(selected_options)
    if display_price_text is not None and not isinstance(display_price_text, str):
        raise ValueError(
            f"display_price_text must be text or None: actual={display_price_text!r}"
        )
    command_path = _validated_command_path(command_path)
    request_directory = Path(request_directory)
    price_result_path = Path(price_result_path)
    request_directory.mkdir(parents=True, exist_ok=True)
    price_result_path.parent.mkdir(parents=True, exist_ok=True)

    for option_number, selected_option in enumerate(validated_options, start=1):
        click_request_path = request_directory / f"click-sku-{option_number:02d}.json"
        click_result_path = request_directory / f"click-result-{option_number:02d}.json"
        click_request_path.write_text(
            json.dumps(
                {
                    "tool": "click_element",
                    "arguments": {
                        "index": selected_option["index"],
                        "sourceApp": SOURCE_APP,
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        _run_taobao_request(
            "click_element",
            command_path,
            click_request_path,
            click_result_path,
        )
        click_response = _read_taobao_result(click_result_path, "SKU click")
        _validate_click_result(
            click_response,
            selected_option["index"],
            click_result_path,
        )

    time.sleep(3.0)
    price_request_path = request_directory / "scan-sku-price.json"
    price_request_path.write_text(
        json.dumps(
            {
                "tool": "scan_page_elements",
                "arguments": {"filter": "￥", "sourceApp": SOURCE_APP},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    _run_taobao_request(
        "scan_page_elements",
        command_path,
        price_request_path,
        price_result_path,
    )
    price_response = _read_taobao_result(price_result_path, "SKU price scan")
    parsed_price = parse_sku_price_scan(price_response, price_result_path)
    return {
        "selected_options": validated_options,
        "display_price_text": display_price_text,
        **parsed_price,
        "raw_price_ref": str(price_result_path),
    }


def _validate_search_response(response, result_path):
    if not isinstance(response, dict):
        raise ValueError(
            f"Search response must be an object: path={result_path} actual={response!r}"
        )

    result = response.get("result")
    if not isinstance(result, dict):
        raise ValueError(
            f"Search response result must be an object: path={result_path} actual={result!r}"
        )

    keyword = result.get("keyword")
    if not isinstance(keyword, str) or not keyword.strip():
        raise ValueError(
            f"Search response keyword must be non-empty text: path={result_path} actual={keyword!r}"
        )

    count = result.get("count")
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        raise ValueError(
            f"Search response count must be a non-negative integer: path={result_path} actual={count!r}"
        )

    products = result.get("products")
    if not isinstance(products, list):
        raise ValueError(
            f"Search response products must be a list: path={result_path} actual={products!r}"
        )
    for product_index, product in enumerate(products):
        if not isinstance(product, dict):
            raise ValueError(
                f"Search response product must be an object: path={result_path} "
                f"product_index={product_index} actual={product!r}"
            )


def run_search_products(
    keyword,
    request_path,
    result_path,
    *,
    command_path=None,
):
    if not isinstance(keyword, str) or not keyword.strip():
        raise ValueError(f"keyword must be non-empty text: keyword={keyword!r}")

    request_path = Path(request_path)
    result_path = Path(result_path)
    if request_path == result_path:
        raise ValueError(
            f"request_path and result_path must differ: actual={request_path}"
        )
    if result_path.exists():
        raise FileExistsError(
            f"Search result path already exists: path={result_path}"
        )

    if command_path is None:
        command_path = resolve_taobao_native_command()
    else:
        command_path = Path(command_path)
        if not command_path.is_file():
            raise FileNotFoundError(
                f"taobao-native command does not exist: path={command_path}"
            )

    request_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.parent.mkdir(parents=True, exist_ok=True)
    request_payload = {
        "tool": "search_products",
        "arguments": {
            "keyword": keyword,
            "sourceApp": SOURCE_APP,
        },
    }
    request_path.write_text(
        json.dumps(request_payload, ensure_ascii=False),
        encoding="utf-8",
    )

    command = [
        str(command_path),
        "--request",
        str(request_path),
        "-o",
        str(result_path),
    ]
    completed_command = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if completed_command.returncode != 0:
        raise RuntimeError(
            f"taobao-native search failed: exit_code={completed_command.returncode} "
            f"stdout={completed_command.stdout!r} stderr={completed_command.stderr!r}"
        )
    if not result_path.is_file():
        raise FileNotFoundError(
            f"taobao-native did not create search result: path={result_path}"
        )

    try:
        response = json.loads(result_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"Cannot read taobao search result JSON: path={result_path} error={exc}"
        ) from exc

    _validate_search_response(response, result_path)
    return response


def _required_item_id(product, product_index):
    item_id = product.get("itemId")
    if not isinstance(item_id, str) or not item_id.strip():
        raise ValueError(
            f"Search product itemId must be non-empty text: "
            f"product_index={product_index} itemId={item_id!r}"
        )
    return item_id.strip()


def _optional_text(product, field_name, product_index):
    value = product.get(field_name)
    if value is None:
        return None
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        raise ValueError(
            f"Search product field must be text or number: "
            f"product_index={product_index} field={field_name} actual={value!r}"
        )
    return str(value)


def _platform_type(product_url):
    hostname = (urlparse(product_url or "").hostname or "").casefold()
    if hostname == "tmall.com" or hostname.endswith(".tmall.com"):
        return "tmall"
    if hostname == "taobao.com" or hostname.endswith(".taobao.com"):
        return "taobao"
    return "unknown"


def _suspected_ad(product, product_index):
    value = product.get("suspectedAd", product.get("isAd"))
    if value is None:
        return None
    if value is True or value == 1:
        return 1
    if value is False or value == 0:
        return 0
    raise ValueError(
        f"Search product suspected ad flag must be bool or 0/1: "
        f"product_index={product_index} actual={value!r}"
    )


def _parsed_search_products(products, requested_result_count):
    parsed_products = []
    for product_index, product in enumerate(products[:requested_result_count]):
        item_id = _required_item_id(product, product_index)
        product_url = canonicalize_search_product_url(
            _optional_text(product, "productUrl", product_index),
            item_id,
        )
        parsed_products.append(
            {
                "item_id": item_id,
                "sku_id": _optional_text(product, "skuId", product_index),
                "title": _optional_text(product, "title", product_index),
                "shop_name": _optional_text(product, "shopName", product_index),
                "display_price": _optional_text(product, "price", product_index),
                "product_url": product_url,
                "shop_url": _optional_text(product, "shopUrl", product_index),
                "image_url": _optional_text(product, "image", product_index),
                "platform_type": _platform_type(product_url),
                "suspected_ad": _suspected_ad(product, product_index),
                "payment_text": _optional_text(product, "paymentText", product_index),
                "origin_text": _optional_text(product, "originText", product_index),
                "promotion_text": _optional_text(product, "promotionText", product_index),
                "logistics_text": _optional_text(product, "logisticsText", product_index),
                "card_text": _optional_text(product, "cardText", product_index),
            }
        )
    return parsed_products


def _validate_capture_arguments(project_id, requested_result_count, captured_at):
    if not isinstance(project_id, int) or isinstance(project_id, bool) or project_id <= 0:
        raise ValueError(f"project_id must be a positive integer: actual={project_id!r}")
    if requested_result_count not in (10, 20, 30):
        raise ValueError(
            f"requested_result_count must be 10, 20, or 30: "
            f"requested_result_count={requested_result_count!r}"
        )
    if not isinstance(captured_at, str):
        raise ValueError(f"captured_at must be ISO text: actual={captured_at!r}")
    try:
        captured_datetime = datetime.fromisoformat(captured_at)
    except ValueError as exc:
        raise ValueError(f"captured_at must be ISO text: actual={captured_at!r}") from exc
    if captured_datetime.tzinfo is None:
        raise ValueError(f"captured_at must include timezone: actual={captured_at!r}")


def _archive_raw_response(source_result_path, raw_archive_path):
    source_result_path = Path(source_result_path)
    raw_archive_path = Path(raw_archive_path)
    if not source_result_path.is_file():
        raise FileNotFoundError(f"Search source result does not exist: path={source_result_path}")
    if raw_archive_path.exists():
        raise FileExistsError(f"Raw search archive already exists: path={raw_archive_path}")

    response_bytes = source_result_path.read_bytes()
    raw_archive_path.parent.mkdir(parents=True, exist_ok=True)
    partial_path = raw_archive_path.parent / (
        f".{raw_archive_path.name}.{uuid4().hex}.partial"
    )
    try:
        with partial_path.open("xb") as partial_file:
            partial_file.write(response_bytes)
            partial_file.flush()
            os.fsync(partial_file.fileno())
        os.replace(partial_path, raw_archive_path)
    finally:
        if partial_path.exists():
            partial_path.unlink()
    return response_bytes


def archive_and_save_search_result(
    application_data_directory,
    project_id,
    source_result_path,
    raw_archive_path,
    requested_result_count,
    captured_at,
    *,
    save_all_results=False,
):
    _validate_capture_arguments(project_id, requested_result_count, captured_at)
    response_bytes = _archive_raw_response(source_result_path, raw_archive_path)

    try:
        response = json.loads(response_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"Cannot parse archived search JSON: path={raw_archive_path} error={exc}"
        ) from exc
    _validate_search_response(response, raw_archive_path)

    result = response["result"]
    parsed_products = _parsed_search_products(
        result["products"],
        len(result["products"]) if save_all_results else requested_result_count,
    )
    search_type = result.get("type", "all")
    if search_type not in ("all", "taobao", "tmall"):
        raise ValueError(
            f"Search response type must be all, taobao, or tmall: "
            f"path={raw_archive_path} actual={search_type!r}"
        )

    with closing(connect_database(application_data_directory)) as connection:
        snapshot_id = save_search_snapshot(
            connection,
            project_id,
            result["keyword"],
            search_type,
            requested_result_count,
            captured_at,
            str(raw_archive_path),
            parsed_products,
        )

    return {
        "snapshot_id": snapshot_id,
        "captured_at": captured_at,
        "requested_result_count": requested_result_count,
        "result_count": len(parsed_products),
        "raw_source_ref": str(raw_archive_path),
        "results": [
            search_result_response(parsed_product, display_rank, captured_at)
            for display_rank, parsed_product in enumerate(parsed_products, start=1)
        ],
    }
