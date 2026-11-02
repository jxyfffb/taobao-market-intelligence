import hashlib
import json
import re


PRICE_PATTERN = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


def parse_price_value(value):
    if value is None:
        return None
    match = PRICE_PATTERN.search(str(value).strip())
    if match is None:
        return None
    try:
        return round(float(match.group(0).replace(",", "")), 2)
    except ValueError:
        return None


def _price_summary(points):
    values = [point["price_value"] for point in points]
    if not values:
        return {
            "current": None,
            "previous": None,
            "change": None,
            "change_percent": None,
            "minimum": None,
            "maximum": None,
            "point_count": 0,
        }
    current = values[-1]
    previous = values[-2] if len(values) > 1 else None
    change = round(current - previous, 2) if previous is not None else None
    change_percent = (
        round(change / previous * 100, 1)
        if change is not None and previous != 0
        else None
    )
    return {
        "current": current,
        "previous": previous,
        "change": change,
        "change_percent": change_percent,
        "minimum": min(values),
        "maximum": max(values),
        "point_count": len(values),
    }


def _price_point(snapshot, price_text):
    price_value = parse_price_value(price_text)
    if price_value is None:
        return None
    return {
        "captured_at": snapshot.get("captured_at"),
        "price_text": str(price_text),
        "price_value": price_value,
    }


def _normalized_options(selected_options):
    return [
        {
            "dimension": str(option.get("dimension") or "规格").strip(),
            "value": str(option.get("value") or "未命名").strip(),
        }
        for option in (selected_options or [])
    ]


def _sku_identity(selected_options):
    options = _normalized_options(selected_options)
    serialized = json.dumps(options, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(serialized.encode("utf-8")).hexdigest()[:12], options


def build_competitor_history(snapshots):
    chronological = list(reversed(snapshots or []))
    page_points = []
    sku_groups = {}

    for snapshot in chronological:
        page_point = _price_point(snapshot, snapshot.get("visible_price_text"))
        if page_point is not None:
            page_points.append(page_point)

        sku = snapshot.get("sku") or {}
        if sku.get("price_status") != "captured":
            continue
        sku_point = _price_point(snapshot, sku.get("sku_price_text"))
        if sku_point is None:
            continue
        sku_key, options = _sku_identity(sku.get("selected_options"))
        group = sku_groups.setdefault(
            sku_key,
            {
                "key": sku_key,
                "label": " / ".join(
                    f'{option["dimension"]}：{option["value"]}' for option in options
                )
                or "目标 SKU",
                "selected_options": options,
                "points": [],
            },
        )
        group["points"].append(sku_point)

    sku_histories = []
    for group in sku_groups.values():
        group["summary"] = _price_summary(group["points"])
        sku_histories.append(group)
    sku_histories.sort(
        key=lambda group: group["points"][-1].get("captured_at") or "",
        reverse=True,
    )

    return {
        "page_price": {
            "basis": "page_visible",
            "label": "页面可见价",
            "points": page_points,
            "summary": _price_summary(page_points),
        },
        "sku_prices": sku_histories,
    }
