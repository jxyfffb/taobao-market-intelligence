"""社区版（开源）授权提供器。

开源仓库不包含离线激活逻辑，`get_license_status()` 恒返回可用状态，
因此采集、导出、监控等全部功能开箱即用。

商业版用同名的 `src/license_client.py` 覆盖本模块（两者接口一致），
`app.py` 会优先加载 `license_client`，加载失败时自动回退到这里。
"""

from __future__ import annotations


class LicenseError(RuntimeError):
    """与商业版保持一致的异常类型，便于上层统一捕获。"""


COMMUNITY_STATUS_MESSAGE = "开源社区版：无需激活码，全部本机功能可直接使用。"
COMMUNITY_PLAN_LABEL = "开源社区版"


def get_license_status() -> dict:
    return {
        "status": "community",
        "can_use": True,
        "message": COMMUNITY_STATUS_MESSAGE,
        "plan_label": COMMUNITY_PLAN_LABEL,
        "expires_at": None,
        "expires_at_text": "永久",
        "remaining_days": None,
        "installation_id_suffix": "",
        "request_code": "",
        "request_type": "activation",
        "is_community_build": True,
    }


def activate_license(code: str) -> dict:
    raise LicenseError("开源社区版无需激活码，直接使用即可。")


def redeem_license(code: str) -> dict:
    raise LicenseError("开源社区版无需激活码，直接使用即可。")
