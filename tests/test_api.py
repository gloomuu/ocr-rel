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
            "营业执照\n"
            "名称：测试售电有限公司\n"
            "统一社会信用代码：91410000MA9ABCDEF0\n"
            "住所：河南省郑州市金水区某某路100号\n"
            "成立日期：2020年05月18日\n"
            "登记机关：郑州市市场监督管理局\n"
            "核准日期：2023年01月10日"
        )

    async def recognize_images(self, images) -> str:
        return await self.recognize_image(None)


class FakeIdCardOcrEngine:
    async def recognize_image(self, image) -> str:
        return (
            "中华人民共和国\n"
            "居民身份证\n"
            "姓名张三\n"
            "性别男民族汉\n"
            "公民身份号码410105199001011234"
        )

    async def recognize_images(self, images) -> str:
        return await self.recognize_image(None)


class FakeAuditReportOcrEngine:
    _cover_text = (
        "审计报告\n"
        "被审计单位：河南测试售电有限公司\n"
        "会计师事务所：立信会计师事务所（特殊普通合伙）\n"
        "报告文号：信会师报字[2023]第ZA12345号\n"
        "我们审计了河南测试售电有限公司财务报表"
    )
    _balance_sheet_text = (
        "资产负债表\n"
        "期末余额 期初余额\n"
        "资产总计 25,000,000.00 20,000,000.00"
    )

    def __init__(self) -> None:
        self._index = 0

    async def recognize_image(self, image) -> str:
        if self._index == 0:
            self._index += 1
            return self._cover_text
        if self._index == 1:
            self._index += 1
            return self._balance_sheet_text
        return ""

    async def recognize_images(self, images) -> str:
        parts = []
        for _ in images:
            text = await self.recognize_image(None)
            if text.strip():
                parts.append(text.strip())
        return "\n".join(parts)


def _make_pdf_bytes(text: str = "sample") -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    return doc.tobytes()


def _make_multi_page_pdf(pages: list[str]) -> bytes:
    doc = fitz.open()
    for text in pages:
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


def test_supported_types(client: TestClient) -> None:
    response = client.get("/api/v1/test/supported-types")
    assert response.status_code == 200
    assert response.json()["data"]["types"] == [1, 2, 3]


@patch("ocr_rel.services.recognition_service.get_ocr_engine", return_value=FakeOcrEngine())
def test_test_recognize_flow(mock_engine, client: TestClient) -> None:
    pdf_bytes = _make_pdf_bytes()
    files = {"file": ("license.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
    data = {
        "registration_id": "reg-business-001",
        "doc_type": "1",
        "attachment_name": "营业执照",
        "ocr_engine": "paddle",
    }
    response = client.post("/api/v1/test/recognize", files=files, data=data)
    assert response.status_code == 200
    body = response.json()
    assert body["message"] == "accepted"
    task_id = body["data"]["taskId"]
    assert body["data"]["requestEcho"]["registrationId"] == "reg-business-001"

    final = _wait_task(client, task_id)
    assert final["status"] == "success"
    assert final["progress"] == 100
    assert len(final["steps"]) >= 2

    callback_resp = client.get(f"/api/v1/tasks/{task_id}/callback")
    assert callback_resp.status_code == 200
    callback = callback_resp.json()["data"]
    assert callback["registrationId"] == "reg-business-001"
    assert callback["results"][0]["type"] == 1


@patch("ocr_rel.services.recognition_service.get_ocr_engine", return_value=FakeOcrEngine())
def test_parse_local_pdf(mock_engine, client: TestClient) -> None:
    pdf_bytes = _make_pdf_bytes()
    files = {"file": ("demo.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
    data = {
        "doc_type": "1",
        "registration_id": "reg-001",
        "ocr_engine": "paddle",
    }
    response = client.post("/api/v1/test/parse", files=files, data=data)
    assert response.status_code == 200
    task_id = response.json()["data"]["taskId"]
    final = _wait_task(client, task_id)
    assert final["status"] == "success"


@patch("ocr_rel.services.recognition_service.get_ocr_engine", return_value=FakeOcrEngine())
@patch("ocr_rel.services.recognition_service.PlatformCallbackClient.send_callback", new_callable=AsyncMock)
@patch("ocr_rel.services.recognition_service.PlatformFileClient.download_file", new_callable=AsyncMock)
def test_recognize_endpoint(mock_download, mock_callback, mock_engine, client: TestClient) -> None:
    mock_download.return_value = ("license.pdf", _make_pdf_bytes())

    payload = {
        "registrationId": "reg-100",
        "files": [
            {
                "type": 1,
                "name": "营业执照",
                "files": [{"uuid": "uuid-001"}],
            }
        ],
    }
    response = client.post("/api/v1/recognize", json=payload)
    assert response.status_code == 200
    task_id = response.json()["data"]["taskId"]
    final = _wait_task(client, task_id)
    assert final["status"] == "success"
    mock_download.assert_awaited_once()
    mock_callback.assert_awaited_once()


@patch("ocr_rel.services.recognition_service.get_ocr_engine", return_value=FakeIdCardOcrEngine())
def test_test_recognize_type_mismatch(mock_engine, client: TestClient) -> None:
    pdf_bytes = _make_pdf_bytes()
    files = {"file": ("idcard.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
    data = {
        "registration_id": "reg-mismatch-001",
        "doc_type": "1",
        "attachment_name": "营业执照",
        "ocr_engine": "paddle",
    }
    response = client.post("/api/v1/test/recognize", files=files, data=data)
    assert response.status_code == 200
    task_id = response.json()["data"]["taskId"]

    final = _wait_task(client, task_id)
    assert final["status"] == "failed"
    assert "文件内容与声明类型不一致" in (final["error"] or "")
    assert "法人身份证" in (final["error"] or "")

    callback_resp = client.get(f"/api/v1/tasks/{task_id}/callback")
    assert callback_resp.status_code == 400


@patch("ocr_rel.services.recognition_service.get_ocr_engine", return_value=FakeAuditReportOcrEngine())
def test_test_recognize_audit_report(mock_engine, client: TestClient) -> None:
    pdf_bytes = _make_multi_page_pdf(["cover", "balance"])
    files = {"file": ("audit-report.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
    data = {
        "registration_id": "reg-audit-001",
        "doc_type": "3",
        "attachment_name": "审计报告",
        "ocr_engine": "paddle",
    }
    response = client.post("/api/v1/test/recognize", files=files, data=data)
    assert response.status_code == 200
    task_id = response.json()["data"]["taskId"]

    final = _wait_task(client, task_id)
    assert final["status"] == "success"

    callback_resp = client.get(f"/api/v1/tasks/{task_id}/callback")
    assert callback_resp.status_code == 200
    callback = callback_resp.json()["data"]
    detail = callback["results"][0]["detail"][0]
    assert callback["results"][0]["type"] == 3
    assert detail["companyName"] == "河南测试售电有限公司"
    assert "立信会计师事务所" in detail["accountingFirmName"]
    assert detail["totalAssets"] == "25000000"
