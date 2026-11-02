import re
from urllib.parse import urlsplit, urlunsplit


PRICE_CHANGE_MINIMUM = 10.0
PRICE_CHANGE_RATIO = 0.10
RANK_CHANGE_MINIMUM = 5


def _text(value):
    return " ".join(str(value or "").split())


def _number(value):
    match = re.search(r"\d+(?:\.\d+)?", _text(value).replace(",", ""))
    return float(match.group()) if match else None


def _payment_count(value):
    text = _text(value).replace(",", "")
    match = re.search(r"(\d+(?:\.\d+)?)\s*([万千]?)\s*\+?\s*(?:人)?(?:付款|购买|已售|销量)", text)
    if not match:
        return None
    multiplier = {"万": 10000, "千": 1000}.get(match.group(2), 1)
    return int(float(match.group(1)) * multiplier)


def _canonical_image_url(value):
    text = _text(value)
    if not text:
        return ""
    parsed = urlsplit(text)
    # Taobao often appends resize/crop instructions to the same image URL.
    path = re.sub(r"_(?:\d+x\d+|q\d+|sum|webp)(?:[^/]*)$", "", parsed.path, flags=re.I)
    return urlunsplit((parsed.scheme.casefold(), parsed.netloc.casefold(), path, "", ""))


def _change(*, priority, category, title, summary, reason, item_id=None, before=None, after=None, product_url=None):
    return {
        "priority": priority,
        "category": category,
        "title": _text(title) or "未命名商品",
        "summary": summary,
        "reason": reason,
        "item_id": str(item_id) if item_id is not None else None,
        "before": before,
        "after": after,
        "product_url": product_url,
    }


def _crossed_rank_boundary(old_rank, new_rank, boundary):
    return (old_rank <= boundary < new_rank) or (new_rank <= boundary < old_rank)


def summarize_keyword_changes(diff):
    """Reduce a raw search snapshot diff to changes an operator should act on."""
    changes = []
    for entry in diff.get("added") or []:
        rank = entry.get("display_rank")
        if not isinstance(rank, int) or rank > 20:
            continue
        changes.append(
            _change(
                priority="high" if rank <= 10 else "medium",
                category="新品进入",
                title=entry.get("title"),
                summary=f"新进入搜索前 20，目前第 {rank} 名",
                reason="前排新增商品可能正在获得流量，值得检查价格、主图和卖点。",
                item_id=entry.get("item_id"),
                after=rank,
                product_url=entry.get("product_url"),
            )
        )
    for entry in diff.get("removed") or []:
        rank = entry.get("display_rank")
        if not isinstance(rank, int) or rank > 20:
            continue
        changes.append(
            _change(
                priority="high" if rank <= 10 else "medium",
                category="商品退出",
                title=entry.get("title"),
                summary=f"原第 {rank} 名，现已退出当前采集范围",
                reason="可能是排名下滑、链接下架或搜索结果发生调整。",
                item_id=entry.get("item_id"),
                before=rank,
                product_url=entry.get("product_url"),
            )
        )
    for entry in diff.get("rank_changes") or []:
        old_rank = entry.get("old_rank")
        new_rank = entry.get("new_rank")
        if not isinstance(old_rank, int) or not isinstance(new_rank, int):
            continue
        distance = abs(new_rank - old_rank)
        boundary_crossed = any(_crossed_rank_boundary(old_rank, new_rank, boundary) for boundary in (10, 20))
        if distance < RANK_CHANGE_MINIMUM and not boundary_crossed:
            continue
        direction = "上升" if new_rank < old_rank else "下降"
        changes.append(
            _change(
                priority="high" if distance >= 10 or _crossed_rank_boundary(old_rank, new_rank, 10) else "medium",
                category="排名异动",
                title=entry.get("title"),
                summary=f"排名从第 {old_rank} 名{direction}到第 {new_rank} 名（{distance} 位）",
                reason="明显排名变化通常对应流量、价格、转化或投放策略变化。",
                item_id=entry.get("item_id"),
                before=old_rank,
                after=new_rank,
            )
        )
    for entry in diff.get("price_changes") or []:
        old_price = _number(entry.get("old_price"))
        new_price = _number(entry.get("new_price"))
        if old_price is None or new_price is None or old_price <= 0:
            continue
        distance = abs(new_price - old_price)
        ratio = distance / old_price
        if distance < PRICE_CHANGE_MINIMUM and ratio < PRICE_CHANGE_RATIO:
            continue
        direction = "降价" if new_price < old_price else "涨价"
        changes.append(
            _change(
                priority="high" if ratio >= 0.20 or distance >= 30 else "medium",
                category="价格变化",
                title=entry.get("title"),
                summary=f"{direction}：¥{old_price:g} → ¥{new_price:g}（{ratio:.0%}）",
                reason="价格变化达到 ¥10 或 10%，可能影响价格带和转化。",
                item_id=entry.get("item_id"),
                before=entry.get("old_price"),
                after=entry.get("new_price"),
            )
        )
    for entry in diff.get("payment_changes") or []:
        old_count = _payment_count(entry.get("old_value"))
        new_count = _payment_count(entry.get("new_value"))
        if old_count is None or new_count is None or old_count == new_count:
            continue
        changes.append(
            _change(
                priority="high" if new_count >= max(1000, old_count * 2) else "medium",
                category="付款增长",
                title=entry.get("title"),
                summary=f"付款档位：{_text(entry.get('old_value'))} → {_text(entry.get('new_value'))}",
                reason="付款人数跨档，说明该商品近期成交热度发生明显变化。",
                item_id=entry.get("item_id"),
                before=entry.get("old_value"),
                after=entry.get("new_value"),
            )
        )
    for field_name, category, reason in (
        ("promotion_changes", "促销变化", "补贴、优惠或活动变化会直接影响到手价和竞争力。"),
        ("logistics_changes", "履约变化", "发货、包邮或时效承诺变化会影响下单决策。"),
        ("shop_changes", "店铺变化", "店铺归属变化需要确认链接、授权或经营主体是否调整。"),
        ("title_changes", "标题变化", "标题调整通常反映关键词、定位或卖点策略变化。"),
        ("image_changes", "主图变化", "主图更换可能意味着点击率测试或视觉策略调整。"),
    ):
        for entry in diff.get(field_name) or []:
            changes.append(
                _change(
                    priority="medium",
                    category=category,
                    title=entry.get("title"),
                    summary=(
                        "商品主图已更换"
                        if field_name == "image_changes"
                        else f"{_text(entry.get('old_value')) or '未提供'} → {_text(entry.get('new_value')) or '未提供'}"
                    ),
                    reason=reason,
                    item_id=entry.get("item_id"),
                    before=entry.get("old_value"),
                    after=entry.get("new_value"),
                )
            )
    return sorted(changes, key=lambda item: (item["priority"] != "high", item["category"], item["title"]))


def _archive(snapshot):
    return snapshot.get("archive") or {}


def _field(snapshot, name):
    archive_fields = _archive(snapshot).get("product_fields") or {}
    return archive_fields.get(name) or snapshot.get(name)


def _image_set(snapshot, kind):
    return {
        _canonical_image_url(item.get("url"))
        for item in (_archive(snapshot).get("images") or [])
        if isinstance(item, dict) and item.get("kind") == kind and _canonical_image_url(item.get("url"))
    }


def _sku_state(snapshot):
    catalog = _archive(snapshot).get("sku_catalog") or {}
    values = set()
    images = set()
    availability = {}
    for dimension in catalog.get("dimensions") or []:
        label = _text(dimension.get("label"))
        for option in dimension.get("options") or []:
            value = _text(option.get("value"))
            if not value:
                continue
            key = (label, value)
            values.add(key)
            availability[key] = option.get("available") is not False
            image = _canonical_image_url(option.get("image_url"))
            if image:
                images.add((label, value, image))
    return values, images, availability


def summarize_competitor_changes(older, newer):
    """Compare two saved competitor snapshots and keep only actionable changes."""
    title = newer.get("title") or older.get("title")
    item_id = newer.get("item_id") or older.get("item_id")
    product_url = newer.get("page_url") or older.get("page_url")
    changes = []

    for name, category, reason, priority in (
        ("title", "标题变化", "竞品可能在调整关键词、定位或主卖点。", "medium"),
        ("shop_name", "店铺变化", "经营主体或链接归属变化，需要确认商品是否仍可比。", "high"),
    ):
        old_value = _text(older.get(name))
        new_value = _text(newer.get(name))
        if old_value and new_value and old_value != new_value:
            changes.append(_change(priority=priority, category=category, title=title, summary=f"{old_value} → {new_value}", reason=reason, item_id=item_id, before=old_value, after=new_value, product_url=product_url))

    old_price = _number(_field(older, "price_text") or older.get("visible_price_text"))
    new_price = _number(_field(newer, "price_text") or newer.get("visible_price_text"))
    if old_price and new_price and old_price != new_price:
        distance = abs(new_price - old_price)
        ratio = distance / old_price
        if distance >= PRICE_CHANGE_MINIMUM or ratio >= PRICE_CHANGE_RATIO:
            direction = "降价" if new_price < old_price else "涨价"
            changes.append(_change(priority="high" if ratio >= .20 or distance >= 30 else "medium", category="价格变化", title=title, summary=f"{direction}：¥{old_price:g} → ¥{new_price:g}（{ratio:.0%}）", reason="价格变化达到监控阈值，会影响竞争价格带。", item_id=item_id, before=old_price, after=new_price, product_url=product_url))

    old_payment = _field(older, "payment_text") or _field(older, "sold_text")
    new_payment = _field(newer, "payment_text") or _field(newer, "sold_text")
    old_count, new_count = _payment_count(old_payment), _payment_count(new_payment)
    if old_count is not None and new_count is not None and old_count != new_count:
        changes.append(_change(priority="high" if new_count >= max(1000, old_count * 2) else "medium", category="付款增长", title=title, summary=f"{_text(old_payment)} → {_text(new_payment)}", reason="付款档位变化反映竞品近期成交热度。", item_id=item_id, before=old_payment, after=new_payment, product_url=product_url))

    for field_name, category, reason in (
        ("promotions", "促销变化", "优惠与补贴变化会影响真实成交价。"),
        ("logistics", "履约变化", "发货和时效承诺变化会影响转化。"),
        ("services", "服务变化", "服务承诺变化会改变信任与售后竞争力。"),
    ):
        old_values = {_text(value) for value in (_field(older, field_name) or []) if _text(value)}
        new_values = {_text(value) for value in (_field(newer, field_name) or []) if _text(value)}
        if old_values != new_values and (old_values or new_values):
            added = sorted(new_values - old_values)
            removed = sorted(old_values - new_values)
            parts = []
            if added:
                parts.append("新增 " + "、".join(added[:3]))
            if removed:
                parts.append("取消 " + "、".join(removed[:3]))
            changes.append(_change(priority="medium", category=category, title=title, summary="；".join(parts), reason=reason, item_id=item_id, before=sorted(old_values), after=sorted(new_values), product_url=product_url))

    for kind, category, reason in (
        ("main", "主图变化", "主图变化通常代表点击率测试或视觉策略调整。"),
        ("detail", "详情页变化", "详情图结构变化可能对应卖点、信任或转化内容调整。"),
    ):
        old_images, new_images = _image_set(older, kind), _image_set(newer, kind)
        if old_images != new_images and (old_images or new_images):
            changes.append(_change(priority="high" if kind == "main" else "medium", category=category, title=title, summary=f"{len(old_images)} 张 → {len(new_images)} 张，新增 {len(new_images - old_images)} 张、移除 {len(old_images - new_images)} 张", reason=reason, item_id=item_id, before=len(old_images), after=len(new_images), product_url=product_url))

    old_values, old_sku_images, old_availability = _sku_state(older)
    new_values, new_sku_images, new_availability = _sku_state(newer)
    if old_values != new_values:
        changes.append(_change(priority="high", category="SKU 变化", title=title, summary=f"规格新增 {len(new_values - old_values)} 项、减少 {len(old_values - new_values)} 项", reason="SKU 增减可能反映上新、断货或主推款调整。", item_id=item_id, before=len(old_values), after=len(new_values), product_url=product_url))
    unavailable = [key for key in old_values & new_values if old_availability.get(key) and not new_availability.get(key)]
    if unavailable:
        changes.append(_change(priority="high", category="SKU 缺货", title=title, summary=f"{len(unavailable)} 个规格由可售变为不可售", reason="核心规格缺货会影响竞品成交与我们承接流量的机会。", item_id=item_id, before=True, after=False, product_url=product_url))
    if old_sku_images != new_sku_images and (old_sku_images or new_sku_images):
        changes.append(_change(priority="medium", category="SKU 图变化", title=title, summary=f"SKU 图新增 {len(new_sku_images - old_sku_images)} 张、移除 {len(old_sku_images - new_sku_images)} 张", reason="SKU 图调整可能代表款式展示或主推规格变化。", item_id=item_id, before=len(old_sku_images), after=len(new_sku_images), product_url=product_url))

    old_reviews = _archive(older).get("reviews") or {}
    new_reviews = _archive(newer).get("reviews") or {}
    old_total = _number(old_reviews.get("total_text") or older.get("review_count_text"))
    new_total = _number(new_reviews.get("total_text") or newer.get("review_count_text"))
    if old_total is not None and new_total is not None and new_total > old_total:
        added = int(new_total - old_total)
        changes.append(_change(priority="medium", category="评价增长", title=title, summary=f"评价新增约 {added} 条（{int(old_total)} → {int(new_total)}）", reason="评价增长速度可辅助判断近期成交和口碑积累。", item_id=item_id, before=int(old_total), after=int(new_total), product_url=product_url))

    return sorted(changes, key=lambda item: (item["priority"] != "high", item["category"], item["title"]))


def summarize_shop_changes(current, previous=None, previous_previous=None):
    """Report shop launches immediately and possible removals after two misses."""
    if not previous:
        return []
    current_items = {str(item.get("item_id")): item for item in current.get("products") or []}
    previous_items = {str(item.get("item_id")): item for item in previous.get("products") or []}
    older_items = {
        str(item.get("item_id")): item
        for item in (previous_previous or {}).get("products") or []
    }
    changes = []
    for item_id in sorted(current_items.keys() - previous_items.keys()):
        item = current_items[item_id]
        changes.append(_change(
            priority="high",
            category="店铺上新",
            title=item.get("title"),
            summary="首次监测到该商品出现在店铺商品列表",
            reason="建议及时查看新品定位、价格、主图和规格组合。",
            item_id=item_id,
            product_url=item.get("product_url"),
        ))
    if previous_previous:
        twice_missing = older_items.keys() - previous_items.keys() - current_items.keys()
        for item_id in sorted(twice_missing):
            item = older_items[item_id]
            changes.append(_change(
                priority="medium",
                category="疑似下架",
                title=item.get("title"),
                summary="连续两次监控未在店铺商品列表中发现",
                reason="可能已下架、售罄或移出当前列表，建议打开店铺核对。",
                item_id=item_id,
                product_url=item.get("product_url"),
            ))
    return sorted(changes, key=lambda item: (item["priority"] != "high", item["category"], item["title"]))
