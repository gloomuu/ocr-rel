from abc import ABC, abstractmethod

from PIL import Image


class OcrEngine(ABC):
    @abstractmethod
    async def recognize_image(self, image: Image.Image) -> str:
        """Return OCR text for a single page image."""

    async def recognize_images(self, images: list[Image.Image]) -> str:
        parts: list[str] = []
        for index, image in enumerate(images, start=1):
            text = await self.recognize_image(image)
            if text.strip():
                parts.append(text.strip())
        return "\n".join(parts)
