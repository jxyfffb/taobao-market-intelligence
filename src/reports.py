from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal, InvalidOperation
from html import escape
from io import BytesIO
import json
from pathlib import Path
import re
from zipfile import ZIP_DEFLATED, ZipFile

from openpyxl import Workbook
from openpyxl.drawing.image import Image as SpreadsheetImage
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from PIL import Image as PillowImage

from src.market_analysis import calculate_market_statistics, classify_market_title_terms


XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
HTML_MEDIA_TYPE = "text/html; charset=utf-8"
HEADERS = (
    "排名",
    "主图",
    "标题",
    "店铺",
    "展示价",
    "付款人数",
    "地区",
    "优惠标签",
    "物流/服务",
    "平台",
    "抓取时间",
)

EXCEL_ILLEGAL_CHARACTERS_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F]")


def _excel_safe_value(value):
    if isinstance(value, str):
        return EXCEL_ILLEGAL_CHARACTERS_RE.sub("", value)
    return value


def _append_excel_row(worksheet, row):
    worksheet.append([_excel_safe_value(value) for value in row])


def _numeric_display_price(display_price):
    if display_price in (None, ""):
        return None
    try:
        return float(Decimal(str(display_price)))
    except InvalidOperation:
        return str(display_price)


def _fetch_images(results, image_fetcher, *, workers=4):
    if image_fetcher is None:
        return {}
    fetched = {}
    targets = {
        index: str(result.get("image_url") or "").strip()
        for index, result in enumerate(results)
        if str(result.get("image_url") or "").strip()
    }
    if not targets:
        return fetched
    with ThreadPoolExecutor(max_workers=min(workers, len(targets))) as executor:
        futures = {
            executor.submit(image_fetcher, image_url): index
            for index, image_url in targets.items()
        }
        for future in as_completed(futures):
            index = futures[future]
            try:
                fetched[index] = future.result()
            except Exception as exc:  # A single remote image must not abort the export.
                fetched[index] = exc
    return fetched


def _spreadsheet_image(image_bytes, *, width=72, height=72):
    with PillowImage.open(BytesIO(image_bytes)) as source:
        source.thumbnail((width, height))
        converted = source.convert("RGB")
        output = BytesIO()
        converted.save(output, format="PNG", optimize=True)
    output.seek(0)
    image = SpreadsheetImage(output)
    image.width = width
    image.height = height
    return image, output


def export_search_snapshot_xlsx(keyword, snapshot, output_path, *, image_fetcher=None):
    if not isinstance(keyword, str) or not keyword.strip():
        raise ValueError(f"keyword must be non-empty text: actual={keyword!r}")
    snapshot_id = snapshot.get("snapshot_id")
    results = snapshot.get("results")
    if not isinstance(results, list) or not results:
        raise ValueError(
            f"Cannot export empty search snapshot: snapshot_id={snapshot_id!r} "
            f"results={results!r}"
        )

    output_path = Path(output_path)
    if output_path.suffix.casefold() != ".xlsx":
        raise ValueError(f"XLSX output path must end with .xlsx: actual={output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "商品数据"
    worksheet.sheet_view.showGridLines = False
    worksheet.freeze_panes = "A9"

    worksheet.merge_cells("A1:K1")
    worksheet["A1"] = "关键词市场搜索快照"
    worksheet["A1"].font = Font(name="Microsoft YaHei", size=18, bold=True, color="FFFFFF")
    worksheet["A1"].fill = PatternFill("solid", fgColor="214D37")
    worksheet["A1"].alignment = Alignment(vertical="center")
    worksheet.row_dimensions[1].height = 34

    metadata_rows = (
        ("快照 ID", snapshot_id),
        ("关键词", keyword),
        ("抓取时间", snapshot.get("captured_at")),
        ("价格口径", "搜索页面展示价（非 SKU 成交价）"),
        ("原始来源", snapshot.get("raw_source_ref")),
    )
    for row_number, (label, value) in enumerate(metadata_rows, start=2):
        worksheet.cell(row=row_number, column=1, value=label).font = Font(bold=True, color="214D37")
        worksheet.cell(row=row_number, column=2, value=value)
        worksheet.merge_cells(start_row=row_number, start_column=2, end_row=row_number, end_column=11)

    header_fill = PatternFill("solid", fgColor="E87932")
    header_font = Font(name="Microsoft YaHei", bold=True, color="FFFFFF")
    header_border = Border(bottom=Side(style="medium", color="B9571F"))
    for column_number, header in enumerate(HEADERS, start=1):
        cell = worksheet.cell(row=8, column=column_number, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.border = header_border
        cell.alignment = Alignment(horizontal="center", vertical="center")
    worksheet.row_dimensions[8].height = 26

    fetched_images = _fetch_images(results, image_fetcher)
    image_streams = []
    for result_index, result in enumerate(results):
        row_number = result_index + 9
        row_values = (
            result.get("display_rank"),
            None,
            result.get("title"),
            result.get("shop_name"),
            _numeric_display_price(result.get("display_price")),
            result.get("payment_text"),
            result.get("origin_text"),
            result.get("promotion_text"),
            result.get("logistics_text"),
            result.get("platform_type"),
            result.get("captured_at"),
        )
        for column_number, value in enumerate(row_values, start=1):
            cell = worksheet.cell(row=row_number, column=column_number, value=value)
            cell.alignment = Alignment(
                vertical="center",
                wrap_text=column_number in (3, 6, 7, 8, 9),
            )
        title_cell = worksheet.cell(row=row_number, column=3)
        if result.get("product_url"):
            title_cell.hyperlink = result["product_url"]
            title_cell.style = "Hyperlink"
        worksheet.cell(row=row_number, column=5).number_format = '¥#,##0.00'
        worksheet.row_dimensions[row_number].height = 60

        fetched = fetched_images.get(result_index)
        image_cell = worksheet.cell(row=row_number, column=2)
        if isinstance(fetched, tuple) and fetched and fetched[0]:
            try:
                image, image_stream = _spreadsheet_image(fetched[0], width=64, height=64)
                image.anchor = image_cell.coordinate
                worksheet.add_image(image)
                image_streams.append(image_stream)
            except Exception:
                image_cell.value = "图片处理失败"
        elif result.get("image_url"):
            image_cell.value = "图片获取失败" if image_fetcher else "未加载图片"
        else:
            image_cell.value = "无图"
        image_cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    worksheet.auto_filter.ref = f"A8:K{8 + len(results)}"
    column_widths = (8, 12, 48, 24, 13, 16, 16, 20, 20, 10, 24)
    for column_number, width in enumerate(column_widths, start=1):
        worksheet.column_dimensions[worksheet.cell(row=8, column=column_number).column_letter].width = width

    workbook.save(output_path)
    workbook.close()
    return output_path


COMPETITOR_IMAGE_FOLDERS = {
    "main": "主图",
    "sku": "SKU图",
    "detail": "详情图",
    "review": "评价图",
}


def _safe_export_name(value, fallback="商品"):
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "-", str(value or "").strip())
    value = re.sub(r"\s+", " ", value).strip(" .-")
    return (value[:80] or fallback)


def _image_extension(content_type, image_url):
    extension = {
        "image/avif": ".avif",
        "image/gif": ".gif",
        "image/png": ".png",
        "image/webp": ".webp",
    }.get(str(content_type or "").casefold())
    if extension:
        return extension
    suffix = Path(str(image_url or "").split("?", 1)[0]).suffix.casefold()
    return suffix if suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"} else ".jpg"


def _style_export_sheet(worksheet, widths):
    worksheet.sheet_view.showGridLines = False
    worksheet.freeze_panes = "A2"
    header_fill = PatternFill("solid", fgColor="214D37")
    header_font = Font(name="Microsoft YaHei", bold=True, color="FFFFFF")
    for cell in worksheet[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    worksheet.row_dimensions[1].height = 26
    for column_number, width in enumerate(widths, start=1):
        worksheet.column_dimensions[
            worksheet.cell(row=1, column=column_number).column_letter
        ].width = width
    if worksheet.max_row > 1 and worksheet.max_column > 0:
        worksheet.auto_filter.ref = worksheet.dimensions


def _append_rows(worksheet, rows):
    for row in rows:
        _append_excel_row(worksheet, row)
    for row in worksheet.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)


def _competitor_image_entries(snapshot):
    archive = snapshot.get("archive") or {}
    entries = []
    seen = set()
    product_visual_urls = set()
    counters = {kind: 0 for kind in COMPETITOR_IMAGE_FOLDERS}

    def add(kind, url, source, related_text=""):
        url = str(url or "").strip()
        normalized_kind = kind if kind in COMPETITOR_IMAGE_FOLDERS else "detail"
        identity = (normalized_kind, url)
        if not url or identity in seen:
            return
        if normalized_kind == "detail" and url in product_visual_urls:
            return
        seen.add((normalized_kind, url))
        if normalized_kind in {"main", "sku"}:
            product_visual_urls.add(url)
        counters[normalized_kind] += 1
        entries.append(
            {
                "kind": normalized_kind,
                "sequence": counters[normalized_kind],
                "url": url,
                "source": source,
                "related_text": related_text,
            }
        )

    for image in archive.get("images") or []:
        add(image.get("kind"), image.get("url"), image.get("source") or "商品页面")
    for dimension in (archive.get("sku_catalog") or {}).get("dimensions") or []:
        dimension_label = str(dimension.get("label") or "SKU").strip()
        for option in dimension.get("options") or []:
            option_label = str(option.get("value") or "").strip()
            add(
                "sku",
                option.get("image_url") or option.get("image"),
                "SKU规格",
                f"{dimension_label}：{option_label}" if option_label else dimension_label,
            )
    for review_index, review in enumerate((archive.get("reviews") or {}).get("items") or [], start=1):
        for image_url in review.get("images") or []:
            add("review", image_url, f"评价 {review_index}", review.get("content") or "")
    return entries


def export_competitor_package_zip(
    item_id,
    snapshot,
    output_path,
    *,
    image_fetcher=None,
):
    item_id = str(item_id or "").strip()
    if not item_id.isdigit():
        raise ValueError(f"item_id must contain digits only: actual={item_id!r}")
    if not isinstance(snapshot, dict) or not snapshot.get("product_snapshot_id"):
        raise ValueError("snapshot must be a saved product snapshot")
    output_path = Path(output_path)
    if output_path.suffix.casefold() != ".zip":
        raise ValueError(f"ZIP output path must end with .zip: actual={output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    archive = snapshot.get("archive") or {}
    fields = archive.get("product_fields") or {}
    sku_catalog = archive.get("sku_catalog") or {}
    reviews = archive.get("reviews") or {}
    questions = archive.get("questions") or {}
    image_entries = _competitor_image_entries(snapshot)
    fetched_images = _fetch_images(
        [{"image_url": entry["url"]} for entry in image_entries],
        image_fetcher,
    )
    workbook = Workbook()
    overview = workbook.active
    overview.title = "商品概览"
    _append_excel_row(overview, ["字段", "采集内容"])
    overview_rows = [
        ("商品 ID", item_id),
        ("标题", snapshot.get("title")),
        ("店铺", fields.get("shop_name") or snapshot.get("shop_name")),
        ("当前价格", fields.get("price_text") or snapshot.get("visible_price_text")),
        ("付款/销量", fields.get("payment_text") or fields.get("sold_text") or snapshot.get("sold_text")),
        ("发货地", fields.get("origin_text")),
        ("优惠标签", "、".join(fields.get("promotions") or [])),
        ("物流/服务", "、".join([*(fields.get("logistics") or []), *(fields.get("services") or []), *(snapshot.get("services") or [])])),
        ("店铺评分", snapshot.get("shop_rating_text")),
        ("好评率", snapshot.get("shop_positive_rate_text")),
        ("发货表现", snapshot.get("shop_shipping_text")),
        ("退款表现", snapshot.get("shop_refund_text")),
        ("回头客", snapshot.get("repeat_buyer_text")),
        ("加购", snapshot.get("cart_text")),
        ("评价数量", reviews.get("total_text") or snapshot.get("review_count_text")),
        ("商品参数", fields.get("attributes_text") or snapshot.get("attributes_text")),
        ("商品页面", snapshot.get("page_url")),
        ("采集时间", snapshot.get("captured_at")),
    ]
    _append_rows(overview, overview_rows)
    _style_export_sheet(overview, (20, 90))
    if snapshot.get("page_url"):
        overview["B18"].hyperlink = snapshot["page_url"]
        overview["B18"].style = "Hyperlink"

    images_sheet = workbook.create_sheet("图片目录")
    _append_excel_row(images_sheet, ["类型", "序号", "缩略图", "文件", "来源", "关联内容", "原始地址", "状态"])
    image_streams = []
    packaged_images = []
    kind_labels = {"main": "主图", "sku": "SKU图", "detail": "详情图", "review": "评价图"}
    for image_index, entry in enumerate(image_entries):
        fetched = fetched_images.get(image_index)
        image_bytes = fetched[0] if isinstance(fetched, tuple) and fetched else None
        content_type = fetched[1] if isinstance(fetched, tuple) and len(fetched) > 1 else None
        folder = COMPETITOR_IMAGE_FOLDERS[entry["kind"]]
        label = kind_labels[entry["kind"]]
        filename = f"{label}-{entry['sequence']:03d}{_image_extension(content_type, entry['url'])}"
        archive_name = f"{folder}/{filename}"
        status = "已保存" if image_bytes else ("获取失败" if image_fetcher else "未下载")
        row_number = images_sheet.max_row + 1
        _append_excel_row(images_sheet, [
            label,
            entry["sequence"],
            None,
            archive_name,
            entry["source"],
            entry["related_text"],
            entry["url"],
            status,
        ])
        images_sheet.row_dimensions[row_number].height = 72
        if image_bytes:
            packaged_images.append((archive_name, image_bytes))
            try:
                image, image_stream = _spreadsheet_image(image_bytes, width=72, height=72)
                image.anchor = f"C{row_number}"
                images_sheet.add_image(image)
                image_streams.append(image_stream)
            except Exception:
                images_sheet.cell(row=row_number, column=3, value="无法预览")
        images_sheet.cell(row=row_number, column=4).hyperlink = archive_name
        images_sheet.cell(row=row_number, column=4).style = "Hyperlink"
    _style_export_sheet(images_sheet, (12, 8, 14, 30, 18, 48, 56, 12))

    sku_sheet = workbook.create_sheet("SKU数据")
    _append_excel_row(sku_sheet, ["规格维度", "规格值", "值 ID", "可用状态", "SKU图片", "已选规格", "目标SKU价格", "价格状态"])
    selected_options = (snapshot.get("sku") or {}).get("selected_options") or []
    selected_text = " / ".join(
        str(item.get("value") or item.get("label") or item) if isinstance(item, dict) else str(item)
        for item in selected_options
    )
    dimensions = sku_catalog.get("dimensions") or []
    for dimension in dimensions:
        for option in dimension.get("options") or []:
            _append_excel_row(sku_sheet, [
                dimension.get("label"),
                option.get("value"),
                option.get("value_id") or option.get("valueId"),
                "可选" if option.get("available", True) else "不可选",
                option.get("image_url") or option.get("image"),
                selected_text,
                (snapshot.get("sku") or {}).get("sku_price_text"),
                (snapshot.get("sku") or {}).get("price_status"),
            ])
    if not dimensions:
        _append_excel_row(sku_sheet, ["本次未采集到 SKU 目录", None, None, None, None, selected_text, (snapshot.get("sku") or {}).get("sku_price_text"), (snapshot.get("sku") or {}).get("price_status")])
    _append_rows(sku_sheet, [])
    _style_export_sheet(sku_sheet, (20, 36, 18, 14, 52, 38, 18, 18))

    review_sheet = workbook.create_sheet("评价与问大家")
    _append_excel_row(review_sheet, ["类型", "序号", "内容", "规格/回答数", "日期", "标签或回答", "图片数"])
    review_tags = "、".join(reviews.get("tags") or [])
    for review_index, review in enumerate(reviews.get("items") or [], start=1):
        _append_excel_row(review_sheet, [
            "评价",
            review_index,
            review.get("content"),
            review.get("sku"),
            review.get("date"),
            review_tags if review_index == 1 else None,
            len(review.get("images") or []),
        ])
    for question_index, question in enumerate(questions.get("items") or [], start=1):
        _append_excel_row(review_sheet, [
            "问大家",
            question_index,
            question.get("question"),
            question.get("answer_count"),
            None,
            "\n".join(question.get("answers") or []),
            0,
        ])
    if review_sheet.max_row == 1:
        _append_excel_row(review_sheet, ["数据缺失", 1, "本次页面没有返回可保存的评价或问答样本", None, None, None, 0])
    _append_rows(review_sheet, [])
    _style_export_sheet(review_sheet, (12, 8, 70, 24, 18, 60, 10))

    review_workbook = Workbook()
    review_export_sheet = review_workbook.active
    review_export_sheet.title = "评价与问大家"
    for row in review_sheet.iter_rows(values_only=True):
        _append_excel_row(review_export_sheet, list(row))
    _style_export_sheet(review_export_sheet, (12, 8, 70, 24, 18, 60, 10))
    review_workbook_bytes = BytesIO()
    review_workbook.save(review_workbook_bytes)
    review_workbook.close()
    review_workbook_bytes.seek(0)
    workbook.remove(review_sheet)

    evidence_sheet = workbook.create_sheet("采集说明")
    _append_excel_row(evidence_sheet, ["项目", "内容"])
    _append_rows(evidence_sheet, [
        ("覆盖状态", json.dumps(archive.get("coverage") or {}, ensure_ascii=False)),
        ("采集状态", json.dumps(archive.get("capture_status") or {}, ensure_ascii=False)),
        ("证据来源", json.dumps(archive.get("raw_source_refs") or {}, ensure_ascii=False)),
        ("说明", "仅保存页面实际返回的数据；缺失字段不会推测或补造。"),
    ])
    _style_export_sheet(evidence_sheet, (20, 100))

    workbook_bytes = BytesIO()
    workbook.save(workbook_bytes)
    workbook.close()
    workbook_bytes.seek(0)
    raw_payload = {
        "item_id": item_id,
        "exported_snapshot": snapshot,
    }
    with ZipFile(output_path, "w", compression=ZIP_DEFLATED) as archive_file:
        archive_file.writestr("商品信息.xlsx", workbook_bytes.getvalue())
        archive_file.writestr("评价与问大家.xlsx", review_workbook_bytes.getvalue())
        archive_file.writestr(
            "原始数据.json",
            json.dumps(raw_payload, ensure_ascii=False, indent=2),
        )
        for archive_name, image_bytes in packaged_images:
            archive_file.writestr(archive_name, image_bytes)
    return output_path


TERM_CATEGORY_LABELS = {
    "product": "产品词",
    "function": "功能词",
    "material": "材质词",
    "specification": "规格词",
    "audience": "人群词",
    "scenario": "场景词",
    "style": "风格词",
    "brand": "品牌词",
}


def _percent_label(percent):
    return f"{percent:.2f}".rstrip("0").rstrip(".") + "%"


def _price_summary(price_statistics):
    if price_statistics["valid_count"] == 0:
        return "没有有效展示价"
    return (
        f"最低 ¥{price_statistics['minimum']:.2f} · "
        f"中位 ¥{price_statistics['median']:.2f} · "
        f"最高 ¥{price_statistics['maximum']:.2f}"
    )


def _title_term_sections(title_classification):
    sections = []
    for category_name, category_label in TERM_CATEGORY_LABELS.items():
        terms = title_classification["categories"][category_name]
        if terms:
            term_cards = "".join(
                "<li><strong>"
                + escape(term["term"])
                + "</strong><span>"
                + str(term["title_count"])
                + " 条标题 · "
                + _percent_label(term["title_share_percent"])
                + "</span></li>"
                for term in terms
            )
        else:
            term_cards = '<li class="empty">本次标题未命中已知词表</li>'
        sections.append(
            f'<article class="term-group"><h3>{category_label}</h3>'
            f'<ul class="term-list">{term_cards}</ul></article>'
        )
    return "".join(sections)


def export_market_report_html(keyword, snapshot, output_path):
    if not isinstance(keyword, str) or not keyword.strip():
        raise ValueError(f"keyword must be non-empty text: actual={keyword!r}")
    if not isinstance(snapshot, dict):
        raise ValueError(f"snapshot must be an object: actual={snapshot!r}")

    snapshot_id = snapshot.get("snapshot_id")
    results = snapshot.get("results")
    if not isinstance(results, list) or not results:
        raise ValueError(
            f"Cannot export empty market report: snapshot_id={snapshot_id!r} "
            f"results={results!r}"
        )

    output_path = Path(output_path)
    if output_path.suffix.casefold() != ".html":
        raise ValueError(f"HTML output path must end with .html: actual={output_path}")

    statistics = calculate_market_statistics(results)
    title_classification = classify_market_title_terms(
        [result.get("title") for result in results]
    )
    platform_shares = statistics["platform"]["shares_percent"]
    suspected_ad = statistics["suspected_ad"]
    store_concentration = statistics["store_concentration"]
    sample_count = statistics["sample_count"]
    known_store_count = sample_count - statistics["missing_store_count"]
    store_coverage = _percent_label(known_store_count * 100 / sample_count)
    price_coverage = _percent_label(
        statistics["price"]["valid_count"] * 100 / sample_count
    )
    title_coverage = _percent_label(
        title_classification["sample_title_count"] * 100 / sample_count
    )
    ad_coverage = _percent_label(suspected_ad["known_count"] * 100 / sample_count)
    ad_summary = (
        "广告标记覆盖不足，不能计算疑似广告占比"
        if suspected_ad["share_percent"] is None
        else (
            f"疑似广告 {suspected_ad['suspected_count']} 条，占已识别标记 "
            f"{_percent_label(suspected_ad['share_percent'])}"
        )
    )
    concentration_summary = (
        (
            f"{escape(store_concentration['top_store_name'])}占样本坑位 "
            f"{_percent_label(store_concentration['top_store_share_percent'])}"
        )
        if store_concentration["top_store_name"]
        else "店铺名称全部缺失，无法计算头部店铺"
    )
    escaped_keyword = escape(keyword.strip())
    escaped_capture_time = escape(str(snapshot.get("captured_at") or "缺失"))
    escaped_raw_source = escape(str(snapshot.get("raw_source_ref") or "缺失"))
    term_sections = _title_term_sections(title_classification)

    report_html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escaped_keyword}｜基础市场报告</title>
  <style>
    :root {{ color-scheme: light; --ink:#183328; --muted:#64736d; --paper:#f5f1e8; --card:#fffdf8; --line:#ded7c9; --green:#214d37; --orange:#e87932; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:var(--paper); color:var(--ink); font-family:"Microsoft YaHei",system-ui,sans-serif; line-height:1.65; }}
    main {{ width:min(1080px,calc(100% - 32px)); margin:32px auto 64px; }}
    header {{ padding:36px; border-radius:22px; color:white; background:linear-gradient(135deg,#173c2a,#2d6549); }}
    h1 {{ margin:8px 0 10px; font-size:32px; line-height:1.25; }}
    h2 {{ margin:0 0 18px; font-size:22px; }}
    h3 {{ margin:0 0 10px; font-size:16px; }}
    p {{ margin:6px 0; }}
    .eyebrow,.level {{ font-size:12px; font-weight:700; letter-spacing:.08em; text-transform:uppercase; }}
    .eyebrow {{ color:#ffd2ad; }}
    .scope {{ color:#dce9e2; }}
    section {{ margin-top:22px; padding:26px; border:1px solid var(--line); border-radius:18px; background:var(--card); }}
    .grid {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:14px; }}
    .card {{ padding:18px; border:1px solid var(--line); border-radius:14px; background:white; }}
    .card strong {{ display:block; margin-top:6px; font-size:20px; }}
    .label {{ color:var(--muted); font-size:13px; }}
    .facts {{ width:100%; border-collapse:collapse; }}
    .facts th,.facts td {{ padding:10px 12px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top; }}
    .facts th {{ width:170px; color:var(--muted); font-weight:600; }}
    .level {{ display:inline-block; padding:3px 8px; border-radius:999px; color:var(--green); background:#e4eee7; }}
    .level.rule {{ color:#8a471d; background:#ffead9; }}
    .term-grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:14px; }}
    .term-group {{ padding:18px; border:1px solid var(--line); border-radius:14px; }}
    .term-list {{ display:flex; flex-wrap:wrap; gap:8px; margin:0; padding:0; list-style:none; }}
    .term-list li {{ display:flex; gap:7px; padding:6px 9px; border-radius:8px; background:#f2eee5; font-size:13px; }}
    .term-list span {{ color:var(--muted); }}
    .term-list .empty {{ color:var(--muted); }}
    .warning {{ border-left:5px solid var(--orange); }}
    .missing-list {{ margin-bottom:0; }}
    footer {{ margin-top:18px; color:var(--muted); font-size:12px; text-align:center; }}
    @media (max-width:760px) {{ .grid,.term-grid {{ grid-template-columns:1fr; }} main {{ width:min(100% - 20px,1080px); margin-top:10px; }} header,section {{ padding:20px; border-radius:14px; }} }}
    @media print {{ @page {{ size:A4; margin:14mm; }} body {{ background:white; }} main {{ width:100%; margin:0; }} header {{ print-color-adjust:exact; -webkit-print-color-adjust:exact; }} section {{ break-inside:avoid; box-shadow:none; }} .term-group {{ break-inside:avoid; }} }}
  </style>
</head>
<body>
<main>
  <header>
    <div class="eyebrow">淘宝选品与竞品情报操作台</div>
    <h1>{escaped_keyword}｜基础市场报告</h1>
    <p class="scope">基于当前一次搜索快照生成，只描述本次可观测样本，不代表全市场销量或长期趋势。</p>
  </header>

  <section>
    <h2>数据范围与口径 <span class="level">程序事实</span></h2>
    <table class="facts">
      <tr><th>关键词</th><td>{escaped_keyword}</td></tr>
      <tr><th>抓取时间</th><td>{escaped_capture_time}</td></tr>
      <tr><th>快照与样本</th><td>快照 {snapshot_id} · {sample_count} 个商品 · 展示排名前 {sample_count} 条</td></tr>
      <tr><th>价格口径</th><td>搜索页面展示价，不是 SKU 成交价</td></tr>
      <tr><th>原始证据</th><td>{escaped_raw_source}</td></tr>
    </table>
  </section>

  <section>
    <h2>市场结构 <span class="level">程序事实</span></h2>
    <div class="grid">
      <article class="card"><span class="label">商品与店铺</span><strong>{sample_count} 个商品</strong><p>{statistics['store_count']} 家可识别店铺</p></article>
      <article class="card"><span class="label">展示价格</span><strong>{_price_summary(statistics['price'])}</strong><p>有效价格覆盖 {price_coverage}</p></article>
      <article class="card"><span class="label">平台结构</span><strong>淘宝 {_percent_label(platform_shares['taobao'])}</strong><p>天猫 {_percent_label(platform_shares['tmall'])} · 未识别 {_percent_label(platform_shares['unknown'])}</p></article>
      <article class="card"><span class="label">疑似广告</span><strong>{ad_summary}</strong><p>标记覆盖 {ad_coverage}</p></article>
      <article class="card"><span class="label">店铺集中度</span><strong>{concentration_summary}</strong><p>店铺字段覆盖 {store_coverage}</p></article>
      <article class="card"><span class="label">标题覆盖</span><strong>{title_coverage}</strong><p>按标题条数计算，不代表成交贡献</p></article>
    </div>
  </section>

  <section>
    <h2>标题候选词 <span class="level rule">规则识别</span></h2>
    <p>以下为内置词表命中频次，用于观察标题表达，不代表需求量、销量或转化效果。</p>
    <div class="term-grid">{term_sections}</div>
  </section>

  <section class="warning">
    <h2>缺失项与不可判断范围</h2>
    <ul class="missing-list">
      <li>缺失标题 {title_classification['missing_title_count']} 条。</li>
      <li>缺失或无效展示价 {statistics['price']['missing_or_invalid_count']} 条。</li>
      <li>缺失店铺名称 {statistics['missing_store_count']} 条。</li>
      <li>广告标记未知 {suspected_ad['unknown_count']} 条。</li>
      <li>体量、利润、转化率、PPC 和真实趋势：数据缺失，未分析。</li>
      <li>SKU 成交价、评价、详情页与视觉表达：尚未深挖，未分析。</li>
    </ul>
  </section>

  <section>
    <h2>事实等级说明</h2>
    <p><span class="level">程序事实</span> 直接来自已保存快照或确定性计算，可回到原始证据复核。</p>
    <p><span class="level rule">规则识别</span> 来自内置词表匹配，只表达标题中出现过什么。</p>
    <p><strong>数据缺失，未分析</strong> 表示现有快照不足以支持结论，报告没有使用推测补齐。</p>
  </section>
  <footer>本报告为本地生成的基础市场快照报告。</footer>
</main>
</body>
</html>
"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report_html, encoding="utf-8")
    return output_path


def _competitor_display_value(value):
    if value is None or value == "":
        return "数据缺失"
    if isinstance(value, list):
        if not value:
            return "数据缺失"
        rendered_items = []
        for item in value:
            if isinstance(item, dict):
                dimension = item.get("dimension")
                option_value = item.get("value")
                rendered_items.append(
                    f"{dimension}：{option_value}" if dimension else str(option_value)
                )
            else:
                rendered_items.append(str(item))
        return "；".join(rendered_items)
    return str(value)


def _competitor_evidence_badge(evidence_level):
    labels = {
        "program_fact": "程序事实",
        "rule_judgment": "规则判断",
        "ai_inference": "AI 推测",
        "missing": "数据缺失",
    }
    label = labels.get(evidence_level, "数据缺失")
    return f'<span class="badge {escape(str(evidence_level or "missing"))}">{label}</span>'


def _competitor_fact_row(label, evidence):
    if not isinstance(evidence, dict):
        evidence = {"value": None, "evidence_level": "missing", "note": "字段结构缺失。"}
    return (
        "<tr>"
        f"<th>{escape(label)}</th>"
        f"<td>{escape(_competitor_display_value(evidence.get('value')))}</td>"
        f"<td>{_competitor_evidence_badge(evidence.get('evidence_level'))}</td>"
        f"<td>{escape(str(evidence.get('note') or ''))}</td>"
        "</tr>"
    )


def export_competitor_report_html(analysis, output_path):
    if not isinstance(analysis, dict):
        raise ValueError(f"analysis must be an object: actual={analysis!r}")
    item_id = analysis.get("item_id")
    keyword = analysis.get("keyword")
    snapshot_id = analysis.get("product_snapshot_id")
    if not isinstance(item_id, str) or not item_id.strip():
        raise ValueError(f"analysis item_id must be non-empty text: actual={item_id!r}")
    if not isinstance(keyword, str) or not keyword.strip():
        raise ValueError(f"analysis keyword must be non-empty text: actual={keyword!r}")
    if not isinstance(snapshot_id, int) or isinstance(snapshot_id, bool):
        raise ValueError(
            "analysis product_snapshot_id must be an integer: "
            f"actual={snapshot_id!r}"
        )
    output_path = Path(output_path)
    if output_path.suffix.casefold() != ".html":
        raise ValueError(f"HTML output path must end with .html: actual={output_path}")

    profile = analysis.get("profile") or {}
    sku_price = analysis.get("sku_price") or {}
    review_concerns = analysis.get("review_concerns") or {}
    direct_competitor = analysis.get("direct_competitor") or {}
    profile_labels = (
        ("商品标题", "title"),
        ("店铺", "shop_name"),
        ("采集时间", "captured_at"),
        ("搜索展示顺序", "search_rank"),
        ("页面可见销量", "visible_sales"),
        ("页面回头客", "repeat_buyer"),
        ("页面加购", "cart"),
        ("评价数量", "review_count"),
        ("服务", "services"),
        ("资料完整度", "completeness_percent"),
        ("原始证据", "raw_source_ref"),
    )
    price_labels = (
        ("已选规格", "selected_options"),
        ("搜索展示价", "search_display_price"),
        ("详情页可见价", "detail_visible_price"),
        ("SKU 面板展示价", "sku_panel_display_price"),
        ("目标 SKU 实价", "target_sku_price"),
        ("SKU 价格状态", "price_status"),
        ("SKU 原始证据", "raw_source_ref"),
    )
    profile_rows = "".join(
        _competitor_fact_row(label, profile.get(field_name))
        for label, field_name in profile_labels
    )
    price_rows = "".join(
        _competitor_fact_row(label, sku_price.get(field_name))
        for label, field_name in price_labels
    )

    chain_sections = []
    for stage in analysis.get("transaction_chain") or []:
        observations = []
        for observation in stage.get("observations") or []:
            observations.append(
                "<li>"
                f"{_competitor_evidence_badge(observation.get('evidence_level'))} "
                f"{escape(_competitor_display_value(observation.get('value')))}"
                f"<small>{escape(str(observation.get('note') or ''))}</small>"
                "</li>"
            )
        chain_sections.append(
            f"<article class=\"chain-card\"><h3>{escape(str(stage.get('stage') or '未命名阶段'))}</h3>"
            f"<ul>{''.join(observations)}</ul></article>"
        )

    review_rows = "".join(
        _competitor_fact_row(label, review_concerns.get(field_name))
        for label, field_name in (
            ("页面评价预览", "review_preview"),
            ("认可点", "recognized_points"),
            ("差评与顾虑", "concerns"),
            ("复购理由", "repeat_reasons"),
            ("未满足需求", "unmet_needs"),
        )
    )
    unknown_items = "".join(
        "<li>"
        f"{_competitor_evidence_badge(item.get('evidence_level'))} "
        f"<strong>{escape(str(item.get('label') or item.get('field') or '未知项'))}</strong>："
        f"{escape(str(item.get('reason') or '当前无法确认。'))}"
        "</li>"
        for item in analysis.get("unknown_data") or []
    )
    legend_items = "".join(
        "<li>"
        f"{_competitor_evidence_badge(level.get('key'))} "
        f"{escape(str(level.get('description') or ''))}"
        "</li>"
        for level in analysis.get("evidence_legend") or []
    )
    escaped_keyword = escape(keyword.strip())
    escaped_item_id = escape(item_id.strip())
    direct_label = escape(str(direct_competitor.get("label") or "数据缺失"))
    direct_reason = escape(str(direct_competitor.get("reason") or "当前无法判断。"))
    direct_badge = _competitor_evidence_badge(
        direct_competitor.get("evidence_level")
    )

    report_html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escaped_keyword}｜竞品分析报告</title>
  <style>
    :root {{ color-scheme:light; --ink:#17332a; --muted:#64716c; --paper:#f4f0e8; --card:#fffdf8; --line:#ddd5c7; --green:#24523c; --orange:#b65d25; --red:#9d3c32; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:var(--paper); color:var(--ink); font-family:"Microsoft YaHei",system-ui,sans-serif; line-height:1.65; }}
    main {{ width:min(1100px,calc(100% - 32px)); margin:30px auto 60px; }}
    header {{ padding:34px; border-radius:22px; color:white; background:linear-gradient(135deg,#173c2a,#2d6549); }}
    header p {{ color:#dfece5; }}
    h1 {{ margin:7px 0 8px; font-size:32px; }} h2 {{ margin:0 0 16px; font-size:22px; }} h3 {{ margin:0 0 10px; }}
    section {{ margin-top:20px; padding:25px; border:1px solid var(--line); border-radius:18px; background:var(--card); }}
    .decision {{ border-left:6px solid var(--orange); }}
    .decision strong {{ display:block; margin:8px 0; font-size:24px; }}
    table {{ width:100%; border-collapse:collapse; }} th,td {{ padding:10px 11px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top; }} th {{ width:150px; color:var(--muted); }}
    td:nth-child(3) {{ width:110px; }} td:nth-child(4) {{ color:var(--muted); font-size:13px; }}
    .badge {{ display:inline-block; padding:3px 8px; border-radius:999px; background:#e4eee7; color:var(--green); font-size:12px; font-weight:700; white-space:nowrap; }}
    .badge.rule_judgment {{ background:#ffead9; color:#8a471d; }} .badge.ai_inference {{ background:#e8e2f7; color:#5e438f; }} .badge.missing {{ background:#f6e3e0; color:var(--red); }}
    .chain-grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:14px; }} .chain-card {{ padding:18px; border:1px solid var(--line); border-radius:14px; }}
    ul {{ margin:0; padding-left:20px; }} li {{ margin:8px 0; }} small {{ display:block; color:var(--muted); }}
    .price-warning {{ margin:0 0 16px; padding:12px 14px; border-left:4px solid var(--orange); background:#fff3e7; }}
    footer {{ margin-top:16px; color:var(--muted); text-align:center; font-size:12px; }}
    @media (max-width:760px) {{ main {{ width:calc(100% - 20px); margin-top:10px; }} header,section {{ padding:19px; border-radius:14px; }} .chain-grid {{ grid-template-columns:1fr; }} table,tbody,tr,th,td {{ display:block; width:100%; }} th {{ padding-bottom:2px; border-bottom:0; }} }}
    @media print {{ @page {{ size:A4; margin:14mm; }} body {{ background:white; }} main {{ width:100%; margin:0; }} header {{ print-color-adjust:exact; -webkit-print-color-adjust:exact; }} section,.chain-card {{ break-inside:avoid; }} }}
  </style>
</head>
<body>
<main>
  <header>
    <div>淘宝选品与竞品情报操作台</div>
    <h1>{escaped_keyword}｜竞品分析报告</h1>
    <p>商品 ID {escaped_item_id} · 详情快照 {snapshot_id} · 仅基于已保存证据生成</p>
  </header>
  <section class="decision">
    <h2>直接竞品判断 {direct_badge}</h2>
    <strong>{direct_label}</strong>
    <p>{direct_reason}</p>
  </section>
  <section><h2>基础档案</h2><table>{profile_rows}</table></section>
  <section><h2>成交链路</h2><div class="chain-grid">{''.join(chain_sections)}</div></section>
  <section>
    <h2>SKU 与价格</h2>
    <p class="price-warning"><strong>价格口径：</strong>搜索展示价、详情页可见价和 SKU 面板展示价都不是目标 SKU 实价；只有目标规格刷新后成功读取的价格才进入“目标 SKU 实价”。</p>
    <table>{price_rows}</table>
  </section>
  <section><h2>评价与购买顾虑</h2><table>{review_rows}</table></section>
  <section><h2>未知数据</h2><ul>{unknown_items}</ul></section>
  <section><h2>证据等级</h2><ul>{legend_items}</ul></section>
  <footer>本报告为本地生成的竞品快照报告，不承诺公开页面无法确认的经营数据。</footer>
</main>
</body>
</html>
"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report_html, encoding="utf-8")
    return output_path


def export_enhanced_market_report_html(analysis, output_path):
    if not isinstance(analysis, dict):
        raise ValueError(f"analysis must be an object: actual={analysis!r}")
    keyword = analysis.get("keyword")
    if not isinstance(keyword, str) or not keyword.strip():
        raise ValueError(f"analysis keyword must be non-empty text: actual={keyword!r}")
    successful_samples = analysis.get("successful_samples")
    failed_samples = analysis.get("failed_samples")
    conclusions = analysis.get("conclusions")
    if not isinstance(successful_samples, list) or not isinstance(failed_samples, list):
        raise ValueError("enhanced analysis samples must be lists")
    if not isinstance(conclusions, dict):
        raise ValueError("enhanced analysis conclusions must be an object")
    output_path = Path(output_path)
    if output_path.suffix.casefold() != ".html":
        raise ValueError(f"HTML output path must end with .html: actual={output_path}")

    success_cards = []
    for sample in successful_samples:
        competitor = sample["analysis"]
        target_price = competitor["sku_price"]["target_sku_price"]
        success_cards.append(
            "<article class=\"sample success\">"
            f"<span>排名 {sample['display_rank']} · 商品 {escape(sample['item_id'])}</span>"
            f"<h3>{escape(str(sample.get('title') or '标题缺失'))}</h3>"
            f"<p><strong>{escape(competitor['direct_competitor']['label'])}</strong> · "
            f"目标 SKU 实价 {escape(_competitor_display_value(target_price.get('value')))}</p>"
            f"<small>{escape(target_price.get('note') or '')}</small>"
            "</article>"
        )
    failure_cards = [
        "<article class=\"sample failure\">"
        f"<span>排名 {sample['display_rank']} · 商品 {escape(sample['item_id'])}</span>"
        f"<h3>{escape(str(sample.get('title') or '标题缺失'))}</h3>"
        f"<p>{escape(sample['reason'])}</p>"
        "</article>"
        for sample in failed_samples
    ]
    price_text = "、".join(
        escape(str(price))
        for price in conclusions.get("captured_target_sku_prices") or []
    ) or "没有成功读取的目标 SKU 实价"
    escaped_keyword = escape(keyword.strip())
    scope_note = escape(str(conclusions.get("scope_note") or ""))
    report_html = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escaped_keyword}｜增强市场报告</title>
<style>
:root{{--ink:#17332a;--muted:#65726c;--paper:#f2efe7;--card:#fffdf8;--line:#ddd6c9;--green:#1c4a34;--orange:#e87932;--red:#9c4038}}*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font-family:"Microsoft YaHei",sans-serif;line-height:1.65}}main{{width:min(1080px,calc(100% - 30px));margin:30px auto 60px}}header{{padding:34px;border-radius:20px;color:white;background:linear-gradient(135deg,#153526,#2d6549)}}h1{{margin:6px 0}}section{{margin-top:18px;padding:24px;border:1px solid var(--line);border-radius:16px;background:var(--card)}}.metrics{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}}.metric,.sample{{padding:15px;border:1px solid var(--line);border-radius:10px;background:white}}.metric strong{{display:block;font-size:24px}}.samples{{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}}.sample span,.sample small{{color:var(--muted);font-size:12px}}.sample h3{{margin:6px 0;font-size:16px}}.failure{{border-left:5px solid var(--red);background:#fff7f5}}.success{{border-left:5px solid var(--green)}}.scope{{border-left:5px solid var(--orange)}}@media(max-width:700px){{.metrics,.samples{{grid-template-columns:1fr}}}}@media print{{@page{{size:A4;margin:14mm}}body{{background:white}}main{{width:100%;margin:0}}section,.sample{{break-inside:avoid}}}}
</style></head><body><main>
<header><div>淘宝选品与竞品情报操作台</div><h1>{escaped_keyword}｜增强市场报告</h1><p>基于用户确认的最多 9 个样本，只汇总已完成详情采集的成功样本。</p></header>
<section class="scope"><h2>结论口径</h2><p>{scope_note}</p><p>目标 SKU 实价：{price_text}</p></section>
<section><h2>采集结果</h2><div class="metrics"><article class="metric"><span>确认样本</span><strong>{len(analysis.get('confirmed_item_ids') or [])}</strong></article><article class="metric"><span>成功样本</span><strong>{len(successful_samples)}</strong></article><article class="metric"><span>失败样本</span><strong>{len(failed_samples)}</strong></article></div></section>
<section><h2>成功样本 {len(successful_samples)}</h2><div class="samples">{''.join(success_cards) or '<p>没有成功样本，未生成增强结论。</p>'}</div></section>
<section><h2>失败样本 {len(failed_samples)}</h2><div class="samples">{''.join(failure_cards) or '<p>没有失败样本。</p>'}</div></section>
<footer><p>本报告不使用失败样本补齐任何结论。</p></footer></main></body></html>"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report_html, encoding="utf-8")
    return output_path


def export_complete_market_analysis_html(keyword, saved_report, output_path):
    if not isinstance(keyword, str) or not keyword.strip():
        raise ValueError(f"keyword must be non-empty text: actual={keyword!r}")
    if not isinstance(saved_report, dict):
        raise ValueError(f"saved_report must be an object: actual={saved_report!r}")
    analysis = saved_report.get("analysis")
    if not isinstance(analysis, dict):
        raise ValueError("saved_report.analysis must be an object")
    report = analysis.get("report")
    if not isinstance(report, dict):
        raise ValueError("saved_report.analysis.report must be an object")
    output_path = Path(output_path)
    if output_path.suffix.casefold() != ".html":
        raise ValueError(f"HTML output path must end with .html: actual={output_path}")

    section_labels = (
        ("executive_summary", "核心结论"),
        ("market_structure", "市场结构"),
        ("title_and_demand", "标题与需求"),
        ("price_and_competition", "价格与竞争"),
        ("visual_analysis", "主图视觉"),
        ("opportunities_and_risks", "机会与风险"),
        ("action_plan", "行动建议"),
    )
    sections = []
    for section_key, section_label in section_labels:
        cards = []
        for item in report.get(section_key) or []:
            if not isinstance(item, dict):
                continue
            evidence_ids = "、".join(
                escape(str(item_id)) for item_id in item.get("evidence_item_ids") or []
            ) or "当前结论未绑定单品"
            cards.append(
                '<article class="insight-card">'
                f'<h3>{escape(str(item.get("conclusion") or "未提供结论"))}</h3>'
                f'<p><strong>证据：</strong>{escape(str(item.get("evidence") or "未提供"))}</p>'
                f'<p><strong>证据商品：</strong>{evidence_ids}</p>'
                f'<p><strong>适用范围：</strong>{escape(str(item.get("scope") or "未说明"))}</p>'
                f'<p class="action"><strong>下一步：</strong>{escape(str(item.get("next_action") or "未提供"))}</p>'
                '</article>'
            )
        sections.append(
            f'<section><h2>{escape(section_label)}</h2><div class="insight-grid">'
            f'{"".join(cards) or "<p>本节没有可验证结论。</p>"}</div></section>'
        )

    statistics = analysis.get("statistics") or {}
    price = statistics.get("price") or {}
    vision = analysis.get("vision") or {}
    vision_notice = str(vision.get("notice") or "").strip()
    vision_status = str(vision.get("status") or "").strip()
    notice_html = ""
    if vision_notice:
        notice_html = (
            '<aside class="notice">'
            f'<strong>{escape(vision_notice)}</strong>'
            '<span>文字类市场分析已经完成；本次报告没有把未分析的图片内容冒充结论。</span>'
            '</aside>'
        )
    evidence = analysis.get("evidence") or {}
    report_html = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(keyword.strip())}｜完整市场分析</title>
<style>
:root{{--ink:#17332a;--muted:#65726c;--paper:#f3f0e8;--card:#fffdf8;--line:#d8d6cc;--green:#1d4b36;--orange:#e87932}}*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font-family:"Microsoft YaHei",system-ui,sans-serif;line-height:1.65}}main{{width:min(1120px,calc(100% - 30px));margin:28px auto 60px}}header{{padding:32px;border-radius:20px;color:#fff;background:linear-gradient(135deg,#153526,#2c6448)}}h1{{margin:5px 0 8px}}section{{margin-top:16px;padding:22px;border:1px solid var(--line);border-radius:16px;background:var(--card)}}.meta,.stats,.insight-grid{{display:grid;gap:10px}}.meta{{grid-template-columns:repeat(4,1fr);margin-top:20px}}.meta div,.stats article,.insight-card{{padding:14px;border:1px solid var(--line);border-radius:11px;background:#fff}}.meta span,.stats span{{display:block;color:var(--muted);font-size:12px}}.meta strong,.stats strong{{font-size:17px}}.stats{{grid-template-columns:repeat(4,1fr)}}.insight-grid{{grid-template-columns:repeat(2,1fr)}}.insight-card h3{{margin:0 0 8px;font-size:16px}}.insight-card p{{margin:6px 0;color:#526159;font-size:13px}}.insight-card .action{{padding-top:7px;border-top:1px dashed var(--line);color:var(--green)}}.notice{{display:flex;gap:12px;align-items:center;margin-top:16px;padding:15px 18px;border-left:5px solid var(--orange);border-radius:8px;background:#fff0e4}}.notice span{{color:#6e5746;font-size:13px}}footer{{margin-top:18px;color:var(--muted);text-align:center;font-size:12px}}@media(max-width:760px){{.meta,.stats,.insight-grid{{grid-template-columns:1fr 1fr}}}}@media(max-width:520px){{.meta,.stats,.insight-grid{{grid-template-columns:1fr}}}}@media print{{@page{{size:A4;margin:14mm}}body{{background:#fff}}main{{width:100%;margin:0}}section,.insight-card{{break-inside:avoid}}}}
</style></head><body><main>
<header><div>淘宝选品与竞品情报操作台</div><h1>{escape(keyword.strip())}｜完整市场分析</h1><p>基于当前已保存搜索快照的全部商品文字数据与代表性主图样本生成。</p><div class="meta"><div><span>快照</span><strong>{escape(str(saved_report.get("snapshot_id") or evidence.get("snapshot_id") or "—"))}</strong></div><div><span>商品数</span><strong>{escape(str(evidence.get("product_count") or statistics.get("sample_count") or 0))}</strong></div><div><span>模型</span><strong>{escape(str(saved_report.get("model_name") or "—"))}</strong></div><div><span>生成时间</span><strong>{escape(str(saved_report.get("generated_at") or "—"))}</strong></div></div></header>
{notice_html}
<section><h2>程序统计</h2><div class="stats"><article><span>样本数</span><strong>{escape(str(statistics.get("sample_count") or 0))}</strong></article><article><span>店铺数</span><strong>{escape(str(statistics.get("store_count") or 0))}</strong></article><article><span>最低展示价</span><strong>¥{escape(str(price.get("minimum") if price.get("minimum") is not None else "—"))}</strong></article><article><span>视觉状态</span><strong>{escape(vision_notice or vision_status or "—")}</strong></article></div></section>
{"".join(sections)}
<footer>方法版本 {escape(str(saved_report.get("method_version") or analysis.get("method_version") or "—"))} · AI 结论与程序事实分开展示</footer>
</main></body></html>"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report_html, encoding="utf-8")
    return output_path
