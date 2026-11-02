import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse


BUYER_LINK_HOSTS = {
    "click.simba.taobao.com",
    "detail.tmall.com",
    "item.taobao.com",
}


def _trusted_buyer_url(value, item_id):
    candidate = str(value or "").strip()
    expected_item_id = str(item_id or "").strip()
    if not candidate or not expected_item_id:
        return None
    try:
        parsed = urlparse(candidate)
        port = parsed.port
    except ValueError:
        return None
    query_item_ids = parse_qs(parsed.query).get("id", [])
    if (
        parsed.scheme.casefold() != "https"
        or (parsed.hostname or "").casefold() not in BUYER_LINK_HOSTS
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or query_item_ids != [expected_item_id]
    ):
        return None
    return candidate


def buyer_urls_from_raw_sources(raw_source_refs, item_ids=None):
    wanted = None if item_ids is None else {str(value) for value in item_ids}
    recovered = {}
    for raw_source_ref in raw_source_refs or []:
        path = Path(str(raw_source_ref or "").strip())
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        products = payload.get("products") if isinstance(payload, dict) else None
        if not isinstance(products, list):
            continue
        for product in products:
            if not isinstance(product, dict):
                continue
            item_id = str(product.get("itemId") or product.get("item_id") or "").strip()
            if not item_id or (wanted is not None and item_id not in wanted):
                continue
            buyer_url = _trusted_buyer_url(
                product.get("productUrl") or product.get("buyer_url") or product.get("product_url"),
                item_id,
            )
            if buyer_url:
                recovered.setdefault(item_id, buyer_url)
        if wanted is not None and wanted.issubset(recovered):
            break
    return recovered
