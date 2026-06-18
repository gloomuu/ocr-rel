from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image

from ocr_rel.ocr.local_engine import LocalHttpOcrClient, LocalHttpOcrEngine


def test_blocks_to_text_filters_low_confidence() -> None:
    client = LocalHttpOcrClient(confidence_threshold=0.6)
    blocks = [
        {"words": "深圳市市场监督管理局", "confidence": 0.95},
        {"words": "噪声", "confidence": 0.5},
    ]
    assert client.blocks_to_text(blocks) == "深圳市市场监督管理局"


def test_encode_image() -> None:
    encoded = LocalHttpOcrClient.encode_image(Image.new("RGB", (8, 8), color=(0, 128, 255)))
    assert encoded


@pytest.mark.asyncio
async def test_recognize_blocks_posts_to_ocr_service() -> None:
    client = LocalHttpOcrClient(server_url="http://127.0.0.1:6006")

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "result": {
            "words_block_list": [
                {"words": "深圳壹创国际设计股份有限公司", "confidence": 0.92},
            ]
        }
    }

    mock_http = AsyncMock()
    mock_http.post = AsyncMock(return_value=mock_response)
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=None)

    with patch("ocr_rel.ocr.local_engine.httpx.AsyncClient", return_value=mock_http):
        blocks = await client.recognize_blocks("base64-image")

    assert blocks[0]["words"] == "深圳壹创国际设计股份有限公司"
    mock_http.post.assert_awaited_once_with(
        "http://127.0.0.1:6006/ocr/single",
        json={"image": "base64-image"},
    )


@pytest.mark.asyncio
async def test_local_http_ocr_engine() -> None:
    fake_client = LocalHttpOcrClient()

    async def fake_recognize(image: Image.Image) -> str:
        assert image.size == (10, 10)
        return "识别文本"

    fake_client.recognize_image = fake_recognize  # type: ignore[method-assign]
    text = await LocalHttpOcrEngine(client=fake_client).recognize_image(Image.new("RGB", (10, 10)))
    assert text == "识别文本"


@pytest.mark.asyncio
async def test_recognize_image_composes_blocks() -> None:
    client = LocalHttpOcrClient()

    with patch.object(
        client,
        "recognize_blocks",
        return_value=[{"words": "测试公司", "confidence": 0.99}],
    ):
        text = await client.recognize_image(Image.new("RGB", (1, 1)))

    assert text == "测试公司"
