from html import unescape
from decimal import Decimal, InvalidOperation
import re


SKU_DIMENSION_KEYWORDS = (
    "规格",
    "型号",
    "颜色",
    "尺码",
    "尺寸",
    "容量",
    "套餐",
    "版本",
    "款式",
    "口味",
    "净含量",
    "适用",
)
PROMOTIONAL_TEXTS = {
    "推荐",
    "近期热销",
    "热销",
    "热门",
    "爆款",
    "新品",
}
PROMOTIONAL_SUFFIXES = tuple(
    sorted(PROMOTIONAL_TEXTS, key=len, reverse=True)
)
PLAIN_LINE_PATTERN = re.compile(r"(?m)^(?P<label>[^\[\]<>\r\n]{1,40})\r?$")
INDEXED_SPAN_PATTERN = re.compile(
    r"(?m)^\s*\[(?P<index>\d+)\]\s*"
    r"<span(?:\s[^>]*)?>(?P<text>.*?)</span>\s*$"
)
BUTTON_PATTERN = re.compile(r"(?m)^\s*\[\d+\]\s*<button(?:\s|/|>)")

EVIDENCE_LEGEND = (
    {
        "key": "program_fact",
        "code": "A",
        "label": "程序事实",
        "description": "直接来自已保存快照或确定性字段映射，可回到原始证据复核。",
    },
    {
        "key": "rule_judgment",
        "code": "B",
        "label": "规则判断",
        "description": "由明确规则对已保存事实进行判断，不等同于真实经营结果。",
    },
    {
        "key": "ai_inference",
        "code": "C",
        "label": "AI 推测",
        "description": "基于已引用证据的解释性推测，必须与事实分开。",
    },
    {
        "key": "missing",
        "code": "D",
        "label": "数据缺失",
        "description": "当前快照不足以支持结论，不使用其他字段或推测回填。",
    },
)

REVIEW_SIGNAL_GROUPS = {
    "recognized_points": (
        ("质量做工", ("质量", "做工", "结实", "耐用")),
        ("外观颜色", ("好看", "外观", "颜色", "颜值")),
        ("尺寸适配", ("合适", "贴合", "尺寸", "适配")),
        ("使用体验", ("手感", "舒服", "好用", "方便")),
        ("履约服务", ("物流", "发货", "客服", "包装")),
    ),
    "concerns": (
        ("质量瑕疵", ("破损", "开胶", "掉色", "划痕", "质量差")),
        ("规格不符", ("不合适", "偏大", "偏小", "不贴合", "尺寸不符")),
        ("感官问题", ("色差", "异味", "难看", "手感差")),
        ("履约问题", ("物流慢", "发货慢", "包装破", "客服差")),
    ),
    "repeat_reasons": (
        ("明确复购", ("回购", "复购", "再次购买", "第二次买", "又买")),
    ),
    "unmet_needs": (
        ("期待改进", ("希望", "建议", "要是", "不够", "不支持", "不能")),
    ),
}


def _required_analysis_text(field_name, value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty text: actual={value!r}")
    return " ".join(value.split())


def _evidence_value(value, source_fields, note, *, price_scope=None):
    missing = value is None or value == "" or value == []
    result = {
        "value": None if missing else value,
        "evidence_level": "missing" if missing else "program_fact",
        "source_fields": list(source_fields),
        "note": note,
    }
    if price_scope is not None:
        result["price_scope"] = price_scope
    return result


def _missing_analysis_value(note, source_fields=()):
    return {
        "value": None,
        "evidence_level": "missing",
        "source_fields": list(source_fields),
        "note": note,
    }


def _review_cluster_evidence(review_items, review_tags, cluster_key):
    grouped_hits = []
    for label, keywords in REVIEW_SIGNAL_GROUPS[cluster_key]:
        matching_items = []
        for item in review_items:
            content = str(item.get("content") or "").strip()
            if content and any(keyword in content for keyword in keywords):
                matching_items.append(content)
        if matching_items:
            grouped_hits.append((label, len(matching_items), matching_items[0][:42]))

    if cluster_key == "recognized_points" and review_tags:
        tags = [str(tag).strip() for tag in review_tags[:8] if str(tag).strip()]
        if tags:
            grouped_hits.insert(0, (f"页面标签：{'、'.join(tags)}", len(tags), ""))

    if not grouped_hits:
        return _missing_analysis_value(
            f"已读取 {len(review_items)} 条评价，但未发现可稳定归入该类的明确信号。",
            ("product_snapshot.archive.reviews.items",),
        )

    value_parts = []
    for label, count, example in grouped_hits[:5]:
        value_parts.append(f"{label}（{count} 条）" + (f"：{example}" if example else ""))
    return _evidence_value(
        "；".join(value_parts),
        ("product_snapshot.archive.reviews.items", "product_snapshot.archive.reviews.tags"),
        f"基于已保存的 {len(review_items)} 条评价做关键词规则归类；仅表示样本信号，不等于全量评价占比。",
    )


def _search_context(item_id, search_result, display_rank):
    if search_result is None:
        if display_rank is not None:
            raise ValueError(
                "display_rank requires search_result: "
                f"item_id={item_id!r} display_rank={display_rank!r}"
            )
        return None, None
    if not isinstance(search_result, dict):
        raise ValueError(
            f"search_result must be an object or None: actual={search_result!r}"
        )
    search_item_id = str(search_result.get("item_id") or "").strip()
    if search_item_id != item_id:
        raise ValueError(
            "search_result item_id does not match competitor: "
            f"expected={item_id!r} actual={search_item_id!r}"
        )
    if display_rank is not None and (
        not isinstance(display_rank, int)
        or isinstance(display_rank, bool)
        or display_rank <= 0
    ):
        raise ValueError(
            f"display_rank must be a positive integer or None: actual={display_rank!r}"
        )
    return search_result, display_rank


def _sku_catalog_summary(product_snapshot):
    archive = product_snapshot.get("archive") or {}
    catalog = archive.get("sku_catalog") or {}
    received_dimensions = catalog.get("dimensions") or []
    dimensions = []
    total_option_count = 0
    for dimension in received_dimensions:
        if not isinstance(dimension, dict):
            continue
        label = str(dimension.get("label") or "规格").strip() or "规格"
        option_names = []
        for option in dimension.get("options") or []:
            if isinstance(option, dict):
                value = str(option.get("value") or option.get("text") or "").strip()
            else:
                value = str(option or "").strip()
            if value and value not in option_names:
                option_names.append(value)
        total_option_count += len(option_names)
        dimensions.append(
            {
                "label": label,
                "option_count": len(option_names),
                "option_names": option_names,
            }
        )
    return {
        "status": catalog.get("status") or ("captured" if dimensions else "not_exposed"),
        "dimension_count": len(dimensions),
        "total_option_count": total_option_count,
        "dimensions": dimensions,
        "note": (
            "已保存页面公开的规格维度和选项名称；不代表已遍历全部组合价格或库存。"
            if dimensions
            else "当前页面没有返回可用的规格目录。"
        ),
        "evidence_level": "program_fact" if dimensions else "missing",
        "source_fields": ["product_snapshot.archive.sku_catalog.dimensions"],
    }


def build_competitor_analysis(
    item_id,
    keyword,
    product_snapshot,
    *,
    search_result=None,
    display_rank=None,
):
    item_id = _required_analysis_text("item_id", str(item_id))
    keyword = _required_analysis_text("keyword", keyword)
    if not isinstance(product_snapshot, dict):
        raise ValueError(
            "product_snapshot must be an object: "
            f"item_id={item_id!r} actual={product_snapshot!r}"
        )
    snapshot_id = product_snapshot.get("product_snapshot_id")
    if not isinstance(snapshot_id, int) or isinstance(snapshot_id, bool):
        raise ValueError(
            "product_snapshot_id must be an integer: "
            f"item_id={item_id!r} actual={snapshot_id!r}"
        )
    search_result, display_rank = _search_context(
        item_id,
        search_result,
        display_rank,
    )

    sku = product_snapshot.get("sku")
    if sku is not None and not isinstance(sku, dict):
        raise ValueError(
            f"product_snapshot sku must be an object or None: actual={sku!r}"
        )
    sku = sku or {}
    price_status = sku.get("price_status") or "not_captured"
    captured_target_price = (
        sku.get("sku_price_text")
        if price_status == "captured" and sku.get("sku_price_text") not in (None, "")
        else None
    )
    search_display_price = (
        search_result.get("display_price") if search_result is not None else None
    )

    profile = {
        "title": _evidence_value(
            product_snapshot.get("title"),
            ("product_snapshot.title",),
            "商品详情页保存的标题。",
        ),
        "main_image_url": _evidence_value(
            product_snapshot.get("main_image_url"),
            ("product_snapshot.main_image_url",),
            "仅表示主图链接已保存，不代表已完成视觉质量判断。",
        ),
        "attributes": _evidence_value(
            product_snapshot.get("attributes_text"),
            ("product_snapshot.attributes_text",),
            "详情页当前可见的属性与卖点文本。",
        ),
        "shop_name": _evidence_value(
            product_snapshot.get("shop_name"),
            ("product_snapshot.shop_name",),
            "商品详情页保存的店铺名称。",
        ),
        "captured_at": _evidence_value(
            product_snapshot.get("captured_at"),
            ("product_snapshot.captured_at",),
            "本次详情快照的采集时间。",
        ),
        "search_rank": _evidence_value(
            display_rank,
            ("search_snapshot.display_rank",),
            "仅表示所选搜索快照中的展示顺序，不代表自然排名。",
        ),
        "visible_sales": _evidence_value(
            product_snapshot.get("sold_text"),
            ("product_snapshot.sold_text",),
            "页面可见销量口径，不推算真实成交量。",
        ),
        "repeat_buyer": _evidence_value(
            product_snapshot.get("repeat_buyer_text"),
            ("product_snapshot.repeat_buyer_text",),
            "页面可见回头客文案，不等同于真实复购率。",
        ),
        "cart": _evidence_value(
            product_snapshot.get("cart_text"),
            ("product_snapshot.cart_text",),
            "页面可见加购文案。",
        ),
        "review_count": _evidence_value(
            product_snapshot.get("review_count_text"),
            ("product_snapshot.review_count_text",),
            "页面可见评价数量文案。",
        ),
        "services": _evidence_value(
            product_snapshot.get("services") or [],
            ("product_snapshot.services",),
            "详情页已保存的服务承诺。",
        ),
        "completeness_percent": _evidence_value(
            product_snapshot.get("completeness_percent"),
            ("product_snapshot.completeness_percent",),
            "按详情采集字段计算的资料完整度。",
        ),
        "raw_source_ref": _evidence_value(
            product_snapshot.get("raw_source_ref"),
            ("product_snapshot.raw_source_ref",),
            "详情快照对应的本地原始证据引用。",
        ),
    }

    direct_competitor = {
        "classification": "single_point_learning_sample",
        "label": "单点学习样本",
        "evidence_level": "rule_judgment",
        "source_fields": [
            "project.keyword",
            "product_snapshot.title",
            "product_snapshot.attributes_text",
        ],
        "reason": (
            f"该商品可围绕项目关键词“{keyword}”作为单点学习样本；"
            "当前没有自有商品的核心需求、价格带以及人群或使用场景对照，"
            "不能据排名、销量或关键词相近自动判定为直接竞品。"
        ),
        "missing_conditions": [
            "核心需求对照",
            "价格带对照",
            "人群或使用场景对照",
        ],
    }

    transaction_chain = [
        {
            "stage": "流量入口",
            "observations": [
                profile["title"],
                profile["search_rank"],
                _evidence_value(
                    search_display_price,
                    ("search_snapshot.display_price",),
                    "搜索展示价仅用于观察入口表达，不是目标 SKU 实价。",
                    price_scope="search_display",
                ),
            ],
        },
        {
            "stage": "点击表达",
            "observations": [
                _evidence_value(
                    product_snapshot.get("main_image_url"),
                    ("product_snapshot.main_image_url",),
                    "仅确认主图链接已保存；尚未完成视觉内容识别。",
                ),
                _missing_analysis_value(
                    "视频、首屏理由、痛点、方案、证明和场景尚未采集或分析。"
                ),
            ],
        },
        {
            "stage": "信任建立",
            "observations": [
                _evidence_value(
                    product_snapshot.get("shop_positive_rate_text"),
                    ("product_snapshot.shop_positive_rate_text",),
                    "页面可见店铺好评率文案。",
                ),
                profile["review_count"],
                profile["services"],
            ],
        },
        {
            "stage": "规格决策",
            "observations": [
                _evidence_value(
                    sku.get("selected_options") or [],
                    ("sku_snapshot.selected_options",),
                    "本次采集已明确选择的目标规格。",
                ),
                _evidence_value(
                    captured_target_price,
                    ("sku_snapshot.sku_price_text", "sku_snapshot.price_status"),
                    (
                        "目标规格刷新后读取到的实价。"
                        if captured_target_price is not None
                        else "目标 SKU 实价未成功读取；不得回填详情可见价或搜索展示价。"
                    ),
                    price_scope="target_sku",
                ),
            ],
        },
    ]

    sku_price = {
        "selected_options": _evidence_value(
            sku.get("selected_options") or [],
            ("sku_snapshot.selected_options",),
            "本次价格采集所选规格。",
        ),
        "search_display_price": _evidence_value(
            search_display_price,
            ("search_snapshot.display_price",),
            "搜索列表展示价，不是目标 SKU 实价。",
            price_scope="search_display",
        ),
        "detail_visible_price": _evidence_value(
            product_snapshot.get("visible_price_text"),
            ("product_snapshot.visible_price_text",),
            "详情页可见价格文案，不是目标 SKU 实价。",
            price_scope="detail_visible",
        ),
        "sku_panel_display_price": _evidence_value(
            sku.get("display_price_text"),
            ("sku_snapshot.display_price_text",),
            "SKU 面板保存的展示价，仅作上下文，不替代刷新后的目标规格实价。",
            price_scope="sku_panel_display",
        ),
        "target_sku_price": _evidence_value(
            captured_target_price,
            ("sku_snapshot.sku_price_text", "sku_snapshot.price_status"),
            (
                "目标规格刷新后读取到的实价。"
                if captured_target_price is not None
                else "目标 SKU 实价缺失；搜索展示价、详情可见价和 SKU 面板展示价均不得回填。"
            ),
            price_scope="target_sku",
        ),
        "price_status": _evidence_value(
            price_status,
            ("sku_snapshot.price_status",),
            "SKU 价格采集状态；只有 captured 允许输出目标 SKU 实价。",
        ),
        "raw_source_ref": _evidence_value(
            sku.get("raw_source_ref"),
            ("sku_snapshot.raw_source_ref",),
            "SKU 价格证据对应的本地原始引用。",
        ),
    }
    sku_structure = _sku_catalog_summary(product_snapshot)

    archive_reviews = ((product_snapshot.get("archive") or {}).get("reviews") or {})
    review_items = [
        item
        for item in (archive_reviews.get("items") or [])
        if isinstance(item, dict) and str(item.get("content") or "").strip()
    ]
    review_tags = archive_reviews.get("tags") or []
    review_preview = _evidence_value(
        product_snapshot.get("review_preview_text"),
        ("product_snapshot.review_preview_text",),
        "页面当前可见的评价摘要或预览，不能代表全部评价。",
    )
    review_concerns = {
        "review_preview": review_preview,
        "recognized_points": _review_cluster_evidence(
            review_items, review_tags, "recognized_points"
        ),
        "concerns": _review_cluster_evidence(review_items, review_tags, "concerns"),
        "repeat_reasons": _review_cluster_evidence(
            review_items, review_tags, "repeat_reasons"
        ),
        "unmet_needs": _review_cluster_evidence(
            review_items, review_tags, "unmet_needs"
        ),
    }

    unknown_data = [
        {
            "field": field,
            "label": label,
            "evidence_level": "missing",
            "reason": reason,
        }
        for field, label, reason in (
            ("conversion_rate", "真实转化率", "公开页面与当前采集结果无法确认。"),
            ("profit", "利润", "缺少进货、履约、平台费用和投放成本。"),
            ("uv_value", "UV 价值", "缺少访客与成交金额数据。"),
            ("ppc", "真实投放与 PPC", "公开页面无法确认投放消耗和点击成本。"),
            ("repeat_purchase_rate", "真实复购率", "页面回头客文案不等于复购率。"),
            *(() if review_items else (
                ("full_review_distribution", "完整评价分布", "当前没有保存可归类的评价正文。"),
            )),
        )
    ]

    return {
        "schema_version": 2,
        "item_id": item_id,
        "keyword": keyword,
        "product_snapshot_id": snapshot_id,
        "captured_at": product_snapshot.get("captured_at"),
        "evidence_legend": [dict(level) for level in EVIDENCE_LEGEND],
        "direct_competitor": direct_competitor,
        "profile": profile,
        "transaction_chain": transaction_chain,
        "sku_price": sku_price,
        "sku_structure": sku_structure,
        "review_concerns": review_concerns,
        "unknown_data": unknown_data,
    }


COMPARISON_STATUS_LEGEND = {
    "competitor_advantage": "竞品占优",
    "own_advantage": "我方占优",
    "not_comparable": "不可比较",
    "missing": "缺失",
}


def _comparison_analysis(role, analysis):
    if not isinstance(analysis, dict):
        raise ValueError(f"{role} analysis must be an object: actual={analysis!r}")
    item_id = str(analysis.get("item_id") or "").strip()
    if not item_id:
        raise ValueError(f"{role} analysis item_id must be non-empty")
    return item_id, analysis


def _comparison_evidence(evidence, source_field):
    if not isinstance(evidence, dict):
        return {
            "value": None,
            "evidence_level": "missing",
            "source_fields": [source_field],
        }
    value = evidence.get("value")
    source_fields = evidence.get("source_fields")
    if not isinstance(source_fields, list) or not source_fields:
        source_fields = [source_field]
    return {
        "value": value,
        "evidence_level": (
            "missing" if value in (None, "", []) else "program_fact"
        ),
        "source_fields": list(source_fields),
    }


def _decimal_from_visible_text(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float, Decimal)):
        try:
            return Decimal(str(value))
        except InvalidOperation:
            return None
    if not isinstance(value, str):
        return None
    match = re.search(r"(?<!\d)(\d+(?:\.\d+)?)", value.replace(",", ""))
    if match is None:
        return None
    try:
        return Decimal(match.group(1))
    except InvalidOperation:
        return None


def _count_from_visible_text(value):
    if not isinstance(value, str):
        return None
    match = re.search(r"(\d+(?:\.\d+)?)\s*(万)?", value.replace(",", ""))
    if match is None:
        return None
    count = Decimal(match.group(1))
    if match.group(2):
        count *= 10000
    return count


def _text_point_count(value):
    if not isinstance(value, str) or not value.strip():
        return None
    points = re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fff]+", value)
    return len(points) or None


def _metric_status(competitor_metric, own_metric, *, lower_is_better):
    if competitor_metric is None or own_metric is None:
        return "not_comparable"
    if competitor_metric == own_metric:
        return "not_comparable"
    competitor_wins = (
        competitor_metric < own_metric
        if lower_is_better
        else competitor_metric > own_metric
    )
    return "competitor_advantage" if competitor_wins else "own_advantage"


def _comparison_item(
    key,
    label,
    competitor_evidence,
    own_evidence,
    status,
    rule,
):
    if (
        competitor_evidence["evidence_level"] == "missing"
        or own_evidence["evidence_level"] == "missing"
    ):
        status = "missing"
    return {
        "key": key,
        "label": label,
        "status": status,
        "status_label": COMPARISON_STATUS_LEGEND[status],
        "rule": rule,
        "competitor": competitor_evidence,
        "own": own_evidence,
    }


def build_product_comparison(competitor_analysis, own_analysis):
    competitor_item_id, competitor = _comparison_analysis(
        "competitor", competitor_analysis
    )
    own_item_id, own = _comparison_analysis("own", own_analysis)
    if competitor_item_id == own_item_id:
        raise ValueError(
            "competitor and own product must use different item_id: "
            f"actual={own_item_id!r}"
        )

    competitor_profile = competitor.get("profile") or {}
    own_profile = own.get("profile") or {}
    competitor_price = competitor.get("sku_price") or {}
    own_price = own.get("sku_price") or {}
    items = []

    competitor_title = _comparison_evidence(
        competitor_profile.get("title"), "product_snapshot.title"
    )
    own_title = _comparison_evidence(
        own_profile.get("title"), "product_snapshot.title"
    )
    items.append(
        _comparison_item(
            "title",
            "标题",
            competitor_title,
            own_title,
            "not_comparable",
            "标题文本可逐字复核，但仅凭长度或措辞不能确定谁占优。",
        )
    )

    competitor_rank = _comparison_evidence(
        competitor_profile.get("search_rank"), "search_snapshot.display_rank"
    )
    own_rank = _comparison_evidence(
        own_profile.get("search_rank"), "search_snapshot.display_rank"
    )
    rank_status = _metric_status(
        competitor_rank["value"], own_rank["value"], lower_is_better=True
    )
    items.append(
        _comparison_item(
            "search_rank",
            "搜索展示顺序",
            competitor_rank,
            own_rank,
            rank_status,
            "仅比较同口径快照中的展示顺序数字，数字更小者占优；不解释为自然排名。",
        )
    )

    for key, label, price_field in (
        ("search_display_price", "搜索展示价", "search_display_price"),
        ("target_sku_price", "目标 SKU 实价", "target_sku_price"),
    ):
        competitor_evidence = _comparison_evidence(
            competitor_price.get(price_field),
            f"{price_field}.competitor",
        )
        own_evidence = _comparison_evidence(
            own_price.get(price_field),
            f"{price_field}.own",
        )
        competitor_number = _decimal_from_visible_text(competitor_evidence["value"])
        own_number = _decimal_from_visible_text(own_evidence["value"])
        price_status = _metric_status(
            competitor_number, own_number, lower_is_better=True
        )
        rule = (
            "同一价格口径解析为数值后，较低者仅标记为价格竞争优势。"
            if competitor_number is not None and own_number is not None
            else "至少一方价格无法解析为单一数值，因此不可比较且不猜测。"
        )
        items.append(
            _comparison_item(
                key,
                label,
                competitor_evidence,
                own_evidence,
                price_status,
                rule,
            )
        )

    competitor_sku = _comparison_evidence(
        competitor_price.get("selected_options"), "sku_snapshot.selected_options"
    )
    own_sku = _comparison_evidence(
        own_price.get("selected_options"), "sku_snapshot.selected_options"
    )
    competitor_sku_count = (
        len(competitor_sku["value"])
        if isinstance(competitor_sku["value"], list)
        else None
    )
    own_sku_count = len(own_sku["value"]) if isinstance(own_sku["value"], list) else None
    items.append(
        _comparison_item(
            "sku",
            "已选 SKU 维度",
            competitor_sku,
            own_sku,
            _metric_status(
                competitor_sku_count, own_sku_count, lower_is_better=False
            ),
            "只比较本次明确选择并保存的 SKU 维度数量；数量更多仅表示规格证据更丰富。",
        )
    )

    competitor_points = _comparison_evidence(
        competitor_profile.get("attributes"), "product_snapshot.attributes_text"
    )
    own_points = _comparison_evidence(
        own_profile.get("attributes"), "product_snapshot.attributes_text"
    )
    items.append(
        _comparison_item(
            "selling_points",
            "页面可见卖点",
            competitor_points,
            own_points,
            _metric_status(
                _text_point_count(competitor_points["value"]),
                _text_point_count(own_points["value"]),
                lower_is_better=False,
            ),
            "按页面可见属性文本中的独立词组数量比较信息覆盖，不推断真实说服力。",
        )
    )

    competitor_reviews = _comparison_evidence(
        competitor_profile.get("review_count"), "product_snapshot.review_count_text"
    )
    own_reviews = _comparison_evidence(
        own_profile.get("review_count"), "product_snapshot.review_count_text"
    )
    items.append(
        _comparison_item(
            "reviews",
            "页面可见评价数",
            competitor_reviews,
            own_reviews,
            _metric_status(
                _count_from_visible_text(competitor_reviews["value"]),
                _count_from_visible_text(own_reviews["value"]),
                lower_is_better=False,
            ),
            "只比较页面文案中可解析的评价数量，数量更高者占优；不代表评价质量。",
        )
    )

    competitor_services = _comparison_evidence(
        competitor_profile.get("services"), "product_snapshot.services"
    )
    own_services = _comparison_evidence(
        own_profile.get("services"), "product_snapshot.services"
    )
    competitor_service_count = (
        len(competitor_services["value"])
        if isinstance(competitor_services["value"], list)
        else None
    )
    own_service_count = (
        len(own_services["value"])
        if isinstance(own_services["value"], list)
        else None
    )
    items.append(
        _comparison_item(
            "services",
            "服务承诺",
            competitor_services,
            own_services,
            _metric_status(
                competitor_service_count,
                own_service_count,
                lower_is_better=False,
            ),
            "按已保存的不同服务承诺数量比较覆盖度，不判断履约质量。",
        )
    )

    competitor_visual = _comparison_evidence(
        competitor_profile.get("main_image_url"), "product_snapshot.main_image_url"
    )
    own_visual = _comparison_evidence(
        own_profile.get("main_image_url"), "product_snapshot.main_image_url"
    )
    items.append(
        _comparison_item(
            "visual",
            "视觉素材",
            competitor_visual,
            own_visual,
            "not_comparable",
            "当前只核对主图链接是否存在；未启用视觉内容分析时不判断画面优劣。",
        )
    )

    summary = {status: 0 for status in COMPARISON_STATUS_LEGEND}
    for item in items:
        summary[item["status"]] += 1
    return {
        "schema_version": 1,
        "competitor_item_id": competitor_item_id,
        "own_item_id": own_item_id,
        "status_legend": dict(COMPARISON_STATUS_LEGEND),
        "items": items,
        "summary": summary,
    }


def _scan_result(response, source_path):
    if not isinstance(response, dict):
        raise ValueError(
            f"SKU element response must be an object: "
            f"path={source_path} actual={response!r}"
        )
    result = response.get("result")
    if not isinstance(result, dict):
        raise ValueError(
            f"SKU element response result must be an object: "
            f"path={source_path} actual={result!r}"
        )
    dom = result.get("dom")
    if not isinstance(dom, str):
        raise ValueError(
            f"SKU element dom must be text: path={source_path} actual={dom!r}"
        )
    total_elements = result.get("totalElements")
    if (
        not isinstance(total_elements, int)
        or isinstance(total_elements, bool)
        or total_elements < 0
    ):
        raise ValueError(
            f"SKU element totalElements must be a non-negative integer: "
            f"path={source_path} actual={total_elements!r}"
        )
    return dom, total_elements


def _normalized_option_text(raw_text):
    normalized_text = " ".join(unescape(raw_text).split())
    if not normalized_text:
        return None
    if normalized_text in PROMOTIONAL_TEXTS:
        return None
    previous_text = None
    while normalized_text and normalized_text != previous_text:
        previous_text = normalized_text
        for suffix in PROMOTIONAL_SUFFIXES:
            if normalized_text.endswith(suffix):
                normalized_text = normalized_text[: -len(suffix)].rstrip()
                break
    return normalized_text or None


def _dimension_labels(dom):
    labels = []
    for match in PLAIN_LINE_PATTERN.finditer(dom):
        label = " ".join(match.group("label").split())
        if not label or not any(keyword in label for keyword in SKU_DIMENSION_KEYWORDS):
            continue
        labels.append((label, match.start(), match.end()))
    return labels


def _validate_span_indices(span_matches, total_elements, source_path):
    text_by_index = {}
    for span_match in span_matches:
        element_index = int(span_match.group("index"))
        if element_index >= total_elements:
            raise ValueError(
                f"SKU element index is outside totalElements: "
                f"path={source_path} index={element_index} "
                f"totalElements={total_elements}"
            )
        raw_text = " ".join(unescape(span_match.group("text")).split())
        previous_text = text_by_index.get(element_index)
        if previous_text is not None and previous_text != raw_text:
            raise ValueError(
                f"SKU scan contains duplicate element index with conflicting text: "
                f"path={source_path} index={element_index} "
                f"first={previous_text!r} actual={raw_text!r}"
            )
        text_by_index[element_index] = raw_text


def parse_sku_dimensions(response, source_path):
    dom, total_elements = _scan_result(response, source_path)
    span_matches = list(INDEXED_SPAN_PATTERN.finditer(dom))
    _validate_span_indices(span_matches, total_elements, source_path)
    label_matches = _dimension_labels(dom)
    dimensions = []

    for label_index, (label, _, label_end) in enumerate(label_matches):
        section_end = (
            label_matches[label_index + 1][1]
            if label_index + 1 < len(label_matches)
            else len(dom)
        )
        button_match = BUTTON_PATTERN.search(dom, label_end, section_end)
        if button_match is not None:
            section_end = button_match.start()

        options = []
        seen_values = set()
        for span_match in span_matches:
            if not label_end <= span_match.start() < section_end:
                continue
            raw_text = " ".join(unescape(span_match.group("text")).split())
            value = _normalized_option_text(raw_text)
            if value is None:
                continue
            normalized_value = value.casefold()
            if normalized_value in seen_values:
                continue
            seen_values.add(normalized_value)
            options.append(
                {
                    "value": value,
                    "index": int(span_match.group("index")),
                    "raw_text": raw_text,
                }
            )
        if options:
            dimensions.append({"label": label, "options": options})

    return {
        "total_elements": total_elements,
        "dimensions": dimensions,
        "raw_source_ref": str(source_path),
    }


def _normalized_price_text(price_text):
    try:
        price = Decimal(price_text)
    except InvalidOperation:
        return None
    if not price.is_finite() or price <= 0:
        return None
    normalized = format(price, "f").rstrip("0").rstrip(".")
    return normalized or "0"


def parse_sku_price_scan(response, source_path):
    dom, _ = _scan_result(response, source_path)
    distinct_prices = []
    for price_match in re.finditer(r"￥\s*(\d+(?:\.\d+)?)", dom):
        normalized_price = _normalized_price_text(price_match.group(1))
        if normalized_price and normalized_price not in distinct_prices:
            distinct_prices.append(normalized_price)

    if not distinct_prices:
        return {
            "sku_price_text": None,
            "price_status": "missing_after_refresh",
            "raw_price_evidence": dom,
        }
    if len(distinct_prices) > 1:
        return {
            "sku_price_text": None,
            "price_status": "ambiguous_after_refresh",
            "raw_price_evidence": dom,
        }
    return {
        "sku_price_text": distinct_prices[0],
        "price_status": "captured",
        "raw_price_evidence": dom,
    }
