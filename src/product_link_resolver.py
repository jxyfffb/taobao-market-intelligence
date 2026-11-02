import html
import re
from urllib import request
from urllib import error
from urllib.parse import parse_qs, urlparse

from src.collector import validate_product_detail_url


URL_PATTERN = re.compile(r"https?://[^\s\"'<>，。；、）)]+", re.IGNORECASE)
TRUSTED_MARKETPLACE_SUFFIXES = ("taobao.com", "tmall.com", "tb.cn")


def _trusted_hostname(hostname):
    hostname = str(hostname or "").casefold().rstrip(".")
    return any(
        hostname == suffix or hostname.endswith(f".{suffix}")
        for suffix in TRUSTED_MARKETPLACE_SUFFIXES
    )


def _extract_urls(text):
    decoded = html.unescape(str(text or "")).replace("\\/", "/")
    return [match.group(0).rstrip(".,;，。；、]") for match in URL_PATTERN.finditer(decoded)]


def _canonical_item_url(candidate):
    candidate = str(candidate or "").strip()
    try:
        return validate_product_detail_url(candidate)
    except ValueError:
        pass

    parsed = urlparse(candidate)
    hostname = (parsed.hostname or "").casefold()
    item_ids = parse_qs(parsed.query).get("id", [])
    if (
        parsed.scheme.casefold() != "https"
        or not _trusted_hostname(hostname)
        or len(item_ids) != 1
        or not item_ids[0].isdigit()
        or int(item_ids[0]) <= 0
    ):
        return None
    canonical_host = "detail.tmall.com" if "tmall.com" in hostname else "item.taobao.com"
    return f"https://{canonical_host}/item.htm?id={item_ids[0]}"


def _default_fetch_short_url(url):
    request_value = request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/126 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
        },
        method="GET",
    )
    with request.urlopen(request_value, timeout=12) as response:
        raw_content = response.read(700000)
        charset = response.headers.get_content_charset() or "utf-8"
        return {
            "final_url": response.geturl(),
            "content": raw_content.decode(charset, errors="ignore"),
        }


def resolve_product_link(value, *, fetch_short_url=None):
    """Extract and resolve one trusted Taobao/Tmall product link.

    The function accepts a plain URL or a copied marketplace share message. Network
    access is used only for ``*.tb.cn`` share links; tests inject a deterministic
    resolver so no public request is required.
    """

    urls = _extract_urls(value)
    if not urls:
        raise ValueError("没有识别到商品链接，请粘贴淘宝/天猫链接或分享内容。")
    source_url = urls[0]
    parsed_source = urlparse(source_url)
    source_host = (parsed_source.hostname or "").casefold()
    if parsed_source.scheme.casefold() != "https" or not _trusted_hostname(source_host):
        raise ValueError("仅支持 HTTPS 淘宝/天猫商品链接和官方分享短链。")

    canonical_url = _canonical_item_url(source_url)
    if canonical_url is None and (
        source_host == "tb.cn" or source_host.endswith(".tb.cn")
    ):
        try:
            fetch_result = (fetch_short_url or _default_fetch_short_url)(source_url)
        except (error.HTTPError, error.URLError, OSError, TimeoutError) as exc:
            raise ValueError("分享短链暂时无法打开，请复制完整商品链接后重试。") from exc
        if not isinstance(fetch_result, dict):
            raise ValueError("分享短链解析结果无效，请复制完整商品链接后重试。")
        candidates = [fetch_result.get("final_url"), *_extract_urls(fetch_result.get("content"))]
        for candidate in candidates:
            canonical_url = _canonical_item_url(candidate)
            if canonical_url is not None:
                break

    if canonical_url is None:
        raise ValueError("没有从链接中识别到有效的淘宝/天猫商品 ID。")
    validated_url = validate_product_detail_url(canonical_url)
    item_id = parse_qs(urlparse(validated_url).query)["id"][0]
    return {
        "input_text": str(value or "").strip(),
        "source_url": source_url,
        "resolved_url": validated_url,
        "item_id": item_id,
    }
