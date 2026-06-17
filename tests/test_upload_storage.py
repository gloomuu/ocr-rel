import io
from unittest.mock import patch

import fitz
import pytest
from fastapi.testclient import TestClient

from ocr_rel.config import settings


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


def test_upload_rejects_oversized_file(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "max_upload_file_size", 1024)
    oversized = b"x" * 1025
    files = {"file": ("big.pdf", io.BytesIO(oversized), "application/pdf")}
    data = {
        "registration_id": "reg-size-001",
        "doc_type": "1",
        "attachment_name": "营业执照",
        "ocr_engine": "paddle",
    }
    response = client.post("/api/v1/test/recognize", files=files, data=data)
    assert response.status_code == 400
    assert "exceeds upload limit" in response.json()["detail"]


@patch("ocr_rel.services.recognition_service.get_ocr_engine", return_value=FakeOcrEngine())
def test_task_file_preview(mock_engine, client: TestClient) -> None:
    pdf_bytes = _make_pdf_bytes()
    files = {"file": ("license.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
    data = {
        "registration_id": "reg-preview-001",
        "doc_type": "1",
        "attachment_name": "营业执照",
        "ocr_engine": "paddle",
    }
    response = client.post("/api/v1/test/recognize", files=files, data=data)
    assert response.status_code == 200
    task_id = response.json()["data"]["taskId"]

    list_resp = client.get("/api/v1/tasks?page=1&pageSize=10")
    matched = next(item for item in list_resp.json()["data"]["items"] if item["taskId"] == task_id)
    assert matched["fileName"] == "license.pdf"
    assert matched["hasStoredFile"] is True

    file_resp = client.get(f"/api/v1/tasks/{task_id}/file")
    assert file_resp.status_code == 200
    assert file_resp.content == pdf_bytes
    assert file_resp.headers["content-type"].startswith("application/pdf")
