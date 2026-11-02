from collections import Counter
from decimal import Decimal, InvalidOperation
import json
import re
from statistics import median

from src.competitor_analysis import build_competitor_analysis


PLATFORM_TYPES = ("taobao", "tmall", "unknown")
TITLE_TERM_ALIASES = {
    "product": (
        ("手机保护套", ("手机保护套",)),
        ("手机壳", ("手机壳",)),
        ("保护套", ("保护套",)),
        ("外壳", ("外壳",)),
        ("手机套", ("手机套",)),
    ),
    "function": (
        ("无线充电", ("无线充电",)),
        ("镜头膜", ("镜头膜",)),
        ("防摔", ("防摔", "抗摔")),
        ("散热", ("散热",)),
        ("磁吸", ("磁吸",)),
        ("全包", ("全包",)),
        ("防水", ("防水",)),
        ("防刮", ("防刮",)),
    ),
    "material": (
        ("液态硅胶", ("液态硅胶",)),
        ("亚克力", ("亚克力",)),
        ("硅胶", ("硅胶",)),
        ("磨砂", ("磨砂",)),
        ("真皮", ("真皮",)),
        ("皮革", ("皮革",)),
        ("玻璃", ("玻璃",)),
        ("金属", ("金属",)),
        ("TPU", ("tpu",)),
        ("PC", ("pc",)),
    ),
    "specification": (
        ("超薄", ("超薄",)),
        ("加厚", ("加厚",)),
    ),
    "audience": (
        ("女士", ("女士",)),
        ("男士", ("男士",)),
        ("女生", ("女生",)),
        ("男生", ("男生",)),
        ("情侣", ("情侣",)),
        ("学生", ("学生",)),
        ("儿童", ("儿童",)),
        ("女", ("女",)),
        ("男", ("男",)),
    ),
    "scenario": (
        ("夏季", ("夏季", "夏天")),
        ("商务", ("商务",)),
        ("游戏", ("游戏",)),
        ("户外", ("户外",)),
        ("运动", ("运动",)),
        ("车载", ("车载",)),
    ),
    "style": (
        ("高级感", ("高级感",)),
        ("简约", ("简约",)),
        ("透明", ("透明",)),
        ("可爱", ("可爱",)),
        ("复古", ("复古",)),
        ("个性", ("个性",)),
        ("潮流", ("潮流",)),
        ("INS", ("ins",)),
    ),
    "brand": (
        ("苹果", ("苹果", "iphone")),
        ("华为", ("华为",)),
        ("小米", ("小米",)),
        ("荣耀", ("荣耀",)),
        ("三星", ("三星",)),
        ("OPPO", ("oppo",)),
        ("vivo", ("vivo",)),
    ),
}
IPHONE_MODEL_PATTERN = re.compile(
    r"(?:iphone|苹果)\s*(1[1-7])\s*(pro\s*max|promax|pro|plus|mini|air)?",
    re.IGNORECASE,
)
MARKET_RECOMMENDATION_EVIDENCE_FIELDS = (
    "display_rank",
    "title",
    "shop_name",
    "display_price",
    "platform_type",
    "suspected_ad",
    "completeness_percent",
)
MARKET_RECOMMENDATION_REQUIRED_TEXT_FIELDS = (
    "recommendation_type",
    "learning_point",
    "risk",
    "deep_dive_advice",
)
PAYMENT_HEAT_PATTERN = re.compile(
    r"(?P<number>\d+(?:\.\d+)?)\s*(?P<unit>万|千)?\+?\s*人(?:付款|收货)",
    re.IGNORECASE,
)


def parse_payment_heat(payment_text):
    """Return a page-displayed demand lower bound, never an exact sales value."""
    if not isinstance(payment_text, str) or not payment_text.strip():
        return None
    match = PAYMENT_HEAT_PATTERN.search(payment_text)
    if match is None:
        return None
    multiplier = {"万": Decimal("10000"), "千": Decimal("1000")}.get(
        match.group("unit"),
        Decimal("1"),
    )
    try:
        lower_bound = int(Decimal(match.group("number")) * multiplier)
    except (InvalidOperation, ValueError):
        return None
    return {
        "metric": "page_display_heat",
        "lower_bound": lower_bound,
        "raw_text": payment_text.strip(),
        "is_exact_sales": False,
    }


def build_complete_market_evidence_pack(keyword, search_snapshot):
    if not isinstance(keyword, str) or not keyword.strip():
        raise ValueError(f"keyword must be non-empty text: actual={keyword!r}")
    if not isinstance(search_snapshot, dict):
        raise ValueError(
            f"search_snapshot must be an object: actual={search_snapshot!r}"
        )
    search_results = search_snapshot.get("results")
    if not isinstance(search_results, list) or not search_results:
        raise ValueError(
            f"complete market analysis requires saved products: actual={search_results!r}"
        )
    products = []
    seen_item_ids = set()
    for result_index, search_result in enumerate(search_results):
        if not isinstance(search_result, dict):
            raise ValueError(
                f"search_result must be an object: index={result_index} "
                f"actual={search_result!r}"
            )
        item_id = str(search_result.get("item_id") or "").strip()
        if not item_id:
            raise ValueError(
                f"item_id must be non-empty text: index={result_index}"
            )
        if item_id in seen_item_ids:
            continue
        seen_item_ids.add(item_id)
        payment_heat = parse_payment_heat(search_result.get("payment_text"))
        products.append(
            {
                "item_id": item_id,
                "display_rank": search_result.get("display_rank") or result_index + 1,
                "title": search_result.get("title"),
                "shop_name": search_result.get("shop_name"),
                "display_price": search_result.get("display_price"),
                "payment_text": search_result.get("payment_text"),
                "payment_heat_lower_bound": (
                    payment_heat["lower_bound"] if payment_heat else None
                ),
                "origin_text": search_result.get("origin_text"),
                "promotion_text": search_result.get("promotion_text"),
                "logistics_text": search_result.get("logistics_text"),
                "platform_type": search_result.get("platform_type"),
                "image_url": search_result.get("image_url"),
                "product_url": search_result.get("product_url"),
                "card_text": search_result.get("card_text"),
            }
        )
    return {
        "schema_version": 1,
        "keyword": keyword.strip(),
        "snapshot_id": search_snapshot.get("snapshot_id"),
        "captured_at": search_snapshot.get("captured_at"),
        "product_count": len(products),
        "payment_metric_note": {
            "metric": "page_display_heat",
            "meaning": "搜索页展示的付款/收货热度下限，不是精确销量。",
        },
        "products": products,
    }


def select_representative_visual_samples(products, limit=24):
    if not isinstance(products, list):
        raise ValueError(f"products must be a list: actual={products!r}")
    if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
        raise ValueError(f"limit must be a positive integer: actual={limit!r}")
    eligible = []
    seen_item_ids = set()
    for product_index, product in enumerate(products):
        if not isinstance(product, dict):
            raise ValueError(
                f"product must be an object: index={product_index} actual={product!r}"
            )
        item_id = str(product.get("item_id") or "").strip()
        image_url = str(product.get("image_url") or "").strip()
        if not item_id or not image_url or item_id in seen_item_ids:
            continue
        seen_item_ids.add(item_id)
        normalized = dict(product)
        normalized["item_id"] = item_id
        normalized["image_url"] = image_url
        normalized["_price"] = _positive_display_price(product.get("display_price"))
        payment_heat = parse_payment_heat(product.get("payment_text"))
        normalized["_payment"] = payment_heat["lower_bound"] if payment_heat else None
        eligible.append(normalized)
    if len(eligible) <= limit:
        return [
            {key: value for key, value in product.items() if not key.startswith("_")}
            for product in eligible
        ]

    ranked = sorted(
        eligible,
        key=lambda product: (
            product.get("display_rank")
            if isinstance(product.get("display_rank"), int)
            else 10**9
        ),
    )
    selected = {}

    def add(product, reason):
        if product is None or len(selected) >= limit:
            return
        item_id = product["item_id"]
        if item_id not in selected:
            selected[item_id] = {
                key: value for key, value in product.items() if not key.startswith("_")
            }
            selected[item_id]["selection_reasons"] = []
        reasons = selected[item_id]["selection_reasons"]
        if reason not in reasons:
            reasons.append(reason)

    add(ranked[0], "rank_top")
    add(ranked[-1], "rank_tail")
    for position in (0.25, 0.5, 0.75):
        add(ranked[round((len(ranked) - 1) * position)], "rank_stratum")

    priced = sorted(
        (product for product in eligible if product["_price"] is not None),
        key=lambda product: product["_price"],
    )
    if priced:
        add(priced[0], "price_low")
        add(priced[len(priced) // 2], "price_middle")
        add(priced[-1], "price_high")

    heated = sorted(
        (product for product in eligible if product["_payment"] is not None),
        key=lambda product: product["_payment"],
        reverse=True,
    )
    if heated:
        add(heated[0], "payment_heat_high")
        add(heated[len(heated) // 2], "payment_heat_middle")

    for platform_type in ("tmall", "taobao", "unknown"):
        add(
            next(
                (
                    product
                    for product in ranked
                    if product.get("platform_type") == platform_type
                ),
                None,
            ),
            f"platform_{platform_type}",
        )

    seen_shops = set()
    for product in ranked:
        shop_name = str(product.get("shop_name") or "").strip()
        if not shop_name or shop_name in seen_shops:
            continue
        seen_shops.add(shop_name)
        add(product, "store_coverage")
        if len(selected) >= limit:
            break

    for sample_index in range(limit):
        add(
            ranked[round((len(ranked) - 1) * sample_index / max(limit - 1, 1))],
            "rank_even_spacing",
        )
    for product in ranked:
        add(product, "rank_fill")
        if len(selected) >= limit:
            break
    return list(selected.values())


COMPLETE_REPORT_SECTIONS = (
    "executive_summary",
    "market_structure",
    "title_and_demand",
    "price_and_competition",
    "visual_analysis",
    "opportunities_and_risks",
    "action_plan",
)
SEMANTIC_LIST_FIELDS = (
    "title_terms",
    "needs",
    "selling_points",
    "audiences",
    "scenarios",
    "competition_signals",
    "risks",
)


def _model_json_object(model_content, operation_name):
    if not isinstance(model_content, str) or not model_content.strip():
        raise ValueError(f"{operation_name} returned empty content")
    normalized = model_content.strip()
    if normalized.startswith("```"):
        normalized = re.sub(r"^```(?:json)?\s*", "", normalized, flags=re.I)
        normalized = re.sub(r"\s*```$", "", normalized)
    try:
        payload = json.loads(normalized)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{operation_name} must return valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{operation_name} must return a JSON object")
    return payload


def _semantic_messages(keyword, products):
    return [
        {
            "role": "system",
            "content": (
                "你是电商市场语义标注器。只能根据给定商品证据标注标题词、需求、卖点、"
                "人群、场景、竞争信号和风险。不得生成统计数值，不得引用不存在的商品。"
                "只返回 JSON 对象，格式为 {\"products\":[...] }。"
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "stage": "semantic_tags",
                    "keyword": keyword,
                    "products": products,
                    "required_fields": list(SEMANTIC_LIST_FIELDS),
                },
                ensure_ascii=False,
            ),
        },
    ]


def _validate_semantic_batch(model_content, allowed_item_ids):
    payload = _model_json_object(model_content, "semantic analysis")
    products = payload.get("products")
    if not isinstance(products, list):
        raise ValueError("semantic analysis products must be a list")
    validated = []
    seen = set()
    for product_index, product in enumerate(products):
        if not isinstance(product, dict):
            raise ValueError(
                f"semantic product must be an object: index={product_index}"
            )
        item_id = str(product.get("item_id") or "").strip()
        if item_id not in allowed_item_ids:
            raise ValueError(
                f"semantic analysis references unknown item_id: actual={item_id!r}"
            )
        if item_id in seen:
            raise ValueError(
                f"semantic analysis contains duplicate item_id: actual={item_id!r}"
            )
        seen.add(item_id)
        normalized = {"item_id": item_id}
        for field_name in SEMANTIC_LIST_FIELDS:
            values = product.get(field_name)
            if not isinstance(values, list) or any(
                not isinstance(value, str) or not value.strip() for value in values
            ):
                raise ValueError(
                    f"semantic field must be a text list: item_id={item_id!r} "
                    f"field={field_name!r} actual={values!r}"
                )
            normalized[field_name] = list(
                dict.fromkeys(value.strip() for value in values)
            )[:12]
        validated.append(normalized)
    return validated


def _aggregate_semantic_products(products):
    aggregated = {}
    for field_name in SEMANTIC_LIST_FIELDS:
        label_sources = {}
        for product in products:
            for label in product[field_name]:
                label_sources.setdefault(label, []).append(product["item_id"])
        aggregated[field_name] = [
            {
                "label": label,
                "product_count": len(item_ids),
                "evidence_item_ids": item_ids[:5],
            }
            for label, item_ids in sorted(
                label_sources.items(),
                key=lambda item: (-len(item[1]), item[0]),
            )[:20]
        ]
    return aggregated


def _vision_prompt(keyword, image_items):
    return json.dumps(
        {
            "stage": "visual_tags",
            "keyword": keyword,
            "instruction": (
                "逐个分析主图的构图、配色、文案、场景、模特、信任表达、信息密度、"
                "可借鉴点和同质化风险。只能引用输入 item_id，只返回 JSON。"
            ),
            "products": [
                {
                    "item_id": item["item_id"],
                    "title": item.get("title"),
                    "image_url": item["image_url"],
                }
                for item in image_items
            ],
            "output": {
                "products": [
                    {
                        "item_id": "输入 item_id",
                        "composition": "构图",
                        "color": "配色",
                        "copy": "文案",
                        "scene": "场景",
                        "model": "模特或无人像",
                        "trust": "信任表达",
                        "information_density": "信息密度",
                        "learning_point": "可借鉴点",
                        "risk": "同质化或表达风险",
                    }
                ]
            },
        },
        ensure_ascii=False,
    )


def _validate_vision_batch(model_content, allowed_item_ids):
    payload = _model_json_object(model_content, "visual analysis")
    products = payload.get("products")
    if not isinstance(products, list):
        raise ValueError("visual analysis products must be a list")
    text_fields = (
        "composition",
        "color",
        "copy",
        "scene",
        "model",
        "trust",
        "information_density",
        "learning_point",
        "risk",
    )
    validated = []
    for product_index, product in enumerate(products):
        if not isinstance(product, dict):
            raise ValueError(f"visual product must be an object: index={product_index}")
        item_id = str(product.get("item_id") or "").strip()
        if item_id not in allowed_item_ids:
            raise ValueError(
                f"visual analysis references unknown item_id: actual={item_id!r}"
            )
        normalized = {"item_id": item_id}
        for field_name in text_fields:
            value = product.get(field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"visual field must be non-empty text: item_id={item_id!r} "
                    f"field={field_name!r} actual={value!r}"
                )
            normalized[field_name] = value.strip()
        validated.append(normalized)
    return validated


def _final_report_messages(keyword, evidence, statistics, semantic_summary, vision):
    return [
        {
            "role": "system",
            "content": (
                "你是电商市场分析顾问。程序统计是不可修改的事实；语义与视觉标签是 AI 推测。"
                "不得补造销量、利润、转化率、PPC 或因果。每条结论必须给出依据、适用范围、"
                "下一步动作和真实 evidence_item_ids。只返回契约 JSON。"
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "stage": "final_report",
                    "keyword": keyword,
                    "snapshot": {
                        "snapshot_id": evidence["snapshot_id"],
                        "captured_at": evidence["captured_at"],
                        "product_count": evidence["product_count"],
                    },
                    "program_statistics": statistics,
                    "semantic_summary": semantic_summary,
                    "vision": vision,
                    "allowed_item_ids": [
                        product["item_id"] for product in evidence["products"]
                    ],
                    "required_sections": list(COMPLETE_REPORT_SECTIONS),
                    "item_contract": {
                        "conclusion": "明确结论",
                        "evidence": "不新增统计值的依据说明",
                        "evidence_item_ids": ["真实商品 ID，可为空"],
                        "scope": "适用范围",
                        "next_action": "可执行动作",
                    },
                },
                ensure_ascii=False,
            ),
        },
    ]


def _validate_complete_report(model_content, allowed_item_ids):
    payload = _model_json_object(model_content, "complete market report")
    report = {}
    for section in COMPLETE_REPORT_SECTIONS:
        items = payload.get(section)
        if not isinstance(items, list) or not items:
            raise ValueError(f"complete market report section is empty: {section}")
        validated_items = []
        for item_index, item in enumerate(items):
            if not isinstance(item, dict):
                raise ValueError(
                    f"report item must be an object: section={section} index={item_index}"
                )
            normalized = {}
            for field_name in ("conclusion", "evidence", "scope", "next_action"):
                value = item.get(field_name)
                if not isinstance(value, str) or not value.strip():
                    raise ValueError(
                        f"report field must be non-empty text: section={section} "
                        f"index={item_index} field={field_name}"
                    )
                normalized[field_name] = value.strip()
            evidence_ids = item.get("evidence_item_ids")
            if not isinstance(evidence_ids, list):
                raise ValueError(
                    f"evidence_item_ids must be a list: section={section} index={item_index}"
                )
            normalized_ids = []
            for item_id in evidence_ids:
                item_id = str(item_id or "").strip()
                if item_id not in allowed_item_ids:
                    raise ValueError(
                        f"report references unknown item_id: actual={item_id!r}"
                    )
                if item_id not in normalized_ids:
                    normalized_ids.append(item_id)
            normalized["evidence_item_ids"] = normalized_ids
            validated_items.append(normalized)
        report[section] = validated_items
    return report


def generate_complete_market_analysis(
    keyword,
    search_snapshot,
    *,
    text_request,
    vision_request,
    capabilities,
    text_batch_size=30,
    vision_batch_size=6,
):
    if not callable(text_request) or not callable(vision_request):
        raise ValueError("text_request and vision_request must be callable")
    if not isinstance(capabilities, dict) or not (
        capabilities.get("text") or {}
    ).get("supported"):
        raise ValueError("configured model does not have verified text capability")
    evidence = build_complete_market_evidence_pack(keyword, search_snapshot)
    statistics = calculate_market_statistics(search_snapshot["results"])
    semantic_products = []
    semantic_failures = []
    for start in range(0, len(evidence["products"]), text_batch_size):
        batch = evidence["products"][start : start + text_batch_size]
        allowed_ids = {product["item_id"] for product in batch}
        try:
            semantic_products.extend(
                _validate_semantic_batch(
                    text_request(_semantic_messages(keyword, batch)),
                    allowed_ids,
                )
            )
        except (RuntimeError, ValueError) as exc:
            semantic_failures.append(
                {"start": start, "count": len(batch), "reason": str(exc)}
            )
    semantic_summary = _aggregate_semantic_products(semantic_products)

    vision_samples = select_representative_visual_samples(evidence["products"])
    vision_results = []
    vision_failures = []
    vision_supported = bool((capabilities.get("vision") or {}).get("supported"))
    if vision_supported:
        for start in range(0, len(vision_samples), vision_batch_size):
            batch = vision_samples[start : start + vision_batch_size]
            try:
                vision_results.extend(
                    _validate_vision_batch(
                        vision_request(_vision_prompt(keyword, batch), batch),
                        {product["item_id"] for product in batch},
                    )
                )
            except (RuntimeError, ValueError) as exc:
                vision_failures.append(
                    {"start": start, "count": len(batch), "reason": str(exc)}
                )
    vision = {
        "status": (
            "skipped"
            if not vision_supported
            else "partial_failed"
            if vision_failures
            else "captured"
        ),
        "notice": (
            "视觉分析未执行"
            if not vision_supported
            else "部分图片分析失败，已保留成功结果"
            if vision_failures
            else None
        ),
        "sample_count": len(vision_samples),
        "successful_count": len(vision_results),
        "failed_batch_count": len(vision_failures),
        "products": vision_results,
        "failures": vision_failures,
    }
    allowed_item_ids = {product["item_id"] for product in evidence["products"]}
    report = _validate_complete_report(
        text_request(
            _final_report_messages(
                keyword,
                evidence,
                statistics,
                semantic_summary,
                vision,
            )
        ),
        allowed_item_ids,
    )
    if not vision_results:
        report["visual_analysis"] = [
            {
                "conclusion": "视觉分析未执行",
                "evidence": (
                    "当前模型未通过图片能力检测。"
                    if not vision_supported
                    else "本次代表主图批次均未成功返回可验证结果。"
                ),
                "scope": "当前快照的主图视觉模块",
                "next_action": "切换支持图片输入的模型后，明确点击重新生成。",
                "evidence_item_ids": [],
            }
        ]
    return {
        "schema_version": 1,
        "method_version": "market-7-step-multimodal-v1",
        "evidence": evidence,
        "statistics": statistics,
        "semantic_analysis": {
            "products": semantic_products,
            "summary": semantic_summary,
            "failed_batches": semantic_failures,
        },
        "vision": vision,
        "report": report,
    }


def _unique_enhanced_candidates(search_results):
    if not isinstance(search_results, list) or not search_results:
        raise ValueError(
            f"enhanced market report requires non-empty search results: actual={search_results!r}"
        )
    candidates = []
    seen_item_ids = set()
    for result_index, result in enumerate(search_results):
        if not isinstance(result, dict):
            raise ValueError(
                f"search_result must be an object: index={result_index} actual={result!r}"
            )
        item_id = result.get("item_id")
        if not isinstance(item_id, str) or not item_id.strip():
            raise ValueError(
                f"item_id must be non-empty text: index={result_index} actual={item_id!r}"
            )
        item_id = item_id.strip()
        if item_id in seen_item_ids:
            continue
        seen_item_ids.add(item_id)
        candidates.append({"item_id": item_id, "result": result, "display_rank": result_index + 1})
    return candidates


def default_enhanced_sample_ids(search_results):
    candidates = _unique_enhanced_candidates(search_results)
    if len(candidates) <= 9:
        return [candidate["item_id"] for candidate in candidates]

    middle_start = (len(candidates) - 3) // 2
    groups = (
        candidates[:3],
        candidates[middle_start:middle_start + 3],
        candidates[-3:],
    )
    selected = []
    for group in groups:
        for candidate in group:
            if candidate["item_id"] not in selected:
                selected.append(candidate["item_id"])
    return selected[:9]


def _validated_confirmed_item_ids(confirmed_item_ids, candidate_by_item_id):
    if not isinstance(confirmed_item_ids, list) or not confirmed_item_ids:
        raise ValueError(
            f"confirmed_item_ids must be a non-empty list: actual={confirmed_item_ids!r}"
        )
    if len(confirmed_item_ids) > 9:
        raise ValueError(
            f"confirmed_item_ids may contain at most 9 items: actual={len(confirmed_item_ids)}"
        )
    validated = []
    seen = set()
    for item_index, item_id in enumerate(confirmed_item_ids):
        if not isinstance(item_id, str) or not item_id.strip():
            raise ValueError(
                f"confirmed item_id must be non-empty text: index={item_index} actual={item_id!r}"
            )
        item_id = item_id.strip()
        if item_id in seen:
            raise ValueError(f"confirmed_item_ids contain duplicate item_id: actual={item_id!r}")
        if item_id not in candidate_by_item_id:
            raise ValueError(f"confirmed_item_ids contain unknown item_id: actual={item_id!r}")
        seen.add(item_id)
        validated.append(item_id)
    return validated


def build_enhanced_market_analysis(
    keyword,
    search_snapshot,
    confirmed_item_ids,
    product_snapshots_by_item_id,
):
    if not isinstance(keyword, str) or not keyword.strip():
        raise ValueError(f"keyword must be non-empty text: actual={keyword!r}")
    if not isinstance(search_snapshot, dict):
        raise ValueError(f"search_snapshot must be an object: actual={search_snapshot!r}")
    if not isinstance(product_snapshots_by_item_id, dict):
        raise ValueError(
            "product_snapshots_by_item_id must be an object: "
            f"actual={product_snapshots_by_item_id!r}"
        )
    candidates = _unique_enhanced_candidates(search_snapshot.get("results"))
    candidate_by_item_id = {candidate["item_id"]: candidate for candidate in candidates}
    confirmed = _validated_confirmed_item_ids(
        confirmed_item_ids,
        candidate_by_item_id,
    )

    successful_samples = []
    failed_samples = []
    for item_id in confirmed:
        candidate = candidate_by_item_id[item_id]
        product_snapshot = product_snapshots_by_item_id.get(item_id)
        if product_snapshot is None:
            failed_samples.append(
                {
                    "item_id": item_id,
                    "display_rank": candidate["display_rank"],
                    "title": candidate["result"].get("title"),
                    "reason": "尚未完成该商品的详情采集，未进入增强结论。",
                }
            )
            continue
        try:
            competitor = build_competitor_analysis(
                item_id,
                keyword,
                product_snapshot,
                search_result=candidate["result"],
                display_rank=candidate["display_rank"],
            )
        except ValueError as exc:
            failed_samples.append(
                {
                    "item_id": item_id,
                    "display_rank": candidate["display_rank"],
                    "title": candidate["result"].get("title"),
                    "reason": f"已保存详情快照无法形成分析：{exc}",
                }
            )
            continue
        successful_samples.append(
            {
                "item_id": item_id,
                "display_rank": candidate["display_rank"],
                "title": candidate["result"].get("title"),
                "analysis": competitor,
            }
        )

    target_sku_prices = []
    classifications = Counter()
    for sample in successful_samples:
        competitor = sample["analysis"]
        target_price = competitor["sku_price"]["target_sku_price"]["value"]
        if target_price is not None:
            target_sku_prices.append(target_price)
        classifications[competitor["direct_competitor"]["classification"]] += 1

    return {
        "schema_version": 1,
        "keyword": keyword.strip(),
        "search_snapshot_id": search_snapshot.get("snapshot_id"),
        "confirmed_item_ids": confirmed,
        "successful_samples": successful_samples,
        "failed_samples": failed_samples,
        "conclusions": {
            "successful_sample_count": len(successful_samples),
            "failed_sample_count": len(failed_samples),
            "source_item_ids": [sample["item_id"] for sample in successful_samples],
            "captured_target_sku_prices": target_sku_prices,
            "direct_competitor_classifications": dict(classifications),
            "scope_note": (
                f"增强结论仅使用 {len(successful_samples)} 个成功样本；"
                f"{len(failed_samples)} 个失败样本未参与任何汇总。"
            ),
        },
    }


def _percentage(numerator, denominator):
    if denominator == 0:
        return 0.0
    return round(numerator * 100 / denominator, 2)


def _positive_display_price(display_price):
    if display_price in (None, "") or isinstance(display_price, bool):
        return None
    try:
        price = Decimal(str(display_price).strip())
    except (InvalidOperation, ValueError):
        return None
    if not price.is_finite() or price <= 0:
        return None
    return price


def _required_recommendation_text(field_name, received_value, recommendation_index):
    if not isinstance(received_value, str) or not received_value.strip():
        raise ValueError(
            f"recommendation field must be non-empty text: "
            f"index={recommendation_index} field={field_name!r} "
            f"actual={received_value!r}"
        )
    return received_value.strip()


def _recommendation_candidates(search_results):
    if not isinstance(search_results, list):
        raise ValueError(f"search_results must be a list: actual={search_results!r}")

    candidates = []
    seen_item_ids = set()
    for result_index, search_result in enumerate(search_results):
        if not isinstance(search_result, dict):
            raise ValueError(
                f"search_result must be an object: index={result_index} "
                f"actual={search_result!r}"
            )
        item_id = search_result.get("item_id")
        if not isinstance(item_id, str) or not item_id.strip():
            raise ValueError(
                f"item_id must be non-empty text: "
                f"index={result_index} actual={item_id!r}"
            )
        normalized_item_id = item_id.strip()
        if normalized_item_id in seen_item_ids:
            raise ValueError(
                f"search_results contain duplicate item_id: actual={normalized_item_id!r}"
            )
        seen_item_ids.add(normalized_item_id)
        candidate = {"item_id": normalized_item_id}
        for field_name in MARKET_RECOMMENDATION_EVIDENCE_FIELDS:
            candidate[field_name] = search_result.get(field_name)
        candidates.append(candidate)
    if len(candidates) < 3:
        raise ValueError(
            f"market recommendations require at least 3 saved products: "
            f"actual={len(candidates)}"
        )
    return candidates


def build_market_recommendation_messages(keyword, search_results):
    if not isinstance(keyword, str) or not keyword.strip():
        raise ValueError(f"keyword must be non-empty text: actual={keyword!r}")
    candidates = _recommendation_candidates(search_results)
    request_payload = {
        "keyword": keyword.strip(),
        "allowed_evidence_fields": list(MARKET_RECOMMENDATION_EVIDENCE_FIELDS),
        "products": candidates,
        "output_contract": {
            "decision_summary": "当前快照的一句话选品判断",
            "recommendations": [
                {
                    "item_id": "必须来自 products",
                    "recommendation_type": "如排名样本、价格标杆、差异化样本",
                    "entry_decision": "推荐进入、谨慎测试或暂不进入",
                    "evidence": [
                        {
                            "field": "必须来自 allowed_evidence_fields",
                            "value": "必须与对应商品字段值完全一致",
                        }
                    ],
                    "learning_point": "适合学习的可见表达",
                    "counter_strategy": "可反打的差异化方向",
                    "avoid_point": "应避开的同质化或风险",
                    "test_hypothesis": "最低成本验证的单一假设",
                    "risk": "数据边界或风险",
                    "deep_dive_advice": "是否值得用户确认后深挖"
                }
            ],
            "keyword_opportunities": [
                {
                    "keyword": "候选机会词，不得自动搜索",
                    "source": "title、shop、scenario 或 review",
                    "reason": "为什么值得人工确认",
                    "confidence": "高、中或待验证"
                }
            ],
            "test_plan": {
                "first_batch": "首批低成本样本数量或方式",
                "visual_test": "只改一个变量的主图测试",
                "duration": "建议观察周期",
                "continue_rule": "继续投入条件",
                "stop_rule": "停止条件"
            }
        },
    }
    return [
        {
            "role": "system",
            "content": (
                "你是淘宝市场样本分析助手。只能使用用户提供的已保存快照，"
                "默认推荐 3 个不同商品，最多 9 个。除证据字段外，策略文字必须标明为建议。"
                "机会词只作为待确认方向，不得声称已搜索或已有市场数据。不得虚构商品、字段或字段值。"
                "只返回一个符合契约的 JSON 对象，不要 Markdown。"
            ),
        },
        {
            "role": "user",
            "content": json.dumps(request_payload, ensure_ascii=False),
        },
    ]


def validate_market_recommendations(model_content, search_results):
    if not isinstance(model_content, str) or not model_content.strip():
        raise ValueError(
            f"AI recommendation content must be non-empty text: actual={model_content!r}"
        )
    try:
        response_payload = json.loads(model_content)
    except json.JSONDecodeError as exc:
        raise ValueError("AI recommendation content must be valid JSON") from exc
    if not isinstance(response_payload, dict):
        raise ValueError(
            f"AI recommendation payload must be an object: actual={response_payload!r}"
        )

    recommendations = response_payload.get("recommendations")
    if not isinstance(recommendations, list) or not 3 <= len(recommendations) <= 9:
        actual_count = len(recommendations) if isinstance(recommendations, list) else None
        raise ValueError(
            f"recommendations must contain 3 to 9 items: actual={actual_count!r}"
        )

    candidates = _recommendation_candidates(search_results)
    candidate_by_item_id = {
        candidate["item_id"]: candidate for candidate in candidates
    }
    validated_recommendations = []
    selected_item_ids = set()
    for recommendation_index, received_recommendation in enumerate(recommendations):
        if not isinstance(received_recommendation, dict):
            raise ValueError(
                f"recommendation must be an object: "
                f"index={recommendation_index} actual={received_recommendation!r}"
            )
        item_id = received_recommendation.get("item_id")
        if not isinstance(item_id, str) or not item_id.strip():
            raise ValueError(
                f"recommendation item_id must be non-empty text: "
                f"index={recommendation_index} actual={item_id!r}"
            )
        normalized_item_id = item_id.strip()
        if normalized_item_id not in candidate_by_item_id:
            raise ValueError(
                f"AI recommendation references unknown item_id: "
                f"actual={normalized_item_id!r}"
            )
        if normalized_item_id in selected_item_ids:
            raise ValueError(
                f"AI recommendations contain duplicate item_id: "
                f"actual={normalized_item_id!r}"
            )
        selected_item_ids.add(normalized_item_id)

        evidence = received_recommendation.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            raise ValueError(
                f"recommendation evidence must be a non-empty list: "
                f"index={recommendation_index} actual={evidence!r}"
            )
        validated_evidence = []
        for evidence_index, received_evidence in enumerate(evidence):
            if not isinstance(received_evidence, dict):
                raise ValueError(
                    f"recommendation evidence must be an object: "
                    f"recommendation_index={recommendation_index} "
                    f"evidence_index={evidence_index} actual={received_evidence!r}"
                )
            field_name = received_evidence.get("field")
            if field_name not in MARKET_RECOMMENDATION_EVIDENCE_FIELDS:
                raise ValueError(
                    f"unsupported evidence field: actual={field_name!r}"
                )
            expected_value = candidate_by_item_id[normalized_item_id][field_name]
            received_value = received_evidence.get("value")
            if type(received_value) is not type(expected_value) or received_value != expected_value:
                raise ValueError(
                    f"evidence value does not match saved snapshot: "
                    f"item_id={normalized_item_id!r} field={field_name!r} "
                    f"expected={expected_value!r} actual={received_value!r}"
                )
            validated_evidence.append(
                {"field": field_name, "value": received_value}
            )

        validated_recommendation = {
            "item_id": normalized_item_id,
            "recommendation_type": _required_recommendation_text(
                "recommendation_type",
                received_recommendation.get("recommendation_type"),
                recommendation_index,
            ),
            "entry_decision": _required_recommendation_text(
                "entry_decision",
                received_recommendation.get("entry_decision"),
                recommendation_index,
            ),
            "evidence": validated_evidence,
            "learning_point": _required_recommendation_text(
                "learning_point",
                received_recommendation.get("learning_point"),
                recommendation_index,
            ),
            "counter_strategy": _required_recommendation_text(
                "counter_strategy",
                received_recommendation.get("counter_strategy"),
                recommendation_index,
            ),
            "avoid_point": _required_recommendation_text(
                "avoid_point",
                received_recommendation.get("avoid_point"),
                recommendation_index,
            ),
            "test_hypothesis": _required_recommendation_text(
                "test_hypothesis",
                received_recommendation.get("test_hypothesis"),
                recommendation_index,
            ),
            "risk": _required_recommendation_text(
                "risk",
                received_recommendation.get("risk"),
                recommendation_index,
            ),
            "deep_dive_advice": _required_recommendation_text(
                "deep_dive_advice",
                received_recommendation.get("deep_dive_advice"),
                recommendation_index,
            ),
        }
        validated_recommendations.append(validated_recommendation)

    decision_summary = _required_recommendation_text(
        "decision_summary", response_payload.get("decision_summary"), -1
    )
    received_keywords = response_payload.get("keyword_opportunities")
    if not isinstance(received_keywords, list) or not 3 <= len(received_keywords) <= 5:
        raise ValueError("keyword_opportunities must contain 3 to 5 items")
    keyword_opportunities = []
    seen_keywords = set()
    for keyword_index, received_keyword in enumerate(received_keywords):
        if not isinstance(received_keyword, dict):
            raise ValueError("keyword opportunity must be an object")
        keyword = _required_recommendation_text(
            "keyword", received_keyword.get("keyword"), keyword_index
        )
        if keyword in seen_keywords:
            raise ValueError(f"duplicate keyword opportunity: actual={keyword!r}")
        seen_keywords.add(keyword)
        keyword_opportunities.append({
            "keyword": keyword,
            "source": _required_recommendation_text(
                "source", received_keyword.get("source"), keyword_index
            ),
            "reason": _required_recommendation_text(
                "reason", received_keyword.get("reason"), keyword_index
            ),
            "confidence": _required_recommendation_text(
                "confidence", received_keyword.get("confidence"), keyword_index
            ),
        })

    received_test_plan = response_payload.get("test_plan")
    if not isinstance(received_test_plan, dict):
        raise ValueError("test_plan must be an object")
    test_plan = {
        field_name: _required_recommendation_text(
            field_name, received_test_plan.get(field_name), -1
        )
        for field_name in (
            "first_batch", "visual_test", "duration", "continue_rule", "stop_rule"
        )
    }
    return {
        "decision_summary": decision_summary,
        "recommendations": validated_recommendations,
        "keyword_opportunities": keyword_opportunities,
        "test_plan": test_plan,
    }


def _validated_search_result(search_result, result_index):
    if not isinstance(search_result, dict):
        raise ValueError(
            f"search_result must be an object: index={result_index} "
            f"actual={search_result!r}"
        )

    item_id = search_result.get("item_id")
    if not isinstance(item_id, str) or not item_id.strip():
        raise ValueError(
            f"item_id must be non-empty text: index={result_index} actual={item_id!r}"
        )

    shop_name = search_result.get("shop_name")
    if shop_name is not None and not isinstance(shop_name, str):
        raise ValueError(
            f"shop_name must be text or None: index={result_index} actual={shop_name!r}"
        )

    platform_type = search_result.get("platform_type")
    if platform_type not in PLATFORM_TYPES:
        raise ValueError(
            f"platform_type must be taobao, tmall, or unknown: "
            f"index={result_index} actual={platform_type!r}"
        )

    suspected_ad = search_result.get("suspected_ad")
    if isinstance(suspected_ad, bool) or suspected_ad not in (0, 1, None):
        raise ValueError(
            f"suspected_ad must be 0, 1, or None: "
            f"index={result_index} actual={suspected_ad!r}"
        )

    return {
        "item_id": item_id.strip(),
        "shop_name": shop_name.strip() if shop_name else None,
        "display_price": search_result.get("display_price"),
        "platform_type": platform_type,
        "suspected_ad": suspected_ad,
    }


def calculate_market_statistics(search_results):
    if not isinstance(search_results, list):
        raise ValueError(f"search_results must be a list: actual={search_results!r}")

    unique_results = []
    seen_item_ids = set()
    duplicate_result_count = 0
    for result_index, search_result in enumerate(search_results):
        validated_result = _validated_search_result(search_result, result_index)
        if validated_result["item_id"] in seen_item_ids:
            duplicate_result_count += 1
            continue
        seen_item_ids.add(validated_result["item_id"])
        unique_results.append(validated_result)

    sample_count = len(unique_results)
    store_counts = Counter(
        result["shop_name"] for result in unique_results if result["shop_name"]
    )
    missing_store_count = sum(result["shop_name"] is None for result in unique_results)

    prices = [
        price
        for result in unique_results
        if (price := _positive_display_price(result["display_price"])) is not None
    ]
    price_statistics = {
        "valid_count": len(prices),
        "missing_or_invalid_count": sample_count - len(prices),
        "minimum": float(min(prices)) if prices else None,
        "median": float(median(prices)) if prices else None,
        "maximum": float(max(prices)) if prices else None,
    }

    platform_counts = Counter(result["platform_type"] for result in unique_results)
    platform_count_result = {
        platform_type: platform_counts[platform_type] for platform_type in PLATFORM_TYPES
    }
    platform_statistics = {
        "counts": platform_count_result,
        "shares_percent": {
            platform_type: _percentage(count, sample_count)
            for platform_type, count in platform_count_result.items()
        },
    }

    known_ad_count = sum(result["suspected_ad"] is not None for result in unique_results)
    suspected_ad_count = sum(result["suspected_ad"] == 1 for result in unique_results)
    suspected_ad_statistics = {
        "known_count": known_ad_count,
        "suspected_count": suspected_ad_count,
        "unknown_count": sample_count - known_ad_count,
        "share_percent": (
            _percentage(suspected_ad_count, known_ad_count) if known_ad_count else None
        ),
    }

    top_store_name = max(store_counts, key=store_counts.get) if store_counts else None
    top_store_product_count = store_counts[top_store_name] if top_store_name else 0
    store_concentration = {
        "top_store_name": top_store_name,
        "top_store_product_count": top_store_product_count,
        "top_store_share_percent": (
            _percentage(top_store_product_count, sample_count) if top_store_name else None
        ),
    }

    return {
        "sample_count": sample_count,
        "duplicate_result_count": duplicate_result_count,
        "store_count": len(store_counts),
        "missing_store_count": missing_store_count,
        "price": price_statistics,
        "platform": platform_statistics,
        "suspected_ad": suspected_ad_statistics,
        "store_concentration": store_concentration,
    }


def _price_percentile(sorted_prices, percentile):
    if not sorted_prices:
        return None
    position = (len(sorted_prices) - 1) * Decimal(str(percentile))
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(sorted_prices) - 1)
    fraction = position - lower_index
    return sorted_prices[lower_index] + (
        sorted_prices[upper_index] - sorted_prices[lower_index]
    ) * fraction


def calculate_price_payment_distribution(search_results):
    """Build chart-ready facts from one complete saved search snapshot."""
    if not isinstance(search_results, list):
        raise ValueError(f"search_results must be a list: actual={search_results!r}")

    unique_results = []
    seen_item_ids = set()
    for result_index, search_result in enumerate(search_results):
        if not isinstance(search_result, dict):
            raise ValueError(
                f"search_result must be an object: index={result_index} "
                f"actual={search_result!r}"
            )
        item_id = str(search_result.get("item_id") or "").strip()
        if not item_id:
            raise ValueError(f"item_id must be non-empty text: index={result_index}")
        if item_id in seen_item_ids:
            continue
        seen_item_ids.add(item_id)
        unique_results.append((item_id, result_index, search_result))

    points = []
    for item_id, result_index, search_result in unique_results:
        price = _positive_display_price(search_result.get("display_price"))
        if price is None:
            continue
        payment_heat = parse_payment_heat(search_result.get("payment_text"))
        shop_name = str(search_result.get("shop_name") or "").strip() or None
        points.append(
            {
                "item_id": item_id,
                "display_rank": search_result.get("display_rank") or result_index + 1,
                "title": search_result.get("title"),
                "shop_name": shop_name,
                "price": float(price),
                "payment_heat_lower_bound": (
                    payment_heat["lower_bound"] if payment_heat else None
                ),
                "payment_text": search_result.get("payment_text"),
            }
        )

    prices = sorted(Decimal(str(point["price"])) for point in points)
    price_summary = {
        "valid_count": len(points),
        "missing_or_invalid_count": len(unique_results) - len(points),
        "minimum": float(prices[0]) if prices else None,
        "median": float(median(prices)) if prices else None,
        "maximum": float(prices[-1]) if prices else None,
    }

    known_payment_count = sum(
        point["payment_heat_lower_bound"] is not None for point in points
    )
    payment_summary = {
        "known_count": known_payment_count,
        "missing_count": len(points) - known_payment_count,
        "coverage_percent": _percentage(known_payment_count, len(points)),
    }

    mainstream_band = None
    if prices:
        lower = _price_percentile(prices, Decimal("0.25"))
        upper = _price_percentile(prices, Decimal("0.75"))
        band_points = [
            point for point in points if lower <= Decimal(str(point["price"])) <= upper
        ]
        mainstream_band = {
            "minimum": float(lower),
            "maximum": float(upper),
            "product_count": len(band_points),
            "shop_count": len(
                {point["shop_name"] for point in band_points if point["shop_name"]}
            ),
        }

    price_groups = {}
    coordinate_groups = {}
    for point in points:
        price_groups.setdefault(point["price"], []).append(point)
        coordinate_groups.setdefault(
            (point["price"], point["payment_heat_lower_bound"]), []
        ).append(point)

    same_price_groups = []
    for price, grouped_points in price_groups.items():
        if len(grouped_points) < 2:
            continue
        same_price_groups.append(
            {
                "price": price,
                "product_count": len(grouped_points),
                "shop_count": len(
                    {
                        point["shop_name"]
                        for point in grouped_points
                        if point["shop_name"]
                    }
                ),
                "item_ids": [point["item_id"] for point in grouped_points],
            }
        )
    same_price_groups.sort(key=lambda group: (-group["product_count"], group["price"]))

    clusters = []
    for (price, heat), grouped_points in coordinate_groups.items():
        clusters.append(
            {
                "price": price,
                "payment_heat_lower_bound": heat,
                "product_count": len(grouped_points),
                "shop_count": len(
                    {
                        point["shop_name"]
                        for point in grouped_points
                        if point["shop_name"]
                    }
                ),
                "item_ids": [point["item_id"] for point in grouped_points],
                "products": grouped_points,
            }
        )
    clusters.sort(
        key=lambda cluster: (
            cluster["price"],
            cluster["payment_heat_lower_bound"] is None,
            cluster["payment_heat_lower_bound"] or 0,
        )
    )

    return {
        "sample_count": len(unique_results),
        "price": price_summary,
        "payment_heat": payment_summary,
        "mainstream_price_band": mainstream_band,
        "same_price_groups": same_price_groups,
        "clusters": clusters,
    }


def _matched_title_terms(normalized_title, canonical_alias_groups):
    matches = []
    for canonical_index, (canonical_term, aliases) in enumerate(canonical_alias_groups):
        for alias in aliases:
            for match in re.finditer(re.escape(alias.casefold()), normalized_title):
                matches.append(
                    (
                        -(match.end() - match.start()),
                        match.start(),
                        canonical_index,
                        canonical_term,
                        match.start(),
                        match.end(),
                    )
                )

    occupied_positions = set()
    selected_terms = []
    for _, _, _, canonical_term, start, end in sorted(matches):
        positions = set(range(start, end))
        if positions & occupied_positions or canonical_term in selected_terms:
            continue
        occupied_positions.update(positions)
        selected_terms.append(canonical_term)
    return selected_terms


def _iphone_specification_terms(normalized_title):
    specifications = []
    suffix_names = {
        "promax": "Pro Max",
        "pro max": "Pro Max",
        "pro": "Pro",
        "plus": "Plus",
        "mini": "Mini",
        "air": "Air",
    }
    for match in IPHONE_MODEL_PATTERN.finditer(normalized_title):
        version = match.group(1)
        suffix = " ".join((match.group(2) or "").split())
        canonical_suffix = suffix_names.get(suffix, "")
        specification = (
            f"{version} {canonical_suffix}" if canonical_suffix else f"{version} 系列"
        )
        if specification not in specifications:
            specifications.append(specification)
    return specifications


def classify_market_title_terms(product_titles):
    if not isinstance(product_titles, list):
        raise ValueError(f"product_titles must be a list: actual={product_titles!r}")

    category_counts = {
        category_name: Counter() for category_name in TITLE_TERM_ALIASES
    }
    sample_title_count = 0
    missing_title_count = 0

    for title_index, product_title in enumerate(product_titles):
        if product_title is not None and not isinstance(product_title, str):
            raise ValueError(
                f"product title must be text or None: "
                f"index={title_index} actual={product_title!r}"
            )
        if product_title is None or not product_title.strip():
            missing_title_count += 1
            continue

        sample_title_count += 1
        normalized_title = product_title.casefold()
        for category_name, canonical_alias_groups in TITLE_TERM_ALIASES.items():
            matched_terms = _matched_title_terms(
                normalized_title,
                canonical_alias_groups,
            )
            if category_name == "specification":
                matched_terms.extend(_iphone_specification_terms(normalized_title))
            for matched_term in dict.fromkeys(matched_terms):
                category_counts[category_name][matched_term] += 1

    return {
        "sample_title_count": sample_title_count,
        "missing_title_count": missing_title_count,
        "categories": {
            category_name: [
                {
                    "term": term,
                    "title_count": title_count,
                    "title_share_percent": _percentage(
                        title_count,
                        sample_title_count,
                    ),
                }
                for term, title_count in sorted(
                    term_counts.items(),
                    key=lambda term_count: -term_count[1],
                )
            ]
            for category_name, term_counts in category_counts.items()
        },
    }
