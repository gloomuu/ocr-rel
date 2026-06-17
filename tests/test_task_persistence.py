import io
from unittest.mock import AsyncMock, patch

import fitz
import pytest
from fastapi.testclient import TestClient

from ocr_rel.config import settings
from ocr_rel.main import app


@pytest.fixture(autouse=True)
def use_regex_in_api_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "extraction_strategy", "regex")
    monkeypatch.setattr(settings, "llm_api_key", "")


class FakeOcrEngine:
    async def recognize_image(self, image) -> str:
        return (
            "名称：测试售电有限公司\n"
            "统一社会信用代码：91410000MA9ABCDEF0\n"
            "住所：河南省郑州市金水区某某路100号\n"
            "成立日期：2020年05月18日\n"
            "登记机关：郑州市市场监督管理局\n"
            "核准日期：2023年01月10日"
        )

    async def recognize_images(self, images) -> str:
        return await self.recognize_image(None)


def _make_pdf_bytes(text: str = "sample") -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    return doc.tobytes()


def _wait_task(client: TestClient, task_id: str) -> dict:
    import time

    for _ in range(30):
        task_response = client.get(f"/api/v1/test/tasks/{task_id}")
        data = task_response.json()["data"]
        if data["status"] in {"success", "failed"}:
            return data
        time.sleep(0.1)
    return client.get(f"/api/v1/test/tasks/{task_id}").json()["data"]


@patch("ocr_rel.services.recognition_service.get_ocr_engine", return_value=FakeOcrEngine())
def test_task_list_and_callback(mock_engine, client: TestClient) -> None:
    pdf_bytes = _make_pdf_bytes()
    files = {"file": ("license.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
    data = {
        "registration_id": "reg-persist-001",
        "doc_type": "1",
        "attachment_name": "营业执照",
        "ocr_engine": "paddle",
    }
    response = client.post("/api/v1/test/recognize", files=files, data=data)
    assert response.status_code == 200
    task_id = response.json()["data"]["taskId"]

    final = _wait_task(client, task_id)
    assert final["status"] == "success"

    list_resp = client.get("/api/v1/tasks?page=1&pageSize=10")
    assert list_resp.status_code == 200
    list_data = list_resp.json()["data"]
    assert list_data["total"] >= 1
    matched = next(item for item in list_data["items"] if item["taskId"] == task_id)
    assert matched["docType"] == 1
    assert matched["docTypeName"] == "营业执照"
    assert matched["fileFormat"] == "PDF"
    assert matched["fileSize"] == len(pdf_bytes)
    assert matched["fileName"] == "license.pdf"
    assert matched["hasStoredFile"] is True
    assert matched["durationMs"] is not None
    assert matched["durationMs"] >= 0

    detail_resp = client.get(f"/api/v1/tasks/{task_id}")
    assert detail_resp.status_code == 200
    detail = detail_resp.json()["data"]
    assert detail["registrationId"] == "reg-persist-001"
    assert detail["createdAt"]
    assert detail["updatedAt"]

    callback_resp = client.get(f"/api/v1/tasks/{task_id}/callback")
    assert callback_resp.status_code == 200
    callback = callback_resp.json()["data"]
    assert callback["registrationId"] == "reg-persist-001"
    assert callback["results"][0]["type"] == 1


@patch("ocr_rel.services.recognition_service.get_ocr_engine", return_value=FakeOcrEngine())
def test_task_persists_across_restarts(mock_engine, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "restart.db"
    monkeypatch.setattr(settings, "database_path", str(db_path))

    with TestClient(app) as first_client:
        pdf_bytes = _make_pdf_bytes()
        files = {"file": ("license.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
        data = {
            "registration_id": "reg-restart-001",
            "doc_type": "1",
            "attachment_name": "营业执照",
            "ocr_engine": "paddle",
        }
        response = first_client.post("/api/v1/test/recognize", files=files, data=data)
        task_id = response.json()["data"]["taskId"]
        final = _wait_task(first_client, task_id)
        assert final["status"] == "success"

    with TestClient(app) as second_client:
        detail_resp = second_client.get(f"/api/v1/tasks/{task_id}")
        assert detail_resp.status_code == 200
        assert detail_resp.json()["data"]["status"] == "success"

        filtered = second_client.get(
            "/api/v1/tasks",
            params={"registrationId": "reg-restart-001"},
        )
        assert filtered.status_code == 200
        items = filtered.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["taskId"] == task_id
        assert items[0]["hasResult"] is True
