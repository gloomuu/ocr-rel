import asyncio
import io
from unittest.mock import patch

import fitz
import pytest
from fastapi.testclient import TestClient

from ocr_rel.config import settings
from ocr_rel.main import app
from ocr_rel.models.schemas import TaskStage
from ocr_rel.tasks.runner import background_runner


class SlowFakeOcrEngine:
    def __init__(self) -> None:
        self._delay = 0.3

    async def recognize_image(self, image) -> str:
        await asyncio.sleep(self._delay)
        return (
            "营业执照\n"
            "名称：测试售电有限公司\n"
            "统一社会信用代码：91410000MA9ABCDEF0\n"
            "登记机关：郑州市市场监督管理局"
        )

    async def recognize_images(self, images) -> str:
        return await self.recognize_image(None)


def _make_pdf_bytes() -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "sample")
    return doc.tobytes()


def _submit_task(client: TestClient, suffix: str) -> str:
    pdf_bytes = _make_pdf_bytes()
    files = {"file": (f"license-{suffix}.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
    data = {
        "registration_id": f"reg-queue-{suffix}",
        "doc_type": "1",
        "attachment_name": "营业执照",
        "ocr_engine": "paddle",
    }
    response = client.post("/api/v1/test/recognize", files=files, data=data)
    assert response.status_code == 200
    return response.json()["data"]["taskId"]


@patch("ocr_rel.services.recognition_service.get_ocr_engine", return_value=SlowFakeOcrEngine())
def test_tasks_queue_when_concurrency_full(mock_engine, client: TestClient) -> None:
    background_runner.configure(1)

    first_id = _submit_task(client, "001")
    second_id = _submit_task(client, "002")

    import time

    deadline = time.time() + 5
    saw_queued = False
    while time.time() < deadline:
        second = client.get(f"/api/v1/test/tasks/{second_id}").json()["data"]
        first = client.get(f"/api/v1/test/tasks/{first_id}").json()["data"]
        if second["stage"] == TaskStage.QUEUED:
            saw_queued = True
            break
        if first["status"] == "success" and second["status"] in {"success", "running"}:
            break
        time.sleep(0.05)

    second = client.get(f"/api/v1/test/tasks/{second_id}").json()["data"]
    assert saw_queued or second["stage"] in {TaskStage.QUEUED, TaskStage.DOWNLOADING, TaskStage.OCR}

    deadline = time.time() + 10
    while time.time() < deadline:
        first = client.get(f"/api/v1/test/tasks/{first_id}").json()["data"]
        second = client.get(f"/api/v1/test/tasks/{second_id}").json()["data"]
        if first["status"] == "success" and second["status"] == "success":
            break
        time.sleep(0.1)

    first = client.get(f"/api/v1/test/tasks/{first_id}").json()["data"]
    second = client.get(f"/api/v1/test/tasks/{second_id}").json()["data"]
    assert first["status"] == "success"
    assert second["status"] == "success"


def test_health_includes_queue_stats(client: TestClient) -> None:
    response = client.get("/health")
    payload = response.json()
    assert payload["maxConcurrent"] == 2
    assert "running" in payload
    assert "waiting" in payload
    assert "available" in payload
