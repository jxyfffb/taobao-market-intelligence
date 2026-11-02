import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
import httpx


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import application
from src.ai_client import (
    read_ai_settings,
    request_ai_text,
    request_ai_vision,
    save_ai_settings,
    test_ai_connection,
)


class AiClientTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = TemporaryDirectory()
        self.application_data_directory = Path(self.temporary_directory.name)
        self.api_key = "sk-test-secret-value-123456"

    def tearDown(self):
        self.temporary_directory.cleanup()

    def save_settings(self):
        return save_ai_settings(
            self.application_data_directory,
            "https://api.example.com/v1/",
            "multimodal-model",
            None,
            self.api_key,
        )

    def test_settings_file_uses_dpapi_ciphertext_and_round_trips(self):
        public_settings = self.save_settings()

        settings_path = (
            self.application_data_directory / "settings" / "ai-provider.json"
        )
        raw_settings = settings_path.read_text(encoding="utf-8")
        self.assertNotIn(self.api_key, raw_settings)
        stored_settings = json.loads(raw_settings)
        self.assertEqual("windows-dpapi", stored_settings["api_key_protection"])
        self.assertTrue(stored_settings["api_key_ciphertext"])
        self.assertNotIn("api_key", public_settings)
        self.assertEqual(
            {
                "base_url": "https://api.example.com/v1",
                "model": "multimodal-model",
                "api_key_configured": True,
                "capabilities": None,
            },
            public_settings,
        )

        private_settings = read_ai_settings(self.application_data_directory)
        self.assertEqual(self.api_key, private_settings["api_key"])
        self.assertEqual("https://api.example.com/v1", private_settings["base_url"])
        self.assertEqual("multimodal-model", private_settings["model"])

    def test_legacy_two_model_settings_migrate_to_one_multimodal_model(self):
        self.save_settings()
        settings_path = self.application_data_directory / "settings" / "ai-provider.json"
        stored = json.loads(settings_path.read_text(encoding="utf-8"))
        stored.update(
            {
                "version": 1,
                "text_model": "legacy-text-model",
                "vision_model": "legacy-vision-model",
            }
        )
        stored.pop("model")
        settings_path.write_text(json.dumps(stored), encoding="utf-8")

        migrated = read_ai_settings(self.application_data_directory)

        self.assertEqual("legacy-vision-model", migrated["model"])
        rewritten = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertEqual(2, rewritten["version"])
        self.assertEqual("legacy-vision-model", rewritten["model"])
        self.assertNotIn("text_model", rewritten)
        self.assertNotIn("vision_model", rewritten)

    def test_settings_boundary_rejects_received_invalid_values(self):
        invalid_settings = (
            ("ftp://api.example.com", "model", None, self.api_key, "base_url"),
            ("https://api.example.com/v1", "", None, self.api_key, "model"),
            ("https://api.example.com/v1", "model", None, "", "api_key"),
        )
        for base_url, text_model, vision_model, api_key, expected_field in invalid_settings:
            with self.subTest(expected_field=expected_field):
                with self.assertRaisesRegex(ValueError, expected_field):
                    save_ai_settings(
                        self.application_data_directory,
                        base_url,
                        text_model,
                        vision_model,
                        api_key,
                    )

    def test_openai_compatible_connection_uses_saved_key_without_returning_it(self):
        self.save_settings()
        request = httpx.Request("POST", "https://api.example.com/v1/chat/completions")
        responses = [
            httpx.Response(200, json={"choices": [{"message": {"content": "OK"}}]}, request=request),
            httpx.Response(200, json={"choices": [{"message": {"content": '{"ok":true}'}}]}, request=request),
            httpx.Response(200, json={"choices": [{"message": {"content": "IMAGE_OK"}}]}, request=request),
        ]

        with patch("src.ai_client.httpx.post", side_effect=responses) as post:
            connection_result = test_ai_connection(self.application_data_directory)

        self.assertTrue(connection_result["connected"])
        self.assertEqual("multimodal-model", connection_result["model"])
        self.assertTrue(connection_result["capabilities"]["text"]["supported"])
        self.assertTrue(connection_result["capabilities"]["structured_json"]["supported"])
        self.assertTrue(connection_result["capabilities"]["vision"]["supported"])
        self.assertNotIn(self.api_key, repr(connection_result))
        self.assertEqual(3, post.call_count)
        request_args = post.call_args_list[0]
        self.assertEqual(
            "https://api.example.com/v1/chat/completions",
            request_args.args[0],
        )
        self.assertEqual(
            f"Bearer {self.api_key}",
            request_args.kwargs["headers"]["Authorization"],
        )
        self.assertEqual("multimodal-model", request_args.kwargs["json"]["model"])
        vision_content = post.call_args_list[2].kwargs["json"]["messages"][0]["content"]
        self.assertEqual("image_url", vision_content[1]["type"])
        self.assertTrue(vision_content[1]["image_url"]["url"].startswith("data:image/png;base64,"))

    def test_text_only_model_reports_visual_skip_without_failing_connection(self):
        self.save_settings()
        request = httpx.Request("POST", "https://api.example.com/v1/chat/completions")
        responses = [
            httpx.Response(200, json={"choices": [{"message": {"content": "OK"}}]}, request=request),
            httpx.Response(200, json={"choices": [{"message": {"content": '{"ok":true}'}}]}, request=request),
            httpx.Response(400, text="image input unsupported", request=request),
        ]

        with patch("src.ai_client.httpx.post", side_effect=responses):
            result = test_ai_connection(self.application_data_directory)

        self.assertTrue(result["connected"])
        self.assertTrue(result["capabilities"]["text"]["supported"])
        self.assertFalse(result["capabilities"]["vision"]["supported"])
        self.assertEqual("视觉分析未执行", result["vision_notice"])

    def test_vision_request_uses_the_same_verified_model(self):
        self.save_settings()
        settings_path = self.application_data_directory / "settings" / "ai-provider.json"
        stored = json.loads(settings_path.read_text(encoding="utf-8"))
        stored["capabilities"] = {
            "text": {"supported": True},
            "structured_json": {"supported": True},
            "vision": {"supported": True},
        }
        settings_path.write_text(json.dumps(stored), encoding="utf-8")
        response = httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"products":[]}'}}]},
            request=httpx.Request("POST", "https://api.example.com/v1/chat/completions"),
        )

        with patch("src.ai_client.httpx.post", return_value=response) as post:
            content = request_ai_vision(
                self.application_data_directory,
                "分析主图",
                [{"image_url": "https://img.alicdn.com/main.jpg"}],
            )

        self.assertEqual('{"products":[]}', content)
        request_payload = post.call_args.kwargs["json"]
        self.assertEqual("multimodal-model", request_payload["model"])
        self.assertEqual("image_url", request_payload["messages"][0]["content"][1]["type"])

    def test_text_request_can_use_long_timeout_and_retry_once(self):
        self.save_settings()
        request = httpx.Request("POST", "https://api.example.com/v1/chat/completions")
        response = httpx.Response(
            200,
            json={"choices": [{"message": {"content": "report"}}]},
            request=request,
        )

        with patch(
            "src.ai_client.httpx.post",
            side_effect=[httpx.TimeoutException("slow", request=request), response],
        ) as post:
            content = request_ai_text(
                self.application_data_directory,
                [{"role": "user", "content": "生成完整报告"}],
                timeout_seconds=90,
                timeout_retries=1,
            )

        self.assertEqual("report", content)
        self.assertEqual(2, post.call_count)
        self.assertEqual(90, post.call_args.kwargs["timeout"])

    def test_connection_fails_fast_for_timeout_limit_non_json_and_bad_protocol(self):
        self.save_settings()
        request = httpx.Request("POST", "https://api.example.com/v1/chat/completions")
        failures = (
            (
                httpx.TimeoutException("slow", request=request),
                r"AI connection timed out: base_url='https://api.example.com/v1'",
            ),
            (
                httpx.Response(429, text="limited", request=request),
                r"AI service request failed: status=429",
            ),
            (
                httpx.Response(200, text="not-json", request=request),
                r"AI service returned non-JSON response: status=200",
            ),
            (
                httpx.Response(200, json={"choices": []}, request=request),
                r"AI service returned incompatible response: choices=\[\]",
            ),
        )
        for response_or_error, expected_message in failures:
            with self.subTest(expected_message=expected_message):
                if isinstance(response_or_error, Exception):
                    mocked_post = patch(
                        "src.ai_client.httpx.post",
                        side_effect=response_or_error,
                    )
                else:
                    mocked_post = patch(
                        "src.ai_client.httpx.post",
                        return_value=response_or_error,
                    )
                with mocked_post:
                    with self.assertRaisesRegex(RuntimeError, expected_message) as raised:
                        test_ai_connection(self.application_data_directory)
                self.assertNotIn(self.api_key, str(raised.exception))

    def test_settings_and_connection_api_never_echo_full_key(self):
        previous_data_directory = application.state.application_data_directory
        application.state.application_data_directory = self.application_data_directory
        try:
            with TestClient(application) as client:
                save_response = client.put(
                    "/api/settings/ai",
                    json={
                        "base_url": "https://api.example.com/v1",
                        "model": "multimodal-model",
                        "api_key": self.api_key,
                    },
                )
                read_response = client.get("/api/settings/ai")
                with patch(
                    "app.test_ai_connection",
                    return_value={
                        "connected": True,
                        "model": "multimodal-model",
                        "response_preview": "OK",
                    },
                ):
                    test_response = client.post("/api/settings/ai/test")
        finally:
            application.state.application_data_directory = previous_data_directory

        self.assertEqual(200, save_response.status_code)
        self.assertEqual(200, read_response.status_code)
        self.assertEqual(200, test_response.status_code)
        self.assertNotIn(self.api_key, save_response.text)
        self.assertNotIn(self.api_key, read_response.text)
        self.assertNotIn(self.api_key, test_response.text)
        self.assertTrue(save_response.json()["api_key_configured"])
        self.assertTrue(read_response.json()["api_key_configured"])


if __name__ == "__main__":
    unittest.main()
