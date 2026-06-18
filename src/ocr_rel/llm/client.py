from __future__ import annotations

import json
import re
from typing import Any

import httpx
from PIL import Image

from ocr_rel.config import settings
from ocr_rel.llm.images import image_to_data_url
from ocr_rel.logging_config import get_logger

logger = get_logger(__name__)


class LlmClient:
    def __init__(self) -> None:
        self._base_url = settings.llm_base_url.rstrip("/")
        self._api_key = settings.llm_api_key
        self._model = settings.llm_model
        self._timeout = settings.llm_timeout
        self._temperature = settings.llm_temperature

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key)

    async def chat_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        images: list[Image.Image] | None = None,
    ) -> dict[str, Any]:
        if not self.is_configured:
            raise ValueError("LLM API key is not configured")

        if images:
            user_content: str | list[dict[str, Any]] = [{"type": "text", "text": user_prompt}]
            for image in images:
                user_content.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": image_to_data_url(image)},
                    }
                )
        else:
            user_content = user_prompt

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "temperature": self._temperature,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        url = f"{self._base_url}/chat/completions"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            body = response.json()

        content = body["choices"][0]["message"]["content"]
        return _parse_json_content(content)


def _parse_json_content(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise ValueError(f"LLM response is not valid JSON: {content}") from exc
        parsed = json.loads(match.group(0))

    if not isinstance(parsed, dict):
        raise ValueError("LLM response JSON must be an object")
    return parsed
