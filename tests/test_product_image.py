import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import _archive_product_images, application


class ProductImageTests(unittest.TestCase):
    @patch("app.httpx.Client")
    def test_archives_classified_product_images_locally(self, client_factory):
        image_url = "https://img.alicdn.com/img/main.webp"
        client = client_factory.return_value
        client.get.return_value = httpx.Response(
            200,
            content=b"example-webp-bytes",
            headers={"content-type": "image/webp"},
            request=httpx.Request("GET", image_url),
        )
        with TemporaryDirectory() as directory:
            archived = _archive_product_images(
                Path(directory) / "assets",
                [{"url": image_url, "kind": "main"}],
            )

            self.assertEqual("saved", archived[0]["local_status"])
            self.assertEqual(1, archived[0]["sequence"])
            self.assertTrue(Path(archived[0]["local_ref"]).is_file())
            self.assertEqual(b"example-webp-bytes", Path(archived[0]["local_ref"]).read_bytes())

    @patch("app.httpx.get")
    def test_downloads_supported_taobao_image_as_attachment(self, read_image):
        image_url = "https://img.alicdn.com/img/product.webp"
        read_image.return_value = httpx.Response(
            200,
            content=b"example-webp-bytes",
            headers={"content-type": "image/webp"},
            request=httpx.Request("GET", image_url),
        )

        with TestClient(application) as client:
            response = client.get(
                "/api/product-image",
                params={"image_url": image_url, "item_id": "970893897222"},
            )

        self.assertEqual(200, response.status_code)
        self.assertEqual("image/webp", response.headers["content-type"])
        self.assertIn(
            'filename="taobao-main-image-970893897222.webp"',
            response.headers["content-disposition"],
        )
        self.assertEqual(b"example-webp-bytes", response.content)

    @patch("app.httpx.get")
    def test_rejects_non_taobao_image_host_before_request(self, read_image):
        with TestClient(application) as client:
            response = client.get(
                "/api/product-image",
                params={"image_url": "https://example.com/private.jpg"},
            )

        self.assertEqual(422, response.status_code)
        self.assertEqual("invalid_product_image_url", response.json()["detail"]["code"])
        read_image.assert_not_called()

    @patch("app.httpx.get")
    def test_rejects_non_image_response(self, read_image):
        image_url = "https://img.alicdn.com/img/product.jpg"
        read_image.return_value = httpx.Response(
            200,
            content=b"not-an-image",
            headers={"content-type": "text/html"},
            request=httpx.Request("GET", image_url),
        )

        with TestClient(application) as client:
            response = client.get(
                "/api/product-image",
                params={"image_url": image_url},
            )

        self.assertEqual(502, response.status_code)
        self.assertEqual("product_image_type_invalid", response.json()["detail"]["code"])


if __name__ == "__main__":
    unittest.main()
