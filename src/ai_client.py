import base64
import binascii
import json
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import pywintypes
import win32crypt


SETTINGS_RELATIVE_PATH = Path("settings") / "ai-provider.json"
DPAPI_DESCRIPTION = "taobao-market-intelligence-ai-api-key"
DPAPI_UI_FORBIDDEN = 0x1
CONNECTION_TIMEOUT_SECONDS = 20.0
COMPLETE_ANALYSIS_TIMEOUT_SECONDS = 90.0
COMPLETE_ANALYSIS_TIMEOUT_RETRIES = 1
TEXT_COMPLETION_MAX_TOKENS = 2000
VISION_COMPLETION_MAX_TOKENS = 4000
SETTINGS_VERSION = 2
DEFAULT_AI_PRESET_ID = "volcengine-ark"
AI_PROVIDER_PRESETS = {
    DEFAULT_AI_PRESET_ID: {
        "id": DEFAULT_AI_PRESET_ID,
        "label": "火山方舟",
        "key_label": "火山方舟 API Key",
        "description": "豆包模型，支持文字、JSON 与主图分析。",
        "recommended": True,
        "key_url": "https://console.volcengine.com/ark/region:ark+cn-beijing/apikey",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "model": "doubao-seed-2-0-lite-260215",
    },
    "deepseek": {
        "id": "deepseek",
        "label": "DeepSeek",
        "key_label": "DeepSeek API Key",
        "description": "适合文字分析与选品决策。",
        "recommended": False,
        "key_url": "https://platform.deepseek.com/api_keys",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-v4-flash",
    },
    "qwen": {
        "id": "qwen",
        "label": "通义千问",
        "key_label": "阿里云百炼 API Key",
        "description": "适合中文分析与结构化输出。",
        "recommended": False,
        "key_url": "https://help.aliyun.com/zh/model-studio/get-api-key",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
    },
    "openai": {
        "id": "openai",
        "label": "OpenAI",
        "key_label": "OpenAI API Key",
        "description": "支持文字、JSON 与主图分析。",
        "recommended": False,
        "key_url": "https://platform.openai.com/api-keys",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4.1-mini",
    },
}
CAPABILITY_TEST_IMAGE = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def _required_text(field_name, received_value):
    if not isinstance(received_value, str) or not received_value.strip():
        raise ValueError(
            f"{field_name} must be non-empty text: actual={received_value!r}"
        )
    return received_value.strip()


def _validated_base_url(base_url):
    normalized_url = _required_text("base_url", base_url).rstrip("/")
    parsed_url = urlsplit(normalized_url)
    if parsed_url.scheme not in ("http", "https") or not parsed_url.netloc:
        raise ValueError(
            f"base_url must be an absolute HTTP(S) URL: actual={base_url!r}"
        )
    if parsed_url.query or parsed_url.fragment:
        raise ValueError(
            f"base_url must not contain query or fragment: actual={base_url!r}"
        )
    return normalized_url


def _validated_vision_model(vision_model):
    if vision_model is None:
        return None
    return _required_text("vision_model", vision_model)


def _encrypted_api_key(api_key):
    protected_bytes = win32crypt.CryptProtectData(
        api_key.encode("utf-8"),
        DPAPI_DESCRIPTION,
        None,
        None,
        None,
        DPAPI_UI_FORBIDDEN,
    )
    return base64.b64encode(protected_bytes).decode("ascii")


def _decrypted_api_key(api_key_ciphertext, settings_path):
    if not isinstance(api_key_ciphertext, str) or not api_key_ciphertext:
        raise RuntimeError(
            f"AI settings contain invalid api_key_ciphertext: path={settings_path} "
            f"actual={api_key_ciphertext!r}"
        )
    try:
        protected_bytes = base64.b64decode(api_key_ciphertext, validate=True)
        _, api_key_bytes = win32crypt.CryptUnprotectData(
            protected_bytes,
            None,
            None,
            None,
            DPAPI_UI_FORBIDDEN,
        )
        api_key = api_key_bytes.decode("utf-8")
    except (binascii.Error, ValueError, pywintypes.error, UnicodeDecodeError) as exc:
        raise RuntimeError(
            f"Cannot decrypt AI API key with Windows DPAPI: path={settings_path}"
        ) from exc
    if not api_key:
        raise RuntimeError(f"Decrypted AI API key is empty: path={settings_path}")
    return api_key


def list_ai_provider_presets():
    public_fields = (
        "id", "label", "key_label", "description", "recommended", "key_url"
    )
    return [
        {field_name: preset[field_name] for field_name in public_fields}
        for preset in AI_PROVIDER_PRESETS.values()
    ]


def resolve_ai_provider(preset_id=None, base_url=None, model=None):
    if preset_id is not None:
        normalized_preset_id = _required_text("preset_id", preset_id)
        preset = AI_PROVIDER_PRESETS.get(normalized_preset_id)
        if preset is None:
            raise ValueError(f"unsupported preset_id: actual={preset_id!r}")
        return preset["base_url"], preset["model"], normalized_preset_id
    return _validated_base_url(base_url), _required_text("model", model), None


def _inferred_preset_id(base_url, model, saved_preset_id=None):
    if saved_preset_id == "selection-scene":
        saved_preset_id = "openai"
    if saved_preset_id in AI_PROVIDER_PRESETS:
        preset = AI_PROVIDER_PRESETS[saved_preset_id]
        if preset["base_url"] == base_url and preset["model"] == model:
            return saved_preset_id
    for preset_id, preset in AI_PROVIDER_PRESETS.items():
        if preset["base_url"] == base_url and preset["model"] == model:
            return preset_id
    return None


def _public_ai_settings(base_url, model, capabilities=None, preset_id=None):
    public_settings = {
        "base_url": base_url,
        "model": model,
        "api_key_configured": True,
        "capabilities": capabilities,
    }
    inferred_preset_id = _inferred_preset_id(base_url, model, preset_id)
    if inferred_preset_id is not None:
        public_settings["preset_id"] = inferred_preset_id
    return public_settings


def _write_settings_payload(settings_path, settings_payload):
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    pending_settings_path = settings_path.with_suffix(".json.pending")
    pending_settings_path.write_text(
        json.dumps(settings_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    pending_settings_path.replace(settings_path)


def save_ai_settings(
    application_data_directory,
    base_url,
    model,
    _legacy_vision_model,
    api_key,
    preset_id=None,
):
    normalized_base_url, normalized_model, normalized_preset_id = resolve_ai_provider(
        preset_id,
        base_url,
        model,
    )
    normalized_api_key = _required_text("api_key", api_key)

    settings_path = Path(application_data_directory) / SETTINGS_RELATIVE_PATH
    settings_payload = {
        "version": SETTINGS_VERSION,
        "base_url": normalized_base_url,
        "model": normalized_model,
        "preset_id": normalized_preset_id,
        "capabilities": None,
        "api_key_protection": "windows-dpapi",
        "api_key_ciphertext": _encrypted_api_key(normalized_api_key),
    }
    _write_settings_payload(settings_path, settings_payload)
    return _public_ai_settings(
        normalized_base_url,
        normalized_model,
        preset_id=normalized_preset_id,
    )


def read_ai_settings(application_data_directory):
    settings_path = Path(application_data_directory) / SETTINGS_RELATIVE_PATH
    if not settings_path.is_file():
        raise FileNotFoundError(f"AI settings file not found: path={settings_path}")
    try:
        settings_payload = json.loads(settings_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"AI settings file contains invalid JSON: path={settings_path}"
        ) from exc
    if not isinstance(settings_payload, dict):
        raise RuntimeError(
            f"AI settings must be a JSON object: path={settings_path} "
            f"actual={settings_payload!r}"
        )
    settings_version = settings_payload.get("version")
    if settings_version not in (1, SETTINGS_VERSION):
        raise RuntimeError(
            f"Unsupported AI settings version: path={settings_path} "
            f"actual={settings_payload.get('version')!r}"
        )
    if settings_payload.get("api_key_protection") != "windows-dpapi":
        raise RuntimeError(
            f"Unsupported API key protection: path={settings_path} "
            f"actual={settings_payload.get('api_key_protection')!r}"
        )

    base_url = _validated_base_url(settings_payload.get("base_url"))
    if settings_version == 1:
        legacy_text_model = _required_text(
            "text_model", settings_payload.get("text_model")
        )
        legacy_vision_model = _validated_vision_model(
            settings_payload.get("vision_model")
        )
        model = legacy_vision_model or legacy_text_model
    else:
        model = _required_text("model", settings_payload.get("model"))
    api_key = _decrypted_api_key(
        settings_payload.get("api_key_ciphertext"),
        settings_path,
    )
    if settings_version == 1:
        settings_payload = {
            "version": SETTINGS_VERSION,
            "base_url": base_url,
            "model": model,
            "capabilities": None,
            "api_key_protection": "windows-dpapi",
            "api_key_ciphertext": settings_payload["api_key_ciphertext"],
        }
        _write_settings_payload(settings_path, settings_payload)
    capabilities = settings_payload.get("capabilities")
    if capabilities is not None and not isinstance(capabilities, dict):
        raise RuntimeError(
            f"AI settings contain invalid capabilities: path={settings_path} "
            f"actual={capabilities!r}"
        )
    return {
        "base_url": base_url,
        "model": model,
        "preset_id": _inferred_preset_id(
            base_url,
            model,
            settings_payload.get("preset_id"),
        ),
        "capabilities": capabilities,
        "api_key": api_key,
    }


def _request_chat_completion(
    settings,
    messages,
    *,
    max_tokens,
    temperature,
    operation_name,
    timeout_seconds=CONNECTION_TIMEOUT_SECONDS,
    timeout_retries=0,
):
    connection_url = f"{settings['base_url']}/chat/completions"
    for attempt in range(timeout_retries + 1):
        try:
            response = httpx.post(
                connection_url,
                headers={
                    "Authorization": f"Bearer {settings['api_key']}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings["model"],
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                },
                timeout=timeout_seconds,
            )
            break
        except httpx.TimeoutException as exc:
            if attempt < timeout_retries:
                continue
            raise RuntimeError(
                f"{operation_name} timed out: base_url={settings['base_url']!r}"
            ) from exc
        except httpx.RequestError as exc:
            raise RuntimeError(
                f"{operation_name} failed: base_url={settings['base_url']!r} "
                f"error={type(exc).__name__}"
            ) from exc

    if not 200 <= response.status_code < 300:
        raise RuntimeError(f"AI service request failed: status={response.status_code}")
    try:
        response_payload = response.json()
    except ValueError as exc:
        raise RuntimeError(
            f"AI service returned non-JSON response: status={response.status_code}"
        ) from exc

    choices = response_payload.get("choices") if isinstance(response_payload, dict) else None
    if not isinstance(choices, list) or not choices:
        raise RuntimeError(
            f"AI service returned incompatible response: choices={choices!r}"
        )
    first_choice = choices[0]
    message = first_choice.get("message") if isinstance(first_choice, dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError(
            f"AI service returned incompatible message content: actual={content!r}"
        )
    return content.strip()


def _validated_messages(messages):
    if not isinstance(messages, list) or not messages:
        raise ValueError(f"messages must be a non-empty list: actual={messages!r}")
    validated_messages = []
    for message_index, message in enumerate(messages):
        if not isinstance(message, dict):
            raise ValueError(
                f"message must be an object: index={message_index} actual={message!r}"
            )
        role = message.get("role")
        content = message.get("content")
        if role not in ("system", "user", "assistant"):
            raise ValueError(
                f"message role is unsupported: index={message_index} actual={role!r}"
            )
        if not isinstance(content, str) or not content.strip():
            raise ValueError(
                f"message content must be non-empty text: "
                f"index={message_index} actual={content!r}"
            )
        validated_messages.append({"role": role, "content": content.strip()})
    return validated_messages


def request_ai_text(
    application_data_directory,
    messages,
    *,
    timeout_seconds=CONNECTION_TIMEOUT_SECONDS,
    timeout_retries=0,
):
    settings = read_ai_settings(application_data_directory)
    return _request_chat_completion(
        settings,
        _validated_messages(messages),
        max_tokens=TEXT_COMPLETION_MAX_TOKENS,
        temperature=0.2,
        operation_name="AI request",
        timeout_seconds=timeout_seconds,
        timeout_retries=timeout_retries,
    )


def request_ai_vision(application_data_directory, prompt, image_items):
    normalized_prompt = _required_text("prompt", prompt)
    if not isinstance(image_items, list) or not image_items:
        raise ValueError(f"image_items must be a non-empty list: actual={image_items!r}")
    if len(image_items) > 8:
        raise ValueError(f"image_items may contain at most 8 images: actual={len(image_items)}")
    settings = read_ai_settings(application_data_directory)
    if not ((settings.get("capabilities") or {}).get("vision") or {}).get("supported"):
        raise RuntimeError("Configured model has not passed the image capability test")
    content = [{"type": "text", "text": normalized_prompt}]
    for image_index, image_item in enumerate(image_items):
        if not isinstance(image_item, dict):
            raise ValueError(
                f"image item must be an object: index={image_index} actual={image_item!r}"
            )
        image_url = _required_text(
            f"image_items[{image_index}].image_url",
            image_item.get("image_url"),
        )
        parsed = urlsplit(image_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError(
                f"image URL must be absolute HTTPS: index={image_index} actual={image_url!r}"
            )
        content.append({"type": "image_url", "image_url": {"url": image_url}})
    return _request_chat_completion(
        settings,
        [{"role": "user", "content": content}],
        max_tokens=VISION_COMPLETION_MAX_TOKENS,
        temperature=0.2,
        operation_name="AI vision request",
    )


def test_ai_connection(application_data_directory):
    settings = read_ai_settings(application_data_directory)
    content = _request_chat_completion(
        settings,
        [
            {
                "role": "user",
                "content": "请只回复 OK，用于验证模型连接。",
            }
        ],
        max_tokens=8,
        temperature=0,
        operation_name="AI connection",
    )
    capabilities = {
        "text": {"supported": True},
        "structured_json": {"supported": False},
        "vision": {"supported": False},
    }
    try:
        structured_content = _request_chat_completion(
            settings,
            [
                {
                    "role": "user",
                    "content": '请只返回 JSON：{"ok":true}',
                }
            ],
            max_tokens=24,
            temperature=0,
            operation_name="AI structured output capability",
        )
        structured_payload = json.loads(
            structured_content.removeprefix("```json").removesuffix("```").strip()
        )
        capabilities["structured_json"] = {
            "supported": isinstance(structured_payload, dict)
            and structured_payload.get("ok") is True
        }
    except (RuntimeError, ValueError, json.JSONDecodeError) as exc:
        capabilities["structured_json"] = {
            "supported": False,
            "reason": str(exc),
        }
    try:
        vision_content = _request_chat_completion(
            settings,
            [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "请只回复 IMAGE_OK。"},
                        {
                            "type": "image_url",
                            "image_url": {"url": CAPABILITY_TEST_IMAGE},
                        },
                    ],
                }
            ],
            max_tokens=16,
            temperature=0,
            operation_name="AI vision capability",
        )
        capabilities["vision"] = {
            "supported": "IMAGE_OK" in vision_content.upper()
        }
    except RuntimeError as exc:
        capabilities["vision"] = {"supported": False, "reason": str(exc)}

    settings_path = Path(application_data_directory) / SETTINGS_RELATIVE_PATH
    stored_payload = json.loads(settings_path.read_text(encoding="utf-8"))
    stored_payload["capabilities"] = capabilities
    _write_settings_payload(settings_path, stored_payload)
    result = {
        "connected": True,
        "model": settings["model"],
        "response_preview": content[:80],
        "capabilities": capabilities,
    }
    if not capabilities["vision"]["supported"]:
        result["vision_notice"] = "视觉分析未执行"
    return result
