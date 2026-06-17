import asyncio

from PIL import Image

from ocr_rel.logging_config import get_logger
from ocr_rel.ocr.base import OcrEngine

logger = get_logger(__name__)


class PaddleOcrEngine(OcrEngine):
    def __init__(self) -> None:
        self._ocr = None
        self._lock = asyncio.Lock()

    def _get_ocr(self):
        if self._ocr is None:
            from paddleocr import PaddleOCR

            self._ocr = PaddleOCR(use_angle_cls=True, lang="ch", show_log=False)
        return self._ocr

    async def recognize_image(self, image: Image.Image) -> str:
        async with self._lock:
            return await asyncio.to_thread(self._recognize_sync, image)

    def _recognize_sync(self, image: Image.Image) -> str:
        import numpy as np

        ocr = self._get_ocr()
        result = ocr.ocr(np.array(image), cls=True)
        if not result or not result[0]:
            return ""

        lines: list[str] = []
        for item in result[0]:
            if item and len(item) >= 2 and item[1] and item[1][0]:
                lines.append(str(item[1][0]))
        return "\n".join(lines)
