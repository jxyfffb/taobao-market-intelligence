from contextlib import closing
from datetime import datetime
from pathlib import Path
import os
import socket
import sqlite3
import sys
import threading
from typing import Literal
from urllib.parse import parse_qs, urlparse
from uuid import uuid4
import webbrowser

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
import httpx
from pydantic import BaseModel
import uvicorn

from src import PRODUCT_KEY, PRODUCT_NAME, PRODUCT_VERSION
from src.ai_client import (
    DEFAULT_AI_PRESET_ID,
    list_ai_provider_presets,
    read_ai_settings,
    resolve_ai_provider,
    save_ai_settings,
    test_ai_connection,
)
from src.collector import (
    archive_and_save_search_result,
    capture_selected_sku_price,
    run_product_detail,
    run_search_products,
    scan_product_sku_dimensions,
    validate_product_detail_url,
)
from src.browser_search_collector import (
    clear_collector_login_profile,
    capture_next_search_page,
    capture_product_images,
    capture_search_page,
    capture_shop_listing,
    open_collector_account_browser,
    validate_shop_url,
)
from src.database import (
    append_search_snapshot_page,
    compare_search_snapshots,
    connect_database,
    delete_competitor_record,
    delete_monitor_task,
    finish_monitor_run,
    get_competitor_record,
    list_competitor_records,
    list_product_snapshots,
    list_monitor_runs,
    list_monitor_tasks,
    list_search_snapshots,
    list_search_raw_source_refs,
    list_shop_snapshots,
    read_monitor_settings,
    read_search_snapshot,
    resolve_application_data_directory,
    save_monitor_settings,
    save_search_snapshot,
    save_product_capture,
    save_shop_snapshot,
    start_monitor_run,
    upsert_competitor_record,
    upsert_monitor_task,
)
from src.buyer_links import buyer_urls_from_raw_sources
from src.monitoring import (
    MonitorRunLock,
    install_windows_schedule,
    remove_windows_schedule,
)
from src.monitor_changes import (
    summarize_competitor_changes,
    summarize_keyword_changes,
    summarize_shop_changes,
)
from src.market_analysis import calculate_price_payment_distribution
from src.competitor_intelligence import build_competitor_history
try:  # 商业版：完整离线激活
    from src.license_client import (
        LicenseError,
        activate_license,
        get_license_status,
        redeem_license,
    )
except ImportError:  # 开源社区版：授权模块不随仓库发布，使用内置免激活实现
    from src.licensing import (
        LicenseError,
        activate_license,
        get_license_status,
        redeem_license,
    )
from src.reports import (
    XLSX_MEDIA_TYPE,
    export_competitor_package_zip,
    export_search_snapshot_xlsx,
)
from src.product_link_resolver import resolve_product_link


LOOPBACK_HOST = "127.0.0.1"
APPLICATION_PORT = 8765
APPLICATION_PORT_CANDIDATES = (8765, 18765, 28765, 38765, 48765)
APPLICATION_URL = f"http://{LOOPBACK_HOST}:{APPLICATION_PORT}/"
INDEX_PATH = Path(__file__).resolve().parent / "static" / "index.html"
STATIC_DIRECTORY = INDEX_PATH.parent
MAX_KEYWORD_LENGTH = 100
LEGACY_ALL_RESULTS_COUNT = 30
MAX_PRODUCT_IMAGE_BYTES = 12 * 1024 * 1024
PRODUCT_IMAGE_HOST_SUFFIXES = ("alicdn.com", "taobaocdn.com")
INVALID_PRODUCT_TITLES = {"参数", "商品参数", "商品详情", "详情"}
INVALID_SHOP_NAMES = {"免费开店", "店铺", "进入店铺", "联系客服", "客服"}


class ApplicationStartupError(RuntimeError):
    """A startup failure that is safe to show directly to an end user."""

if not INDEX_PATH.is_file():
    raise RuntimeError(f"Homepage file not found: {INDEX_PATH}")

application = FastAPI(title=PRODUCT_NAME, version=PRODUCT_VERSION)
application.state.application_data_directory = None
application.mount("/static", StaticFiles(directory=STATIC_DIRECTORY), name="static")


class ProjectCreateRequest(BaseModel):
    keyword: str


class SearchCreateRequest(BaseModel):
    result_count: Literal[10, 20, 30] | None = None


class AiSettingsRequest(BaseModel):
    preset_id: str | None = None
    base_url: str | None = None
    model: str | None = None
    text_model: str | None = None
    vision_model: str | None = None
    api_key: str


class CompetitorPrepareRequest(BaseModel):
    product_url: str


class SkuOptionRequest(BaseModel):
    dimension: str
    value: str
    index: int


class CompetitorSkuCaptureRequest(BaseModel):
    selected_options: list[SkuOptionRequest]


class MonitorScheduleRequest(BaseModel):
    enabled: bool
    run_time: str


class KeywordMonitorRequest(BaseModel):
    page_count: Literal[1, 2, 3] = 1


class CompetitorMonitorRequest(BaseModel):
    product_url: str
    item_id: str | None = None
    label: str | None = None


class ShopMonitorRequest(BaseModel):
    shop_url: str
    shop_name: str | None = None


class LicenseCodeRequest(BaseModel):
    code: str


def _development_license_bypass_enabled():
    if bool(getattr(sys, "frozen", False)):
        return False
    try:
        from src.development_entitlement import is_development_license_bypass_enabled
    except ImportError:  # 开源版没有开发绕过模块
        return False

    return is_development_license_bypass_enabled()


def _license_status():
    status = get_license_status()
    if _development_license_bypass_enabled():
        return {
            **status,
            "can_use": True,
            "status": "development_bypass",
            "message": "源码开发绕过已显式启用；打包版本会强制验签。",
        }
    return status


def _require_entitlement(capability):
    status = _license_status()
    if not status.get("can_use"):
        raise HTTPException(
            status_code=403,
            detail={
                "code": "license_required",
                "message": status.get("message") or "请先激活软件。",
                "capability": capability,
                "license_status": status.get("status"),
            },
        )
    return status


@application.get("/api/health")
def health_status():
    return {
        "product_key": PRODUCT_KEY,
        "product_name": PRODUCT_NAME,
        "version": PRODUCT_VERSION,
    }


class RevealFolderRequest(BaseModel):
    kind: Literal["exports", "downloads"] = "exports"


def _reveal_target_directory(kind):
    if kind == "downloads":
        downloads_directory = Path.home() / "Downloads"
        return downloads_directory if downloads_directory.is_dir() else Path.home()
    configured_data_directory = application.state.application_data_directory
    data_directory = (
        Path(configured_data_directory)
        if configured_data_directory is not None
        else resolve_application_data_directory()
    )
    exports_directory = data_directory / "exports"
    exports_directory.mkdir(parents=True, exist_ok=True)
    return exports_directory


@application.post("/api/system/reveal-folder")
def reveal_folder(request: RevealFolderRequest):
    """在本机文件管理器中打开导出目录或下载目录。"""

    directory = _reveal_target_directory(request.kind)
    if os.name != "nt":
        raise HTTPException(
            status_code=501,
            detail={"code": "unsupported_platform", "message": "当前仅支持在 Windows 上打开文件夹。"},
        )
    try:
        os.startfile(str(directory))  # noqa: S606 - 打开本机目录，路径由服务端自行计算
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail={"code": "reveal_failed", "message": f"无法打开文件夹：{exc}"},
        ) from exc
    return {"opened": True, "path": str(directory)}


@application.get("/api/license/status")
def license_status():
    return _license_status()


@application.post("/api/license/activate")
def activate_product_license(request: LicenseCodeRequest):
    try:
        return activate_license(request.code)
    except LicenseError as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc


@application.post("/api/license/redeem")
def redeem_product_license(request: LicenseCodeRequest):
    try:
        return redeem_license(request.code)
    except LicenseError as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc


@application.get("/", response_class=FileResponse)
def homepage():
    return FileResponse(INDEX_PATH, media_type="text/html; charset=utf-8")


def validate_product_image_url(received_url):
    parsed_url = urlparse(received_url)
    hostname = (parsed_url.hostname or "").casefold()
    if parsed_url.scheme not in ("http", "https") or not hostname:
        raise ValueError(f"商品主图地址无效：{received_url!r}")
    if not any(
        hostname == suffix or hostname.endswith(f".{suffix}")
        for suffix in PRODUCT_IMAGE_HOST_SUFFIXES
    ):
        raise ValueError(f"商品主图域名不受支持：{hostname!r}")
    return received_url


def product_image_filename(item_id, content_type):
    safe_item_id = "".join(
        character for character in str(item_id or "") if character.isalnum()
    )[:40] or "product"
    extension = {
        "image/avif": "avif",
        "image/gif": "gif",
        "image/png": "png",
        "image/webp": "webp",
    }.get(content_type.casefold(), "jpg")
    return f"taobao-main-image-{safe_item_id}.{extension}"


def fetch_product_image_payload(image_url: str):
    try:
        validated_url = validate_product_image_url(image_url)
        image_response = httpx.get(
            validated_url,
            follow_redirects=True,
            timeout=15,
        )
        image_response.raise_for_status()
        validate_product_image_url(str(image_response.url))
    except ValueError as exc:
        raise ValueError(str(exc)) from exc
    except httpx.HTTPError as exc:
        raise RuntimeError("商品图片读取失败，请稍后重试") from exc

    content_type = image_response.headers.get("content-type", "").split(";", 1)[0].strip()
    if not content_type.casefold().startswith("image/"):
        raise RuntimeError("商品图片地址没有返回图片内容")
    if len(image_response.content) > MAX_PRODUCT_IMAGE_BYTES:
        raise RuntimeError("商品图片文件过大，无法保存")
    return image_response.content, content_type


@application.get("/api/product-image")
def download_product_image(image_url: str, item_id: str = "product"):
    try:
        image_content, content_type = fetch_product_image_payload(image_url)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_product_image_url", "message": str(exc)},
        ) from exc
    except RuntimeError as exc:
        message = str(exc)
        code = (
            "product_image_type_invalid"
            if "没有返回图片内容" in message
            else "product_image_too_large"
            if "文件过大" in message
            else "product_image_download_failed"
        )
        raise HTTPException(
            status_code=413 if code == "product_image_too_large" else 502,
            detail={"code": code, "message": message},
        ) from exc

    filename = product_image_filename(item_id, content_type)
    return Response(
        content=image_content,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@application.put("/api/settings/ai")
def update_ai_settings(request: AiSettingsRequest):
    configured_data_directory = application.state.application_data_directory
    application_data_directory = (
        Path(configured_data_directory)
        if configured_data_directory is not None
        else resolve_application_data_directory()
    )
    try:
        base_url, model, preset_id = resolve_ai_provider(
            request.preset_id,
            request.base_url,
            request.model or request.vision_model or request.text_model,
        )
        return save_ai_settings(
            application_data_directory,
            base_url,
            model,
            None,
            request.api_key,
            preset_id=preset_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_ai_settings",
                "message": str(exc),
            },
        ) from exc


@application.get("/api/settings/ai")
def current_ai_settings():
    configured_data_directory = application.state.application_data_directory
    application_data_directory = (
        Path(configured_data_directory)
        if configured_data_directory is not None
        else resolve_application_data_directory()
    )
    try:
        settings = read_ai_settings(application_data_directory)
    except FileNotFoundError:
        return Response(status_code=204)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "ai_settings_invalid", "message": str(exc)},
        ) from exc
    return {
        "base_url": settings["base_url"],
        "model": settings["model"],
        "preset_id": settings.get("preset_id"),
        "api_key_configured": True,
        "capabilities": settings.get("capabilities"),
    }


@application.get("/api/settings/ai/presets")
def ai_provider_presets():
    return {
        "default_preset_id": DEFAULT_AI_PRESET_ID,
        "presets": list_ai_provider_presets(),
    }


@application.post("/api/settings/ai/test")
def verify_ai_connection():
    _require_entitlement("ai")
    configured_data_directory = application.state.application_data_directory
    application_data_directory = (
        Path(configured_data_directory)
        if configured_data_directory is not None
        else resolve_application_data_directory()
    )
    try:
        return test_ai_connection(application_data_directory)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "ai_settings_missing",
                "message": "请先保存模型设置",
            },
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "code": "ai_connection_failed",
                "message": str(exc),
            },
        ) from exc


def normalize_keyword(received_keyword):
    display_keyword = " ".join(received_keyword.split())
    if not display_keyword:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "keyword_required",
                "message": "关键词不能为空",
                "value": received_keyword,
            },
        )
    if len(display_keyword) > MAX_KEYWORD_LENGTH:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "keyword_too_long",
                "message": f"关键词最多 {MAX_KEYWORD_LENGTH} 个字符",
                "value": received_keyword,
            },
        )
    return display_keyword, display_keyword.casefold()


def project_response(project_row):
    return {
        "id": project_row["id"],
        "keyword": project_row["keyword"],
        "normalized_keyword": project_row["normalized_keyword"],
        "created_at": project_row["created_at"],
        "updated_at": project_row["updated_at"],
    }


def raise_search_capture_http_error(error):
    error_text = str(error).casefold()
    login_required = any(
        marker in error_text
        for marker in ("未登录", "需要登录", "请先登录", "login.taobao")
    )
    if login_required:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "taobao_login_required",
                "message": (
                    "淘宝采集尚未登录。请先在已打开的淘宝登录页面完成扫码登录，"
                    "再重新搜索。"
                ),
            },
        ) from error
    raise HTTPException(
        status_code=502,
        detail={
            "code": "taobao_search_failed",
            "message": "淘宝搜索暂时没有完成，请确认采集窗口正常后重试。",
        },
    ) from error


def raise_browser_search_gate(capture):
    status = capture.get("status")
    if status == "login_required":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "taobao_browser_login_required",
                "message": capture.get("message") or "请先完成淘宝扫码登录后重新搜索。",
            },
        )
    if status == "blocked":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "taobao_browser_verification_required",
                "message": capture.get("message") or "请先在采集浏览器完成安全验证后重新搜索。",
            },
        )


def save_browser_search_capture(
    application_data_directory,
    project_id,
    keyword,
    request,
    capture,
):
    all_products = list(capture.get("products") or [])
    saved_products = (
        all_products
        if request.result_count is None
        else all_products[: request.result_count]
    )
    requested_result_count = request.result_count or LEGACY_ALL_RESULTS_COUNT
    with closing(connect_database(application_data_directory)) as connection:
        snapshot_id = save_search_snapshot(
            connection,
            project_id,
            keyword,
            "all",
            requested_result_count,
            capture["captured_at"],
            capture["raw_source_ref"],
            saved_products,
            has_next_page=capture.get("has_next_page", False),
            read_result_count=len(all_products),
        )
        snapshot = read_search_snapshot(connection, snapshot_id, project_id)
    snapshot.update(
        {
            "capture_source": "browser",
            "read_result_count": len(all_products),
            "duplicate_result_count": 0,
            "added_result_count": len(saved_products),
            "collection_message": f"第一页读取 {len(all_products)} 条，已保存 {len(saved_products)} 条完整市场数据。",
        }
    )
    return snapshot


def search_snapshot_response(snapshot):
    response = dict(snapshot)
    results = [dict(result) for result in response.get("results") or []]
    buyer_urls = buyer_urls_from_raw_sources(
        response.get("raw_source_refs") or [response.get("raw_source_ref")],
        [result.get("item_id") for result in results],
    )
    for result in results:
        result["buyer_url"] = buyer_urls.get(str(result.get("item_id"))) or result.get("product_url")
    response["results"] = results
    response["price_distribution"] = calculate_price_payment_distribution(
        results
    )
    return response


def _buyer_urls_for_items(connection, item_ids):
    return buyer_urls_from_raw_sources(
        list_search_raw_source_refs(connection),
        item_ids,
    )


@application.post("/api/projects", status_code=201)
def create_project(request: ProjectCreateRequest):
    display_keyword, normalized_keyword = normalize_keyword(request.keyword)
    application_data_directory = application.state.application_data_directory

    with closing(connect_database(application_data_directory)) as connection:
        try:
            cursor = connection.execute(
                """
                INSERT INTO market_projects (keyword, normalized_keyword)
                VALUES (?, ?)
                """,
                (display_keyword, normalized_keyword),
            )
            connection.commit()
        except sqlite3.IntegrityError as exc:
            if "market_projects.normalized_keyword" not in str(exc):
                raise
            project_row = connection.execute(
                "SELECT * FROM market_projects WHERE normalized_keyword = ?",
                (normalized_keyword,),
            ).fetchone()
        else:
            project_row = connection.execute(
                "SELECT * FROM market_projects WHERE id = ?",
                (cursor.lastrowid,),
            ).fetchone()
    if project_row is None:
        raise RuntimeError(
            "Created or reused project not found: "
            f"normalized_keyword={normalized_keyword!r}"
        )
    return project_response(project_row)


@application.get("/api/projects")
def list_projects():
    application_data_directory = application.state.application_data_directory
    with closing(connect_database(application_data_directory)) as connection:
        project_rows = connection.execute(
            "SELECT * FROM market_projects ORDER BY updated_at DESC, id DESC"
        ).fetchall()
    return {"projects": [project_response(project_row) for project_row in project_rows]}


@application.get("/api/projects/{project_id}")
def reopen_project(project_id: int):
    application_data_directory = application.state.application_data_directory
    with closing(connect_database(application_data_directory)) as connection:
        project_row = connection.execute(
            "SELECT * FROM market_projects WHERE id = ?",
            (project_id,),
        ).fetchone()
    if project_row is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "project_not_found",
                "message": "项目不存在",
                "value": project_id,
            },
        )
    return project_response(project_row)


@application.post("/api/projects/{project_id}/searches", status_code=201)
def create_search_snapshot(project_id: int, request: SearchCreateRequest):
    _require_entitlement("capture")
    configured_data_directory = application.state.application_data_directory
    application_data_directory = (
        Path(configured_data_directory)
        if configured_data_directory is not None
        else resolve_application_data_directory()
    )
    with closing(connect_database(application_data_directory)) as connection:
        project_row = connection.execute(
            "SELECT keyword FROM market_projects WHERE id = ?",
            (project_id,),
        ).fetchone()
    if project_row is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "project_not_found",
                "message": "项目不存在",
                "value": project_id,
            },
        )

    capture_id = uuid4().hex
    captured_at = datetime.now().astimezone().isoformat(timespec="microseconds")
    work_directory = application_data_directory / "work" / "searches"
    request_path = work_directory / f"{capture_id}-request.json"
    source_result_path = work_directory / f"{capture_id}-result.json"
    browser_raw_archive_path = (
        application_data_directory
        / "raw"
        / "searches"
        / str(project_id)
        / f"{capture_id}-browser-page-1.json"
    )
    native_raw_archive_path = browser_raw_archive_path.with_name(
        f"{capture_id}-native-fallback.json"
    )

    try:
        browser_capture = capture_search_page(
            application_data_directory,
            project_row["keyword"],
            1,
            browser_raw_archive_path,
        )
    except (OSError, RuntimeError, ValueError):
        browser_capture = None

    if browser_capture is not None:
        raise_browser_search_gate(browser_capture)
    if browser_capture is not None and browser_capture.get("status") == "success":
        saved_snapshot = save_browser_search_capture(
            application_data_directory,
            project_id,
            project_row["keyword"],
            request,
            browser_capture,
        )
    else:
        try:
            run_search_products(project_row["keyword"], request_path, source_result_path)
        except (FileNotFoundError, OSError, RuntimeError, ValueError) as exc:
            raise_search_capture_http_error(exc)
        save_all_results = request.result_count is None
        requested_result_count = request.result_count or LEGACY_ALL_RESULTS_COUNT
        native_snapshot = archive_and_save_search_result(
            application_data_directory,
            project_id,
            source_result_path,
            native_raw_archive_path,
            requested_result_count,
            captured_at,
            save_all_results=save_all_results,
        )
        with closing(connect_database(application_data_directory)) as connection:
            saved_snapshot = read_search_snapshot(
                connection,
                native_snapshot["snapshot_id"],
                project_id,
            )
        saved_snapshot.update(
            {
                "capture_source": "taobao_native_fallback",
                "read_result_count": saved_snapshot["result_count"],
                "duplicate_result_count": 0,
                "added_result_count": saved_snapshot["result_count"],
                "collection_message": (
                    f"浏览器完整采集暂时不可用，已保存 {saved_snapshot['result_count']} 条基础数据。"
                    "完成浏览器验证后重新搜索，可获得付款、产地、促销和物流字段。"
                ),
            }
        )

    snapshot_captured_at = saved_snapshot["captured_at"]
    with closing(connect_database(application_data_directory)) as connection:
        connection.execute(
            "UPDATE market_projects SET updated_at = ? WHERE id = ?",
            (snapshot_captured_at, project_id),
        )
        connection.commit()
    request_path.unlink(missing_ok=True)
    source_result_path.unlink(missing_ok=True)
    return search_snapshot_response(saved_snapshot)


@application.get("/api/projects/{project_id}/searches")
def search_history(project_id: int):
    application_data_directory = application.state.application_data_directory
    with closing(connect_database(application_data_directory)) as connection:
        try:
            snapshots = list_search_snapshots(connection, project_id)
        except LookupError as exc:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "project_not_found",
                    "message": "项目不存在",
                    "value": project_id,
                },
            ) from exc
    return {"snapshots": snapshots}


@application.get("/api/projects/{project_id}/searches/{snapshot_id}")
def reopen_search_snapshot(project_id: int, snapshot_id: int):
    application_data_directory = application.state.application_data_directory
    with closing(connect_database(application_data_directory)) as connection:
        try:
            return search_snapshot_response(
                read_search_snapshot(connection, snapshot_id, project_id)
            )
        except LookupError as exc:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "snapshot_not_found",
                    "message": "搜索快照不存在或不属于当前项目",
                    "value": snapshot_id,
                },
            ) from exc


@application.post("/api/projects/{project_id}/searches/{snapshot_id}/next-page")
def collect_next_search_page(project_id: int, snapshot_id: int):
    _require_entitlement("capture")
    configured_data_directory = application.state.application_data_directory
    application_data_directory = (
        Path(configured_data_directory)
        if configured_data_directory is not None
        else resolve_application_data_directory()
    )
    with closing(connect_database(application_data_directory)) as connection:
        project_row = connection.execute(
            "SELECT keyword FROM market_projects WHERE id = ?",
            (project_id,),
        ).fetchone()
        try:
            snapshot = read_search_snapshot(connection, snapshot_id, project_id)
        except LookupError as exc:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "snapshot_not_found",
                    "message": "搜索记录不存在或不属于当前关键词",
                    "value": snapshot_id,
                },
            ) from exc
    if project_row is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "project_not_found", "message": "关键词不存在"},
        )
    if not snapshot["can_collect_next_page"]:
        return {
            "status": "exhausted",
            "message": "已经到淘宝搜索结果的最后一页。",
            "added_result_count": 0,
            "snapshot": search_snapshot_response(snapshot),
        }

    page_number = snapshot["next_page_number"]
    capture_id = uuid4().hex
    raw_archive_path = (
        application_data_directory
        / "raw"
        / "searches"
        / str(project_id)
        / f"{capture_id}-page-{page_number}.json"
    )
    try:
        capture = capture_next_search_page(
            application_data_directory,
            project_row["keyword"],
            page_number,
            raw_archive_path,
        )
    except (RuntimeError, OSError) as exc:
        return {
            "status": "failed",
            "message": str(exc),
            "added_result_count": 0,
            "snapshot": search_snapshot_response(snapshot),
        }

    if capture["status"] in {"login_required", "blocked", "failed"}:
        return {
            "status": capture["status"],
            "message": capture["message"],
            "added_result_count": 0,
            "snapshot": search_snapshot_response(snapshot),
        }

    status = capture["status"]
    with closing(connect_database(application_data_directory)) as connection:
        try:
            appended = append_search_snapshot_page(
                connection,
                project_id,
                snapshot_id,
                page_number,
                capture["captured_at"],
                capture["raw_source_ref"],
                capture.get("products") or [],
                has_next_page=capture.get("has_next_page", False),
                status=status,
            )
            updated_snapshot = read_search_snapshot(connection, snapshot_id, project_id)
        except (LookupError, ValueError) as exc:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "next_page_conflict",
                    "message": "搜索记录已经变化，请刷新后再试。",
                },
            ) from exc

    if status == "exhausted":
        message = "已经到淘宝搜索结果的最后一页。"
    elif appended["added_result_count"]:
        message = (
            f"第{page_number}页采集完成：本页读取 {appended['read_result_count']} 条，"
            f"重复 {appended['duplicate_result_count']} 条，"
            f"新增 {appended['added_result_count']} 条。"
        )
    else:
        message = (
            f"第{page_number}页采集完成：本页读取 {appended['read_result_count']} 条，"
            f"全部与已保存商品重复，没有新增。"
        )
    return {
        "status": status,
        "message": message,
        "read_result_count": appended["read_result_count"],
        "duplicate_result_count": appended["duplicate_result_count"],
        "added_result_count": appended["added_result_count"],
        "snapshot": search_snapshot_response(updated_snapshot),
    }


@application.get("/api/projects/{project_id}/search-diff")
def search_snapshot_diff(
    project_id: int,
    older_snapshot_id: int,
    newer_snapshot_id: int,
):
    application_data_directory = application.state.application_data_directory
    with closing(connect_database(application_data_directory)) as connection:
        try:
            return compare_search_snapshots(
                connection,
                project_id,
                older_snapshot_id,
                newer_snapshot_id,
            )
        except LookupError as exc:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "snapshot_not_found",
                    "message": "对比快照不存在或不属于当前项目",
                    "value": {
                        "older_snapshot_id": older_snapshot_id,
                        "newer_snapshot_id": newer_snapshot_id,
                    },
                },
            ) from exc


@application.get("/api/projects/{project_id}/searches/{snapshot_id}/export.xlsx")
def export_search_snapshot(project_id: int, snapshot_id: int):
    configured_data_directory = application.state.application_data_directory
    application_data_directory = (
        Path(configured_data_directory)
        if configured_data_directory is not None
        else resolve_application_data_directory()
    )
    with closing(connect_database(application_data_directory)) as connection:
        project_row = connection.execute(
            "SELECT keyword FROM market_projects WHERE id = ?",
            (project_id,),
        ).fetchone()
        if project_row is None:
            raise HTTPException(
                status_code=404,
                detail={"code": "project_not_found", "message": "项目不存在", "value": project_id},
            )
        try:
            snapshot = read_search_snapshot(connection, snapshot_id, project_id)
        except LookupError as exc:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "snapshot_not_found",
                    "message": "搜索快照不存在或不属于当前项目",
                    "value": snapshot_id,
                },
            ) from exc

    output_path = application_data_directory / "exports" / f"search-snapshot-{snapshot_id}.xlsx"
    try:
        export_search_snapshot_xlsx(
            project_row["keyword"],
            snapshot,
            output_path,
            image_fetcher=fetch_product_image_payload,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "empty_snapshot",
                "message": "空快照不能导出",
                "value": snapshot_id,
            },
        ) from exc
    return FileResponse(
        output_path,
        media_type=XLSX_MEDIA_TYPE,
        filename=f"{project_row['keyword']}-搜索快照-{snapshot_id}.xlsx",
    )


def _competitor_data_directory():
    configured_data_directory = application.state.application_data_directory
    return (
        Path(configured_data_directory)
        if configured_data_directory is not None
        else resolve_application_data_directory()
    )


@application.post("/api/collector/account-browser")
def open_collector_account():
    _require_entitlement("capture")
    try:
        return open_collector_account_browser(_competitor_data_directory())
    except RuntimeError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "collector_browser_unavailable", "message": str(exc)},
        ) from exc


@application.delete("/api/collector/login-profile")
def clear_collector_login():
    _require_entitlement("capture")
    try:
        return clear_collector_login_profile(_competitor_data_directory())
    except RuntimeError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "collector_browser_still_open", "message": str(exc)},
        ) from exc


def _require_competitor_project(application_data_directory, project_id):
    with closing(connect_database(application_data_directory)) as connection:
        project_row = connection.execute(
            "SELECT keyword FROM market_projects WHERE id = ?",
            (project_id,),
        ).fetchone()
    if project_row is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "project_not_found",
                "message": "项目不存在",
                "value": project_id,
            },
        )
    return project_row["keyword"]


def _latest_search_product_evidence(application_data_directory, project_id, item_id):
    with closing(connect_database(application_data_directory)) as connection:
        row = connection.execute(
            """
            SELECT
                search_results.title,
                search_results.shop_name,
                search_results.image_url,
                search_snapshots.id AS snapshot_id,
                search_snapshots.captured_at
            FROM search_results
            JOIN search_snapshots ON search_snapshots.id = search_results.snapshot_id
            JOIN products ON products.id = search_results.product_id
            WHERE search_snapshots.project_id = ? AND products.item_id = ?
            ORDER BY search_snapshots.captured_at DESC, search_snapshots.id DESC
            LIMIT 1
            """,
            (project_id, item_id),
        ).fetchone()
    return dict(row) if row is not None else None


def _usable_product_title(value):
    title = str(value or "").strip()
    return bool(title and title not in INVALID_PRODUCT_TITLES and len(title) >= 4)


def _usable_shop_name(value):
    shop_name = str(value or "").strip()
    return bool(shop_name and shop_name not in INVALID_SHOP_NAMES)


def _clean_browser_page_title(value):
    title = " ".join(str(value or "").split()).strip()
    for suffix in ("-tmall.com天猫", "-淘宝网", "-天猫", "_淘宝网"):
        if title.endswith(suffix):
            title = title[: -len(suffix)].strip()
    return title


def _latest_valid_product_evidence(application_data_directory, item_id):
    with closing(connect_database(application_data_directory)) as connection:
        rows = connection.execute(
            """
            SELECT product_snapshots.title, product_snapshots.shop_name,
                   product_snapshots.main_image_url, product_snapshots.id AS product_snapshot_id,
                   product_snapshots.captured_at
            FROM product_snapshots
            JOIN products ON products.id = product_snapshots.product_id
            WHERE products.item_id = ?
            ORDER BY product_snapshots.captured_at DESC, product_snapshots.id DESC
            """,
            (str(item_id),),
        ).fetchall()
    evidence = {}
    for row in rows:
        if "title" not in evidence and _usable_product_title(row["title"]):
            evidence["title"] = row["title"]
        if "shop_name" not in evidence and _usable_shop_name(row["shop_name"]):
            evidence["shop_name"] = row["shop_name"]
        if "image_url" not in evidence and str(row["main_image_url"] or "").strip():
            evidence["image_url"] = row["main_image_url"]
        if len(evidence) == 3:
            break
    return evidence or None


def _apply_search_product_fallback(
    product_detail,
    search_evidence,
    *,
    source="search_snapshot_fallback",
):
    if not search_evidence:
        return {}
    product = product_detail.setdefault("product", {})
    shop = product_detail.setdefault("shop", {})
    field_sources = {}
    title = str(product.get("page_title") or "").strip()
    if not _usable_product_title(title) and search_evidence.get("title"):
        product["page_title"] = str(search_evidence["title"]).strip()
        field_sources["title"] = source
    shop_name = str(shop.get("name") or "").strip()
    if not _usable_shop_name(shop_name) and search_evidence.get("shop_name"):
        shop["name"] = str(search_evidence["shop_name"]).strip()
        field_sources["shop_name"] = source
    if not str(product.get("main_image_url") or "").strip() and search_evidence.get(
        "image_url"
    ):
        image_url = str(search_evidence["image_url"]).strip()
        product["main_image_url"] = image_url
        product_images = product.setdefault("images", [])
        product_images.insert(
            0,
            {
                "url": image_url,
                "kind": "main",
                "source": "search_snapshot_fallback",
            },
        )
        field_sources["main_image_url"] = source
    return field_sources


def _competitor_capture_paths(application_data_directory, item_id):
    capture_id = uuid4().hex
    request_directory = (
        application_data_directory / "work" / "products" / capture_id
    )
    raw_directory = application_data_directory / "raw" / "products" / item_id
    return {
        "request_directory": request_directory,
        "detail_result_path": raw_directory / f"{capture_id}-detail.json",
        "browser_image_result_path": raw_directory / f"{capture_id}-browser-images.json",
        "sku_catalog_result_path": raw_directory / f"{capture_id}-sku-catalog.json",
        "sku_result_path": raw_directory / f"{capture_id}-sku-dimensions.json",
        "price_result_path": raw_directory / f"{capture_id}-sku-price.json",
        "asset_directory": (
            application_data_directory / "assets" / "products" / item_id / capture_id
        ),
    }


def _merge_browser_product_fields(product_detail, browser_capture):
    fields = browser_capture.get("product_fields") or {}
    product = product_detail.setdefault("product", {})
    shop = product_detail.setdefault("shop", {})
    sales = product_detail.setdefault("sales", {})
    attributes = product_detail.setdefault("attributes", {})
    browser_title = fields.get("title") or browser_capture.get("title")
    if browser_title and not product.get("page_title"):
        product["page_title"] = browser_title
    if fields.get("price_text") and not product.get("visible_price_text"):
        product["visible_price_text"] = fields["price_text"]
    if fields.get("shop_name") and not shop.get("name"):
        shop["name"] = fields["shop_name"]
    if not sales.get("sold_text"):
        sales["sold_text"] = fields.get("sold_text") or fields.get("payment_text")
    browser_services = fields.get("services") or []
    existing_services = product_detail.get("services") or []
    product_detail["services"] = list(dict.fromkeys([*existing_services, *browser_services]))
    if fields.get("attributes_text") and not attributes.get("visible_text"):
        attributes["visible_text"] = fields["attributes_text"]
    return product_detail


def _browser_product_detail(browser_capture, product_url, item_id):
    """Build the product record directly from the logged-in browser capture."""
    fields = browser_capture.get("product_fields") or {}
    images = browser_capture.get("images") or []
    field_title = str(fields.get("title") or "").strip()
    page_title = _clean_browser_page_title(browser_capture.get("title"))
    title = field_title if _usable_product_title(field_title) else page_title
    main_image_url = next(
        (
            str(image.get("url") or "").strip()
            for image in images
            if image.get("kind") == "main" and image.get("url")
        ),
        None,
    )
    return {
        "page_url": product_url,
        "product": {
            "item_id": item_id,
            "page_title": title or f"商品 {item_id}",
            "main_image_url": main_image_url,
            "visible_price_text": fields.get("price_text"),
            "images": images,
        },
        "shop": {
            "name": fields.get("shop_name"),
            "rating_text": None,
            "positive_rate_text": None,
            "shipping_text": None,
            "refund_text": None,
        },
        "sales": {
            "sold_text": fields.get("sold_text") or fields.get("payment_text"),
            "repeat_buyer_text": None,
            "cart_text": None,
        },
        "reviews": {"count_text": None, "preview_text": None},
        "services": fields.get("services") or [],
        "attributes": {"visible_text": fields.get("attributes_text")},
    }


def _archive_product_images(asset_directory, images):
    """Best-effort local image archive; capture success never depends on downloads."""
    asset_directory = Path(asset_directory)
    archived = []
    counters = {"main": 0, "sku": 0, "detail": 0, "review": 0, "gallery": 0}
    if not images:
        return archived
    try:
        client = httpx.Client(
            follow_redirects=True,
            timeout=8,
            headers={"User-Agent": "Mozilla/5.0 TaobaoMarketIntelligence/0.1"},
        )
    except Exception:
        return [{**image, "local_status": "failed", "local_ref": None} for image in images]
    try:
        for image in images[:60]:
            kind = str(image.get("kind") or "gallery")
            counters[kind] = counters.get(kind, 0) + 1
            archived_image = {**image, "sequence": counters[kind]}
            try:
                validated_url = validate_product_image_url(str(image.get("url") or ""))
                response = client.get(validated_url)
                response.raise_for_status()
                validate_product_image_url(str(response.url))
                content_type = response.headers.get("content-type", "").split(";", 1)[0].strip()
                if not content_type.casefold().startswith("image/"):
                    raise ValueError("image response type is invalid")
                if not response.content or len(response.content) > MAX_PRODUCT_IMAGE_BYTES:
                    raise ValueError("image response size is invalid")
                extension = {
                    "image/avif": "avif",
                    "image/gif": "gif",
                    "image/png": "png",
                    "image/webp": "webp",
                }.get(content_type.casefold(), "jpg")
                destination = asset_directory / f"{kind}-{counters[kind]:03d}.{extension}"
                destination.parent.mkdir(parents=True, exist_ok=True)
                partial = destination.parent / f".{destination.name}.{uuid4().hex}.partial"
                partial.write_bytes(response.content)
                os.replace(partial, destination)
                archived_image["local_status"] = "saved"
                archived_image["local_ref"] = str(destination)
            except (ValueError, OSError, httpx.HTTPError):
                archived_image["local_status"] = "failed"
                archived_image["local_ref"] = None
            archived.append(archived_image)
    finally:
        client.close()
    return archived


def _validated_requested_sku_options(dimensions, requested_options):
    if not dimensions:
        raise ValueError("当前页面没有识别到可选 SKU 规格")
    requested = [
        {
            "dimension": option.dimension.strip(),
            "value": option.value.strip(),
            "index": option.index,
        }
        for option in requested_options
    ]
    if len(requested) != len(dimensions):
        raise ValueError(
            "每个 SKU 维度必须且只能选择一项："
            f"expected={len(dimensions)} actual={len(requested)}"
        )
    available_options = {
        (dimension["label"], option["value"], option["index"])
        for dimension in dimensions
        for option in dimension["options"]
    }
    seen_dimensions = set()
    for selection in requested:
        if not selection["dimension"] or not selection["value"]:
            raise ValueError(f"SKU 维度和值不能为空：actual={selection!r}")
        if selection["dimension"] in seen_dimensions:
            raise ValueError(
                f"SKU 维度重复选择：actual={selection['dimension']!r}"
            )
        if (
            selection["dimension"],
            selection["value"],
            selection["index"],
        ) not in available_options:
            raise ValueError(
                "所选 SKU 不在当前页面最新扫描结果中："
                f"actual={selection!r}"
            )
        seen_dimensions.add(selection["dimension"])
    return requested


def _prepare_product_capture(project_id, requested_product_url):
    application_data_directory = _competitor_data_directory()
    if project_id is not None:
        _require_competitor_project(application_data_directory, project_id)
    try:
        resolved_link = resolve_product_link(requested_product_url)
        product_url = resolved_link["resolved_url"]
        item_id = resolved_link["item_id"]
        capture_paths = _competitor_capture_paths(
            application_data_directory,
            item_id,
        )
        search_product_evidence = (
            _latest_search_product_evidence(
                application_data_directory,
                project_id,
                item_id,
            )
            if project_id is not None
            else None
        )
        previous_product_evidence = _latest_valid_product_evidence(
            application_data_directory,
            item_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_competitor_input", "message": str(exc)},
        ) from exc

    try:
        browser_images = capture_product_images(
            application_data_directory,
            product_url,
            item_id,
            capture_paths["browser_image_result_path"],
        )
    except (FileNotFoundError, RuntimeError, OSError) as exc:
        browser_images = {
            "status": "failed",
            "message": f"浏览器图片读取暂未完成：{exc}",
            "images": [],
        }

    if browser_images.get("status") == "login_required":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "taobao_browser_login_required",
                "message": browser_images["message"],
            },
        )

    browser_fields = browser_images.get("product_fields") or {}
    browser_capture_sufficient = bool(
        browser_images.get("status") == "success"
        and browser_images.get("images")
        and (browser_fields.get("title") or browser_images.get("title"))
    )
    if browser_capture_sufficient:
        text_capture_status = "browser_primary"
        text_capture_message = "商品详情已从当前登录的采集浏览器读取。"
        product_detail = _browser_product_detail(browser_images, product_url, item_id)
    else:
        text_capture_status = "success"
        text_capture_message = None
        try:
            product_detail = run_product_detail(
                product_url,
                capture_paths["request_directory"],
                capture_paths["detail_result_path"],
            )
        except (FileNotFoundError, RuntimeError, ValueError) as exc:
            if not browser_images.get("images"):
                error_text = str(exc).casefold()
                login_message = (
                    "淘宝登录状态已失效，请先在采集浏览器或淘宝客户端完成登录，再重新抓取。"
                    if "login.taobao" in error_text or "未登录" in error_text
                    else "商品详情读取暂未完成，请确认淘宝页面可以正常打开后重试。"
                )
                raise HTTPException(
                    status_code=(
                        409 if "login" in error_text or "未登录" in error_text else 502
                    ),
                    detail={"code": "taobao_login_required", "message": login_message},
                ) from exc
            text_capture_status = "browser_fallback"
            text_capture_message = "旧接口读取超时，已保存登录浏览器采集到的完整档案。"
            product_detail = _browser_product_detail(browser_images, product_url, item_id)

    product_detail = _merge_browser_product_fields(product_detail, browser_images)
    fallback_evidence = search_product_evidence or previous_product_evidence
    fallback_field_sources = _apply_search_product_fallback(
        product_detail,
        fallback_evidence,
        source=(
            "search_snapshot_fallback"
            if search_product_evidence
            else "previous_product_snapshot_fallback"
        ),
    )

    browser_sku_catalog = browser_images.get("sku_catalog") or {}
    if browser_sku_catalog.get("dimensions"):
        sku_dimensions = {
            "dimensions": browser_sku_catalog["dimensions"],
            "raw_source_ref": browser_images.get("raw_source_ref"),
            "catalog": {
                **browser_sku_catalog,
                "capture_error": False,
                "raw_source_ref": browser_images.get("raw_source_ref"),
            },
        }
    else:
        try:
            sku_dimensions = scan_product_sku_dimensions(
                capture_paths["request_directory"],
                capture_paths["sku_result_path"],
                item_id=item_id,
                sku_catalog_result_path=capture_paths["sku_catalog_result_path"],
            )
        except (FileNotFoundError, RuntimeError, ValueError):
            sku_dimensions = {
                "dimensions": [],
                "raw_source_ref": None,
                "catalog": {
                    "has_sku": False,
                    "dimensions": [],
                    "message": "规格接口暂未完成读取，可先查看已保存图片。",
                    "capture_error": True,
                    "raw_source_ref": None,
                },
            }

    review_archive = browser_images.get("reviews") or {
        "status": "not_exposed",
        "total_text": None,
        "tags": [],
        "items": [],
    }
    product_reviews = product_detail.setdefault("reviews", {})
    if review_archive.get("total_text"):
        product_reviews["count_text"] = review_archive["total_text"]
    if review_archive.get("items"):
        product_reviews["preview_text"] = "\n".join(
            item["content"] for item in review_archive["items"]
        )

    product_images = []
    seen_image_urls = set()
    browser_product_images = browser_images.get("images") or []
    fallback_main_images = []
    if not any(image.get("kind") == "main" for image in browser_product_images):
        fallback_main_images = [
            image
            for image in (product_detail["product"].get("images") or [])
            if image.get("kind") == "main"
        ][:1]
    for image in [*fallback_main_images, *browser_product_images]:
        image_url = str(image.get("url") or "").strip()
        if not image_url or image_url in seen_image_urls:
            continue
        seen_image_urls.add(image_url)
        product_images.append(
            {
                "url": image_url,
                "kind": str(image.get("kind") or "gallery"),
            }
        )
    if product_images and not product_detail["product"].get("main_image_url"):
        product_detail["product"]["main_image_url"] = next(
            (
                image["url"]
                for image in product_images
                if image.get("kind") == "main"
            ),
            product_images[0]["url"],
        )
    native_sku_catalog = sku_dimensions.get("catalog") or {
        "has_sku": False,
        "dimensions": [],
        "message": None,
        "raw_source_ref": None,
    }
    browser_sku_catalog = browser_images.get("sku_catalog") or {
        "status": "not_exposed",
        "has_sku": False,
        "dimensions": [],
        "source": "browser_page",
    }
    if browser_sku_catalog.get("dimensions"):
        sku_catalog = {
            **browser_sku_catalog,
            "message": "规格来自当前登录商品页；仅保存目录，不自动遍历全部组合价格。",
            "capture_error": False,
            "raw_source_ref": browser_images.get("raw_source_ref"),
        }
    elif native_sku_catalog.get("dimensions"):
        sku_catalog = {**native_sku_catalog, "status": "captured", "source": "native"}
    else:
        sku_catalog = {
            **native_sku_catalog,
            "status": browser_sku_catalog.get("status", "not_exposed"),
            "source": "native",
        }

    questions_archive = browser_images.get("questions") or {
        "status": "not_exposed",
        "total_text": None,
        "items": [],
    }
    videos_archive = browser_images.get("videos") or []
    if application.state.application_data_directory is None:
        product_images = _archive_product_images(
            capture_paths["asset_directory"],
            product_images,
        )
    else:
        sequence_by_kind = {}
        for image in product_images:
            kind = image.get("kind", "gallery")
            sequence_by_kind[kind] = sequence_by_kind.get(kind, 0) + 1
            image["sequence"] = sequence_by_kind[kind]
            image["local_status"] = "not_requested"
            image["local_ref"] = None

    browser_product_fields = browser_images.get("product_fields") or {}
    archive_product_fields = {
        **browser_product_fields,
        "title": product_detail["product"].get("page_title"),
        "price_text": product_detail["product"].get("visible_price_text"),
        "shop_name": product_detail["shop"].get("name"),
        "sold_text": product_detail["sales"].get("sold_text"),
        "services": product_detail.get("services") or [],
        "attributes_text": product_detail["attributes"].get("visible_text"),
        "field_sources": fallback_field_sources,
    }
    archive_product_fields["status"] = "captured"
    coverage = {
        **(browser_images.get("coverage") or {}),
        "basic": "captured",
        "images": "captured" if product_images else "not_exposed",
        "sku": sku_catalog.get("status", "not_exposed"),
        "reviews": review_archive.get("status", "not_exposed"),
        "questions": questions_archive.get("status", "not_exposed"),
        "videos": "captured" if videos_archive else "not_exposed",
        "attributes": (
            "captured"
            if product_detail["attributes"].get("visible_text")
            else "not_exposed"
        ),
    }
    captured_at = datetime.now().astimezone().isoformat(timespec="microseconds")
    saved_detail_source_ref = (
        str(capture_paths["detail_result_path"])
        if text_capture_status == "success"
        else str(browser_images.get("raw_source_ref") or capture_paths["browser_image_result_path"])
    )
    product_archive_record = {
        "product_fields": archive_product_fields,
        "images": product_images,
        "sku_catalog": sku_catalog,
        "reviews": review_archive,
        "questions": questions_archive,
        "videos": videos_archive,
        "coverage": coverage,
        "capture_status": {
            "browser": browser_images.get("status", "failed"),
            "text": text_capture_status,
            "local_images": (
                "saved"
                if any(image.get("local_status") == "saved" for image in product_images)
                else "not_saved"
            ),
        },
        "raw_source_refs": {
            "browser": browser_images.get("raw_source_ref"),
            "detail": (
                str(capture_paths["detail_result_path"])
                if capture_paths["detail_result_path"].is_file()
                else None
            ),
            "sku": sku_catalog.get("raw_source_ref"),
        },
    }
    with closing(connect_database(application_data_directory)) as connection:
        saved = save_product_capture(
            connection,
            product_detail,
            captured_at,
            saved_detail_source_ref,
            archive=product_archive_record,
        )
        competitor_record = upsert_competitor_record(
            connection,
            item_id=item_id,
            source_url=resolved_link["source_url"],
            resolved_url=product_url,
            captured_at=captured_at,
        )
        saved_snapshot = list_product_snapshots(connection, item_id)[0]
    completeness_percent = saved_snapshot["completeness_percent"]
    return {
        **saved,
        "item_id": item_id,
        "competitor_record": competitor_record,
        "source_url": resolved_link["source_url"],
        "page_url": product_url,
        "title": product_detail["product"]["page_title"],
        "shop_name": product_detail["shop"]["name"],
        "visible_price_text": product_detail["product"]["visible_price_text"],
        "product_archive": {
            "title": product_detail["product"]["page_title"],
            "product_fields": archive_product_fields,
            "images": product_images,
            "image_count": len(product_images),
            "detail_image_status": (
                "captured"
                if any(image.get("kind") == "detail" for image in product_images)
                else "not_exposed"
            ),
            "image_capture_status": browser_images.get("status", "failed"),
            "image_capture_message": browser_images.get("message"),
            "image_raw_source_ref": browser_images.get("raw_source_ref"),
            "text_capture_status": text_capture_status,
            "text_capture_message": text_capture_message,
            "reviews": review_archive,
            "sku_catalog": sku_catalog,
            "questions": questions_archive,
            "videos": videos_archive,
            "coverage": coverage,
            "capture_status": product_archive_record["capture_status"],
        },
        "dimensions": sku_dimensions["dimensions"],
        "sku_raw_source_ref": sku_dimensions["raw_source_ref"],
        "capture_status": "waiting_for_sku_selection",
        "completeness_percent": completeness_percent,
        "completeness_status": (
            "complete" if completeness_percent == 100 else "incomplete_saved"
        ),
    }


def _capture_product_sku(
    project_id: int | None,
    item_id: str,
    selected_option_requests,
    search_snapshot_id: int | None = None,
):
    application_data_directory = _competitor_data_directory()
    if project_id is not None:
        _require_competitor_project(application_data_directory, project_id)
    with closing(connect_database(application_data_directory)) as connection:
        snapshots = list_product_snapshots(connection, item_id)
    if not snapshots:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "competitor_snapshot_not_found",
                "message": "尚未读取该商品详情，请先执行规格准备",
                "value": item_id,
            },
        )

    product_url = snapshots[0]["page_url"]
    capture_paths = _competitor_capture_paths(application_data_directory, item_id)
    try:
        product_detail = run_product_detail(
            product_url,
            capture_paths["request_directory"],
            capture_paths["detail_result_path"],
        )
        sku_dimensions = scan_product_sku_dimensions(
            capture_paths["request_directory"],
            capture_paths["sku_result_path"],
        )
        selected_options = _validated_requested_sku_options(
            sku_dimensions["dimensions"],
            selected_option_requests,
        )
        sku_capture = capture_selected_sku_price(
            selected_options,
            product_detail["product"]["visible_price_text"],
            capture_paths["request_directory"],
            capture_paths["price_result_path"],
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_sku_selection", "message": str(exc)},
        ) from exc
    except (FileNotFoundError, RuntimeError) as exc:
        raise HTTPException(
            status_code=502,
            detail={"code": "sku_capture_failed", "message": str(exc)},
        ) from exc

    previous_snapshot = snapshots[0]
    product_reviews = product_detail.setdefault("reviews", {})
    if previous_snapshot.get("review_count_text"):
        product_reviews["count_text"] = previous_snapshot["review_count_text"]
    if previous_snapshot.get("review_preview_text"):
        product_reviews["preview_text"] = previous_snapshot["review_preview_text"]

    captured_at = datetime.now().astimezone().isoformat(timespec="microseconds")
    previous_archive = previous_snapshot.get("archive")
    carried_archive = None
    if previous_archive:
        carried_archive = {
            field_name: previous_archive[field_name]
            for field_name in (
                "product_fields",
                "images",
                "sku_catalog",
                "reviews",
                "questions",
                "videos",
                "coverage",
                "capture_status",
                "raw_source_refs",
            )
        }
        carried_archive["capture_status"] = {
            **carried_archive["capture_status"],
            "selected_sku": sku_capture.get("price_status", "captured"),
        }
    with closing(connect_database(application_data_directory)) as connection:
        save_product_capture(
            connection,
            product_detail,
            captured_at,
            str(capture_paths["detail_result_path"]),
            sku_capture=sku_capture,
            archive=carried_archive,
        )
        saved_snapshot = list_product_snapshots(connection, item_id)[0]
    saved_archive = saved_snapshot.get("archive") or {}
    return {
        "item_id": str(item_id),
        "title": saved_snapshot["title"],
        "shop_name": saved_snapshot.get("shop_name"),
        "visible_price_text": saved_snapshot.get("visible_price_text"),
        "sku": saved_snapshot.get("sku"),
        "product_archive": {
            "title": saved_snapshot["title"],
            **saved_archive,
            "image_count": len(saved_archive.get("images") or []),
            "image_capture_status": "success",
        },
        "dimensions": (saved_archive.get("sku_catalog") or {}).get("dimensions") or [],
        "capture_status": "sku_captured",
    }


def _product_detail_from_snapshot(item_id, snapshot, reviews_archive=None):
    reviews_archive = reviews_archive or {}
    return {
        "page_url": snapshot["page_url"],
        "product": {
            "item_id": str(item_id),
            "page_title": snapshot["title"],
            "main_image_url": snapshot.get("main_image_url"),
            "visible_price_text": snapshot.get("visible_price_text"),
        },
        "shop": {
            "name": snapshot.get("shop_name"),
            "rating_text": snapshot.get("shop_rating_text"),
            "positive_rate_text": snapshot.get("shop_positive_rate_text"),
            "shipping_text": snapshot.get("shop_shipping_text"),
            "refund_text": snapshot.get("shop_refund_text"),
        },
        "sales": {
            "sold_text": snapshot.get("sold_text"),
            "repeat_buyer_text": snapshot.get("repeat_buyer_text"),
            "cart_text": snapshot.get("cart_text"),
        },
        "reviews": {
            "count_text": reviews_archive.get("total_text") or snapshot.get("review_count_text"),
            "preview_text": "\n".join(
                item.get("content", "") for item in reviews_archive.get("items") or []
            ) or snapshot.get("review_preview_text"),
        },
        "services": snapshot.get("services") or [],
        "attributes": {"visible_text": snapshot.get("attributes_text")},
    }


def _merge_archive_items(existing_items, new_items, identity_fields):
    merged = []
    seen = set()
    for item in [*(existing_items or []), *(new_items or [])]:
        if not isinstance(item, dict):
            continue
        identity = tuple(str(item.get(field_name) or "").strip() for field_name in identity_fields)
        if not any(identity) or identity in seen:
            continue
        seen.add(identity)
        merged.append(item)
    return merged


def _continue_product_archive_capture(project_id, item_id):
    application_data_directory = _competitor_data_directory()
    if project_id is not None:
        _require_competitor_project(application_data_directory, project_id)
    with closing(connect_database(application_data_directory)) as connection:
        snapshots = list_product_snapshots(connection, item_id)
    if not snapshots or not snapshots[0].get("archive"):
        raise HTTPException(
            status_code=404,
            detail={
                "code": "product_archive_not_found",
                "message": "尚未保存竞品原始档案，请先抓取商品信息。",
            },
        )
    previous_snapshot = snapshots[0]
    previous_archive = previous_snapshot["archive"]
    previous_reviews = previous_archive.get("reviews") or {}
    review_start_page = previous_reviews.get("next_page") or 4
    capture_paths = _competitor_capture_paths(application_data_directory, item_id)
    try:
        continued = capture_product_images(
            application_data_directory,
            previous_snapshot["page_url"],
            item_id,
            capture_paths["browser_image_result_path"],
            review_start_page=review_start_page,
        )
    except (FileNotFoundError, RuntimeError, OSError) as exc:
        raise HTTPException(
            status_code=502,
            detail={"code": "product_archive_continue_failed", "message": str(exc)},
        ) from exc
    if continued.get("status") == "login_required":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "taobao_browser_login_required",
                "message": continued["message"],
            },
        )
    if continued.get("status") != "success":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "product_archive_continue_unavailable",
                "message": continued.get("message") or "当前页面没有返回更多竞品数据。",
            },
        )

    new_reviews = continued.get("reviews") or {}
    merged_review_items = _merge_archive_items(
        previous_reviews.get("items"),
        new_reviews.get("items"),
        ("content", "sku", "date"),
    )
    merged_reviews = {
        "status": "captured" if merged_review_items else previous_reviews.get("status", "not_exposed"),
        "total_text": new_reviews.get("total_text") or previous_reviews.get("total_text"),
        "tags": list(
            dict.fromkeys([*(previous_reviews.get("tags") or []), *(new_reviews.get("tags") or [])])
        ),
        "items": merged_review_items,
        "next_page": new_reviews.get("next_page") or review_start_page,
    }
    previous_questions = previous_archive.get("questions") or {}
    new_questions = continued.get("questions") or {}
    merged_question_items = _merge_archive_items(
        previous_questions.get("items"),
        new_questions.get("items"),
        ("question",),
    )
    merged_questions = {
        "status": "captured" if merged_question_items else previous_questions.get("status", "not_exposed"),
        "total_text": new_questions.get("total_text") or previous_questions.get("total_text"),
        "items": merged_question_items,
    }
    merged_archive = {
        "product_fields": {
            **(previous_archive.get("product_fields") or {}),
            **{
                key: value
                for key, value in (continued.get("product_fields") or {}).items()
                if value not in (None, "", [], {})
            },
        },
        "images": previous_archive.get("images") or continued.get("images") or [],
        "sku_catalog": (
            previous_archive.get("sku_catalog")
            if (previous_archive.get("sku_catalog") or {}).get("dimensions")
            else continued.get("sku_catalog") or {}
        ),
        "reviews": merged_reviews,
        "questions": merged_questions,
        "videos": previous_archive.get("videos") or continued.get("videos") or [],
        "coverage": {
            **(previous_archive.get("coverage") or {}),
            **(continued.get("coverage") or {}),
            "reviews": merged_reviews["status"],
            "questions": merged_questions["status"],
        },
        "capture_status": {
            **(previous_archive.get("capture_status") or {}),
            "browser": "success",
            "continued_reviews_from_page": review_start_page,
        },
        "raw_source_refs": {
            **(previous_archive.get("raw_source_refs") or {}),
            f"browser_reviews_page_{review_start_page}": continued.get("raw_source_ref"),
        },
    }
    product_detail = _product_detail_from_snapshot(item_id, previous_snapshot, merged_reviews)
    previous_sku = previous_snapshot.get("sku")
    carried_sku = None
    if previous_sku:
        carried_sku = {
            "selected_options": previous_sku["selected_options"],
            "display_price_text": previous_sku["display_price_text"],
            "sku_price_text": previous_sku["sku_price_text"],
            "price_status": previous_sku["price_status"],
            "raw_price_ref": previous_sku["raw_source_ref"],
        }
    captured_at = datetime.now().astimezone().isoformat(timespec="microseconds")
    with closing(connect_database(application_data_directory)) as connection:
        saved = save_product_capture(
            connection,
            product_detail,
            captured_at,
            str(continued.get("raw_source_ref") or capture_paths["browser_image_result_path"]),
            sku_capture=carried_sku,
            archive=merged_archive,
        )
        existing_record = get_competitor_record(connection, str(item_id))
        if existing_record is not None:
            upsert_competitor_record(
                connection,
                item_id=str(item_id),
                source_url=existing_record["source_url"],
                resolved_url=existing_record["resolved_url"],
                captured_at=captured_at,
            )
    return {
        **saved,
        "item_id": str(item_id),
        "title": previous_snapshot["title"],
        "shop_name": previous_snapshot.get("shop_name"),
        "product_archive": {
            "title": previous_snapshot["title"],
            **merged_archive,
            "image_count": len(merged_archive["images"]),
            "image_capture_status": "success",
        },
        "added_review_count": len(merged_review_items) - len(previous_reviews.get("items") or []),
        "review_count": len(merged_review_items),
        "capture_status": "archive_extended",
    }


@application.get("/api/competitors")
def independent_competitor_records():
    application_data_directory = _competitor_data_directory()
    with closing(connect_database(application_data_directory)) as connection:
        records = list_competitor_records(connection)
        buyer_urls = _buyer_urls_for_items(
            connection,
            [record["item_id"] for record in records],
        )
    for record in records:
        record["buyer_url"] = (
            buyer_urls.get(str(record["item_id"]))
            or record.get("source_url")
            or record.get("resolved_url")
        )
    return {"records": records}


@application.post("/api/competitors/prepare", status_code=201)
def prepare_independent_competitor(request: CompetitorPrepareRequest):
    _require_entitlement("capture")
    return {
        **_prepare_product_capture(None, request.product_url),
        "comparison_role": "competitor",
    }


@application.post("/api/competitors/{item_id}/continue", status_code=201)
def continue_independent_competitor_archive(item_id: str):
    _require_entitlement("capture")
    if not str(item_id).isdigit():
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_item_id", "message": "商品 ID 必须为数字。"},
        )
    return _continue_product_archive_capture(None, str(item_id))


@application.post("/api/competitors/{item_id}/capture", status_code=201)
def capture_independent_competitor_sku(
    item_id: str,
    request: CompetitorSkuCaptureRequest,
):
    _require_entitlement("capture")
    return _capture_product_sku(None, item_id, request.selected_options)


@application.post("/api/projects/{project_id}/competitors/prepare", status_code=201)
def prepare_competitor(
    project_id: int,
    request: CompetitorPrepareRequest,
):
    _require_entitlement("capture")
    return {
        **_prepare_product_capture(project_id, request.product_url),
        "comparison_role": "competitor",
    }


@application.post(
    "/api/projects/{project_id}/competitors/{item_id}/continue",
    status_code=201,
)
def continue_competitor_archive(project_id: int, item_id: str):
    _require_entitlement("capture")
    if not str(item_id).isdigit():
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_item_id", "message": "商品 ID 必须为数字。"},
        )
    return _continue_product_archive_capture(project_id, str(item_id))


@application.post(
    "/api/projects/{project_id}/competitors/{item_id}/capture",
    status_code=201,
)
def capture_competitor_sku(
    project_id: int,
    item_id: str,
    request: CompetitorSkuCaptureRequest,
    search_snapshot_id: int | None = None,
):
    _require_entitlement("capture")
    return _capture_product_sku(
        project_id,
        item_id,
        request.selected_options,
        search_snapshot_id,
    )


def _saved_competitor_snapshot(project_id, item_id, *, require_record=False):
    application_data_directory = _competitor_data_directory()
    if project_id is not None:
        _require_competitor_project(application_data_directory, project_id)
    with closing(connect_database(application_data_directory)) as connection:
        if require_record and get_competitor_record(connection, str(item_id)) is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "competitor_record_not_found",
                    "message": "竞品记录不存在或已删除",
                    "value": item_id,
                },
            )
        product_snapshots = list_product_snapshots(connection, item_id)
        if not product_snapshots:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "competitor_snapshot_not_found",
                    "message": "尚未保存该商品的详情快照，请先主动采集",
                    "value": item_id,
                },
            )

    return application_data_directory, product_snapshots[0]


@application.get("/api/competitors/{item_id}")
def independent_competitor_snapshot(item_id: str):
    application_data_directory, snapshot = _saved_competitor_snapshot(
        None,
        item_id,
        require_record=True,
    )
    with closing(connect_database(application_data_directory)) as connection:
        record = get_competitor_record(connection, str(item_id))
        product_snapshots = list_product_snapshots(connection, str(item_id))
        buyer_url = _buyer_urls_for_items(connection, [item_id]).get(str(item_id))
    outbound_url = (
        buyer_url
        or (record or {}).get("source_url")
        or (record or {}).get("resolved_url")
        or snapshot.get("page_url")
    )
    return {
        "item_id": str(item_id),
        "record": record,
        "snapshot": snapshot,
        "outbound_url": outbound_url,
        "history": build_competitor_history(product_snapshots),
    }


@application.delete("/api/competitors/{item_id}")
def remove_independent_competitor(item_id: str):
    application_data_directory = _competitor_data_directory()
    with closing(connect_database(application_data_directory)) as connection:
        deleted = delete_competitor_record(connection, str(item_id))
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "competitor_record_not_found",
                "message": "竞品记录不存在或已删除",
                "value": item_id,
            },
        )
    return {"item_id": str(item_id), "deleted": True, "message": "竞品记录已删除"}


@application.get("/api/projects/{project_id}/competitors/{item_id}")
def competitor_snapshot(project_id: int, item_id: str):
    application_data_directory, snapshot = _saved_competitor_snapshot(project_id, item_id)
    with closing(connect_database(application_data_directory)) as connection:
        product_snapshots = list_product_snapshots(connection, str(item_id))
        buyer_url = _buyer_urls_for_items(connection, [item_id]).get(str(item_id))
    return {
        "item_id": str(item_id),
        "snapshot": snapshot,
        "outbound_url": buyer_url or snapshot.get("page_url"),
        "history": build_competitor_history(product_snapshots),
    }


@application.get("/api/projects/{project_id}/competitors/{item_id}/available")
def saved_competitor_available(project_id: int, item_id: str):
    application_data_directory = _competitor_data_directory()
    _require_competitor_project(application_data_directory, project_id)
    with closing(connect_database(application_data_directory)) as connection:
        return {"available": bool(list_product_snapshots(connection, str(item_id)))}


def _export_competitor_package_response(project_id, item_id, *, require_record=False):
    application_data_directory, snapshot = _saved_competitor_snapshot(
        project_id,
        item_id,
        require_record=require_record,
    )
    output_path = (
        application_data_directory
        / "exports"
        / f"competitor-package-{item_id}-{snapshot['product_snapshot_id']}.zip"
    )
    export_competitor_package_zip(
        item_id,
        snapshot,
        output_path,
        image_fetcher=fetch_product_image_payload,
    )
    safe_title = "".join(
        character
        for character in str(snapshot.get("title") or "竞品")
        if character not in '<>:"/\\|?*'
    )[:40]
    return FileResponse(
        output_path,
        media_type="application/zip",
        filename=f"{safe_title or '竞品'}-{item_id}-资料包.zip",
    )


@application.get("/api/competitors/{item_id}/export.zip")
def export_independent_competitor_package(item_id: str):
    return _export_competitor_package_response(None, item_id, require_record=True)


@application.get(
    "/api/projects/{project_id}/competitors/{item_id}/export.zip"
)
def export_competitor_package(project_id: int, item_id: str):
    return _export_competitor_package_response(project_id, item_id)


def _monitor_data_directory():
    configured_data_directory = application.state.application_data_directory
    return (
        Path(configured_data_directory)
        if configured_data_directory is not None
        else resolve_application_data_directory()
    )


def _monitor_response(application_data_directory):
    with closing(connect_database(application_data_directory)) as connection:
        runs = list_monitor_runs(connection, limit=10)
        today_prefix = datetime.now().astimezone().date().isoformat()
        today_runs = [run for run in runs if str(run.get("started_at") or "").startswith(today_prefix)]
        important_changes = []
        seen_changes = set()
        for run in today_runs:
            for change in (run.get("summary") or {}).get("important_changes") or []:
                identity = (
                    change.get("task_type"),
                    change.get("item_id"),
                    change.get("category"),
                    change.get("summary"),
                )
                if identity in seen_changes:
                    continue
                seen_changes.add(identity)
                important_changes.append(change)
        important_changes.sort(
            key=lambda item: (
                item.get("priority") != "high",
                item.get("category") or "",
                item.get("title") or "",
            )
        )
        return {
            "settings": read_monitor_settings(connection),
            "tasks": list_monitor_tasks(connection),
            "runs": runs,
            "important_changes": important_changes[:50],
            "monitor_summary": {
                "run_count_today": len(today_runs),
                "important_count": len(important_changes),
                "latest_run_at": runs[0]["started_at"] if runs else None,
            },
        }


@application.get("/api/monitor")
def monitor_center():
    return _monitor_response(_monitor_data_directory())


@application.put("/api/monitor/schedule")
def update_monitor_schedule(request: MonitorScheduleRequest):
    if request.enabled:
        _require_entitlement("monitor")
    application_data_directory = _monitor_data_directory()
    updated_at = datetime.now().astimezone().isoformat(timespec="seconds")
    try:
        if request.enabled:
            install_windows_schedule(application_data_directory, request.run_time)
        else:
            remove_windows_schedule()
        with closing(connect_database(application_data_directory)) as connection:
            settings = save_monitor_settings(
                connection,
                enabled=request.enabled,
                run_time=request.run_time,
                updated_at=updated_at,
            )
    except (OSError, RuntimeError, ValueError) as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "monitor_schedule_failed", "message": str(exc)},
        ) from exc
    return {"settings": settings}


@application.post("/api/projects/{project_id}/monitor/keyword", status_code=201)
def add_keyword_monitor(project_id: int, request: KeywordMonitorRequest | None = None):
    _require_entitlement("monitor")
    application_data_directory = _monitor_data_directory()
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    with closing(connect_database(application_data_directory)) as connection:
        project = connection.execute(
            "SELECT id, keyword FROM market_projects WHERE id = ?",
            (project_id,),
        ).fetchone()
        if project is None:
            raise HTTPException(
                status_code=404,
                detail={"code": "project_not_found", "message": "搜索历史不存在"},
            )
        task = upsert_monitor_task(
            connection,
            task_type="keyword",
            target_key=f"project:{project_id}",
            project_id=project_id,
            label=project["keyword"],
            created_at=now,
            page_count=(request.page_count if request is not None else 1),
        )
    return {
        "task_id": task["id"],
        "message": f"关键词已加入每日监控，每次采集 {task['page_count']} 页",
    }


@application.post(
    "/api/projects/{project_id}/competitors/{item_id}/monitor",
    status_code=201,
)
def add_competitor_monitor(project_id: int, item_id: str):
    _require_entitlement("monitor")
    return _add_competitor_monitor(project_id, item_id)


@application.post("/api/competitors/{item_id}/monitor", status_code=201)
def add_independent_competitor_monitor(item_id: str):
    _require_entitlement("monitor")
    return _add_competitor_monitor(None, item_id, require_record=True)


def _add_competitor_monitor(project_id, item_id, *, require_record=False):
    application_data_directory, snapshot = _saved_competitor_snapshot(
        project_id,
        item_id,
        require_record=require_record,
    )
    product_url = str(snapshot.get("page_url") or "").strip()
    if not product_url:
        raise HTTPException(
            status_code=422,
            detail={"code": "competitor_url_missing", "message": "竞品快照缺少详情链接"},
        )
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    with closing(connect_database(application_data_directory)) as connection:
        task = upsert_monitor_task(
            connection,
            task_type="competitor",
            target_key=f"item:{item_id}",
            project_id=project_id,
            item_id=str(item_id),
            product_url=product_url,
            label=str(snapshot.get("title") or item_id),
            created_at=now,
        )
    return {"task_id": task["id"], "message": "竞品已加入每日监控"}


@application.post(
    "/api/projects/{project_id}/monitor/competitor",
    status_code=201,
)
def add_search_result_competitor_monitor(project_id: int, request: CompetitorMonitorRequest):
    _require_entitlement("monitor")
    application_data_directory = _monitor_data_directory()
    _require_competitor_project(application_data_directory, project_id)
    try:
        product_url = validate_product_detail_url(request.product_url)
        parsed_item_id = parse_qs(urlparse(product_url).query)["id"][0]
    except (KeyError, IndexError, ValueError) as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_competitor_input", "message": str(exc)},
        ) from exc
    if request.item_id and str(request.item_id).strip() != parsed_item_id:
        raise HTTPException(
            status_code=422,
            detail={"code": "competitor_item_mismatch", "message": "商品链接与商品 ID 不一致"},
        )
    label = " ".join(str(request.label or parsed_item_id).split())[:240]
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    with closing(connect_database(application_data_directory)) as connection:
        task = upsert_monitor_task(
            connection,
            task_type="competitor",
            target_key=f"item:{parsed_item_id}",
            project_id=project_id,
            item_id=parsed_item_id,
            product_url=product_url,
            label=label,
            created_at=now,
        )
    return {"task_id": task["id"], "message": "竞品已加入每日监控"}


@application.post("/api/projects/{project_id}/monitor/shop", status_code=201)
def add_shop_monitor(project_id: int, request: ShopMonitorRequest):
    _require_entitlement("monitor")
    application_data_directory = _monitor_data_directory()
    _require_competitor_project(application_data_directory, project_id)
    try:
        shop_url = validate_shop_url(request.shop_url)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_shop_url", "message": str(exc)},
        ) from exc
    shop_name = " ".join(str(request.shop_name or "淘宝店铺").split())[:120]
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    with closing(connect_database(application_data_directory)) as connection:
        task = upsert_monitor_task(
            connection,
            task_type="shop",
            target_key=f"shop:{shop_url}",
            project_id=project_id,
            shop_url=shop_url,
            shop_name=shop_name,
            label=shop_name,
            created_at=now,
        )
    return {"task_id": task["id"], "message": f"{shop_name}已加入每日店铺监控"}


@application.post("/api/monitor/shop", status_code=201)
def add_manual_shop_monitor(request: ShopMonitorRequest):
    _require_entitlement("monitor")
    application_data_directory = _monitor_data_directory()
    try:
        shop_url = validate_shop_url(request.shop_url)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_shop_url", "message": str(exc)},
        ) from exc
    with closing(connect_database(application_data_directory)) as connection:
        project = connection.execute(
            "SELECT id FROM market_projects ORDER BY updated_at DESC, id DESC LIMIT 1"
        ).fetchone()
        if project is None:
            raise HTTPException(
                status_code=422,
                detail={"code": "project_required", "message": "请先完成一次关键词搜索，再添加店铺监控"},
            )
        hostname = (urlparse(shop_url).hostname or "淘系店铺").split(".")[0]
        shop_name = " ".join(str(request.shop_name or hostname).split())[:120]
        task = upsert_monitor_task(
            connection,
            task_type="shop",
            target_key=f"shop:{shop_url}",
            project_id=project["id"],
            shop_url=shop_url,
            shop_name=shop_name,
            label=shop_name,
            created_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        )
    return {"task_id": task["id"], "shop_url": shop_url, "message": "店铺已加入监控，正在建立商品基线"}


@application.delete("/api/monitor/tasks/{task_id}", status_code=204)
def remove_monitor_task(task_id: int):
    application_data_directory = _monitor_data_directory()
    with closing(connect_database(application_data_directory)) as connection:
        deleted = delete_monitor_task(connection, task_id)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail={"code": "monitor_task_not_found", "message": "监控项不存在"},
        )
    return Response(status_code=204)


def _monitor_error_message(error):
    if isinstance(error, HTTPException):
        detail = error.detail
        if isinstance(detail, dict):
            return str(detail.get("message") or detail.get("code") or detail)
        return str(detail)
    return str(error) or error.__class__.__name__


def _changes_with_task_context(changes, task):
    return [
        {
            **change,
            "task_id": task["id"],
            "task_type": task["task_type"],
            "task_label": task["label"],
            "project_id": task["project_id"],
        }
        for change in changes
    ]


def _capture_shop_monitor_task(application_data_directory, task):
    raw_path = (
        Path(application_data_directory)
        / "raw"
        / "monitor-shops"
        / str(task["id"])
        / f"{uuid4().hex}.json"
    )
    captured = capture_shop_listing(
        application_data_directory,
        task["shop_url"],
        task.get("shop_name") or task["label"],
        raw_path,
    )
    if captured.get("status") != "success":
        raise RuntimeError(captured.get("message") or "店铺商品清单读取失败")
    with closing(connect_database(application_data_directory)) as connection:
        snapshot_id = save_shop_snapshot(
            connection,
            monitor_task_id=task["id"],
            captured_at=captured["captured_at"],
            shop_url=captured["shop_url"],
            shop_name=captured.get("shop_name"),
            raw_source_ref=captured["raw_source_ref"],
            products=captured["products"],
        )
        snapshots = list_shop_snapshots(connection, task["id"], limit=3)
    important_changes = _changes_with_task_context(
        summarize_shop_changes(
            snapshots[0],
            snapshots[1] if len(snapshots) > 1 else None,
            snapshots[2] if len(snapshots) > 2 else None,
        ),
        task,
    )
    return {
        "task_id": task["id"],
        "task_type": "shop",
        "label": task["label"],
        "status": "success",
        "shop_snapshot_id": snapshot_id,
        "result_count": captured["result_count"],
        "baseline_created": len(snapshots) == 1,
        "important_changes": important_changes,
        "message": f"店铺基线已保存，本次监测到 {captured['result_count']} 件商品",
    }


@application.post("/api/monitor/tasks/{task_id}/capture-shop")
def capture_one_shop_monitor(task_id: int):
    _require_entitlement("monitor")
    application_data_directory = _monitor_data_directory()
    with closing(connect_database(application_data_directory)) as connection:
        task = next(
            (item for item in list_monitor_tasks(connection) if item["id"] == task_id),
            None,
        )
    if task is None or task["task_type"] != "shop":
        raise HTTPException(
            status_code=404,
            detail={"code": "shop_monitor_not_found", "message": "店铺监控任务不存在"},
        )
    try:
        return _capture_shop_monitor_task(application_data_directory, task)
    except (OSError, RuntimeError, ValueError) as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "shop_capture_failed", "message": str(exc)},
        ) from exc


def run_monitor_cycle(*, trigger="manual"):
    try:
        _require_entitlement("monitor")
    except HTTPException:
        return False
    application_data_directory = _monitor_data_directory()
    with closing(connect_database(application_data_directory)) as connection:
        settings = read_monitor_settings(connection)
        tasks = list_monitor_tasks(connection, enabled_only=True)
    if trigger == "scheduled" and not settings["enabled"]:
        return True

    with MonitorRunLock(application_data_directory) as run_lock:
        started_at = datetime.now().astimezone().isoformat(timespec="seconds")
        with closing(connect_database(application_data_directory)) as connection:
            run_id = start_monitor_run(
                connection,
                started_at=started_at,
                task_count=len(tasks),
            )
        if not run_lock.acquired:
            with closing(connect_database(application_data_directory)) as connection:
                finish_monitor_run(
                    connection,
                    run_id,
                    finished_at=datetime.now().astimezone().isoformat(timespec="seconds"),
                    status="skipped",
                    success_count=0,
                    failure_count=0,
                    summary={"trigger": trigger, "message": "已有监控任务正在执行"},
                )
            return True

        results = []
        for task in tasks:
            try:
                if task["task_type"] == "keyword":
                    with closing(connect_database(application_data_directory)) as connection:
                        previous_snapshots = list_search_snapshots(connection, task["project_id"])
                    previous_snapshot_id = (
                        previous_snapshots[0]["snapshot_id"] if previous_snapshots else None
                    )
                    snapshot = create_search_snapshot(
                        task["project_id"],
                        SearchCreateRequest(result_count=None),
                    )
                    requested_page_count = task.get("page_count") or 1
                    captured_page_count = 1
                    page_messages = []
                    task_status = "success"
                    for _page_number in range(2, requested_page_count + 1):
                        next_page = collect_next_search_page(
                            task["project_id"], snapshot["snapshot_id"]
                        )
                        page_messages.append(next_page.get("message"))
                        if next_page.get("status") == "success":
                            snapshot = next_page["snapshot"]
                            captured_page_count += 1
                            continue
                        if next_page.get("status") == "exhausted":
                            break
                        task_status = "partial"
                        break
                    important_changes = []
                    current_snapshot_id = snapshot.get("snapshot_id")
                    if previous_snapshot_id and current_snapshot_id and previous_snapshot_id != current_snapshot_id:
                        try:
                            with closing(connect_database(application_data_directory)) as connection:
                                raw_diff = compare_search_snapshots(
                                    connection,
                                    task["project_id"],
                                    previous_snapshot_id,
                                    current_snapshot_id,
                                )
                            important_changes = _changes_with_task_context(
                                summarize_keyword_changes(raw_diff), task
                            )
                        except LookupError:
                            important_changes = []
                    results.append(
                        {
                            "task_id": task["id"],
                            "task_type": "keyword",
                            "label": task["label"],
                            "status": task_status,
                            "snapshot_id": snapshot.get("snapshot_id"),
                            "result_count": snapshot.get("result_count", 0),
                            "requested_page_count": requested_page_count,
                            "captured_page_count": captured_page_count,
                            "baseline_created": previous_snapshot_id is None,
                            "important_changes": important_changes,
                            "message": next((message for message in reversed(page_messages) if message), None),
                        }
                    )
                elif task["task_type"] == "competitor":
                    with closing(connect_database(application_data_directory)) as connection:
                        previous_product_snapshots = list_product_snapshots(
                            connection, task["item_id"]
                        )
                    previous_product_snapshot_id = (
                        previous_product_snapshots[0]["product_snapshot_id"]
                        if previous_product_snapshots
                        else None
                    )
                    prepared = _prepare_product_capture(
                        task["project_id"], task["product_url"]
                    )
                    captured_item_id = str(prepared.get("item_id") or task["item_id"])
                    with closing(connect_database(application_data_directory)) as connection:
                        latest_product_snapshots = list_product_snapshots(
                            connection, captured_item_id
                        )
                    important_changes = []
                    if (
                        previous_product_snapshot_id
                        and latest_product_snapshots
                        and latest_product_snapshots[0]["product_snapshot_id"]
                        != previous_product_snapshot_id
                    ):
                        older = next(
                            (
                                item
                                for item in latest_product_snapshots
                                if item["product_snapshot_id"] == previous_product_snapshot_id
                            ),
                            None,
                        )
                        if older is not None:
                            important_changes = _changes_with_task_context(
                                summarize_competitor_changes(
                                    {**older, "item_id": captured_item_id},
                                    {**latest_product_snapshots[0], "item_id": captured_item_id},
                                ),
                                task,
                            )
                    results.append(
                        {
                            "task_id": task["id"],
                            "task_type": "competitor",
                            "label": task["label"],
                            "status": "success",
                            "item_id": captured_item_id,
                            "baseline_created": previous_product_snapshot_id is None,
                            "important_changes": important_changes,
                        }
                    )
                elif task["task_type"] == "shop":
                    results.append(_capture_shop_monitor_task(application_data_directory, task))
            except Exception as exc:
                results.append(
                    {
                        "task_id": task["id"],
                        "task_type": task["task_type"],
                        "label": task["label"],
                        "status": "failed",
                        "message": _monitor_error_message(exc),
                    }
                )

        success_count = sum(result["status"] in {"success", "partial"} for result in results)
        failure_count = sum(result["status"] == "failed" for result in results)
        partial_count = sum(result["status"] == "partial" for result in results)
        important_changes = [
            change
            for result in results
            for change in (result.get("important_changes") or [])
        ]
        important_changes.sort(
            key=lambda item: (
                item.get("priority") != "high",
                item.get("category") or "",
                item.get("title") or "",
            )
        )
        if not tasks:
            status = "skipped"
        elif failure_count == 0 and partial_count == 0:
            status = "success"
        elif success_count:
            status = "partial"
        else:
            status = "failed"
        with closing(connect_database(application_data_directory)) as connection:
            finish_monitor_run(
                connection,
                run_id,
                finished_at=datetime.now().astimezone().isoformat(timespec="seconds"),
                status=status,
                success_count=success_count,
                failure_count=failure_count,
                summary={
                    "trigger": trigger,
                    "items": results,
                    "important_changes": important_changes,
                },
                error_text=(
                    next(
                        (result.get("message") for result in results if result["status"] == "failed"),
                        None,
                    )
                ),
            )
    return status in ("success", "skipped")


@application.post("/api/monitor/run-now")
def run_monitor_now():
    _require_entitlement("monitor")
    success = run_monitor_cycle(trigger="manual")
    payload = _monitor_response(_monitor_data_directory())
    payload["success"] = success
    return payload


def find_running_product_version(host=LOOPBACK_HOST, port=APPLICATION_PORT):
    health_url = f"http://{host}:{port}/api/health"
    try:
        response = httpx.get(health_url, timeout=0.5)
    except httpx.RequestError:
        return None

    if response.status_code != 200:
        raise RuntimeError(
            f"Listen address used by another service: host={host} port={port} "
            f"health_status={response.status_code}"
        )

    try:
        health_payload = response.json()
    except ValueError as exc:
        raise RuntimeError(
            f"Listen address returned invalid health JSON: host={host} port={port}"
        ) from exc

    actual_product_key = health_payload.get("product_key")
    if actual_product_key != PRODUCT_KEY:
        raise RuntimeError(
            f"Listen address used by product_key={actual_product_key!r}: "
            f"host={host} port={port}"
        )

    actual_version = health_payload.get("version")
    if not isinstance(actual_version, str) or not actual_version.strip():
        raise RuntimeError(
            f"Running product returned invalid version={actual_version!r}: "
            f"host={host} port={port}"
        )
    return actual_version


def find_running_product(host=LOOPBACK_HOST, ports=APPLICATION_PORT_CANDIDATES):
    for port in ports:
        try:
            running_version = find_running_product_version(host, port)
        except RuntimeError:
            continue
        if running_version is not None:
            return port, running_version
    return None


def ensure_listen_address_available(host, port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listen_probe:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            listen_probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            listen_probe.bind((host, port))
        except OSError as exc:
            raise RuntimeError(
                f"Listen address unavailable: host={host} port={port} error={exc}"
            ) from exc


def select_application_port(host=LOOPBACK_HOST, ports=APPLICATION_PORT_CANDIDATES):
    unavailable_ports = []
    for port in ports:
        try:
            ensure_listen_address_available(host, port)
        except RuntimeError:
            unavailable_ports.append(port)
            continue
        return port

    port_text = "、".join(str(port) for port in unavailable_ports)
    raise ApplicationStartupError(
        "无法启动本地服务，电脑上的可用端口可能被其他软件占用或被系统保留。\n\n"
        f"已尝试端口：{port_text or '无'}。\n"
        "请重启电脑后再打开；如果仍然失败，请把此提示发给管理员。"
    )


def application_url(port=APPLICATION_PORT):
    return f"http://{LOOPBACK_HOST}:{port}/"


def open_application_in_browser(port=APPLICATION_PORT):
    try:
        return bool(webbrowser.open(application_url(port)))
    except Exception:
        return False


def schedule_browser_open(port=APPLICATION_PORT, delay_seconds=0.9):
    timer = threading.Timer(delay_seconds, open_application_in_browser, args=(port,))
    timer.daemon = True
    timer.start()
    return timer


def schedule_packaged_browser_open(port=APPLICATION_PORT, delay_seconds=0.9):
    if not bool(getattr(sys, "frozen", False)):
        return None
    return schedule_browser_open(port, delay_seconds)


def start_application(*, open_browser=False):
    running_product = find_running_product()
    if running_product is not None:
        running_port, running_version = running_product
        if bool(getattr(sys, "frozen", False)) or open_browser:
            open_application_in_browser(running_port)
        print(
            f"Application already running: host={LOOPBACK_HOST} "
            f"port={running_port} version={running_version}"
        )
        return 0

    selected_port = select_application_port()
    schedule_packaged_browser_open(selected_port)
    if open_browser and not bool(getattr(sys, "frozen", False)):
        schedule_browser_open(selected_port)
    run_options = {
        "host": LOOPBACK_HOST,
        "port": selected_port,
        "log_level": "info",
    }
    if bool(getattr(sys, "frozen", False)):
        run_options.update(log_config=None, access_log=False)
    uvicorn.run(application, **run_options)
    return 0


def show_startup_error(message):
    if bool(getattr(sys, "frozen", False)) and os.name == "nt":
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(None, str(message), PRODUCT_NAME, 0x10)
            return True
        except Exception:
            pass
    print(str(message), file=sys.stderr)
    return False


def main(argv=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    if "--run-monitor" in arguments:
        return 0 if run_monitor_cycle(trigger="scheduled") else 1
    try:
        return start_application(open_browser="--open-browser" in arguments)
    except ApplicationStartupError as exc:
        show_startup_error(str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
