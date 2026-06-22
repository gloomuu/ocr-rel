import io
from unittest.mock import AsyncMock, patch

import fitz
import pytest
from fastapi.testclient import TestClient

from ocr_rel.config import settings
from ocr_rel.main import app
from ocr_rel.services.callback_serializer import serialize_callback_payload


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


class FakeGradeProtectionOcrEngine:
    async def recognize_image(self, image) -> str:
        return (
            "信息系统安全等级保护备案证明\n"
            "单位名称：河南测试售电有限公司\n"
            "系统名称：售电业务技术支持系统\n"
            "安全保护等级：第二级\n"
            "备案号：41010000000-00001"
        )

    async def recognize_images(self, images) -> str:
        return await self.recognize_image(None)


class FakeSoftwareCopyrightOcrEngine:
    async def recognize_image(self, image) -> str:
        return (
            "计算机软件著作权登记证书\n"
            "软件名称：售电业务技术支持系统V1.0\n"
            "著作权人：河南测试售电有限公司\n"
            "登记号：2024SR1234567"
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
    data = response.json()["data"]
    assert data["types"] == [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]
    assert [item["type"] for item in data["items"]] == [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]
    assert data["items"][7]["name"] == "信用证明"
    assert data["items"][8]["name"] == "企业董事、监事、高级管理人员信用证明"
    assert data["items"][9]["name"] == "股东信用证明"


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


@patch("ocr_rel.services.recognition_service.get_ocr_engine", return_value=FakeIdCardOcrEngine())
def test_test_recognize_employee_id_with_personnel(mock_engine, client: TestClient) -> None:
    pdf_bytes = _make_pdf_bytes("id-card")
    files = {"file": ("employee-id.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
    data = {
        "registration_id": "reg-employee-001",
        "doc_type": "5",
        "attachment_name": "从业人员身份证",
        "ocr_engine": "paddle",
        "personnel": "张三",
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
    assert callback["results"][0]["type"] == 5
    assert detail["name"] == "张三"
    assert detail["idCardNumber"] == "410105199001011234"
    assert detail["personnel"] == "张三"


@patch("ocr_rel.services.recognition_service.get_ocr_engine", return_value=FakeGradeProtectionOcrEngine())
def test_test_recognize_grade_protection(mock_engine, client: TestClient) -> None:
    pdf_bytes = _make_pdf_bytes("grade-protection")
    files = {"file": ("grade-protection.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
    data = {
        "registration_id": "reg-grade-001",
        "doc_type": "6",
        "attachment_name": "等级保护备案证明",
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
    assert callback["results"][0]["type"] == 6
    assert detail["companyName"] == "河南测试售电有限公司"
    assert detail["systemLevel"] == "二级"
    assert detail["copyrightOwner"] == ""


@patch("ocr_rel.services.recognition_service.get_ocr_engine", return_value=FakeSoftwareCopyrightOcrEngine())
def test_test_recognize_software_copyright(mock_engine, client: TestClient) -> None:
    pdf_bytes = _make_pdf_bytes("software-copyright")
    files = {"file": ("software-copyright.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
    data = {
        "registration_id": "reg-soft-001",
        "doc_type": "6",
        "attachment_name": "软件著作证书",
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
    assert detail["copyrightOwner"] == "河南测试售电有限公司"
    assert detail["companyName"] == ""
    assert detail["systemLevel"] == ""


def test_document_analysis_submit_rejects_unsupported_type(client: TestClient) -> None:
    payload = {
        "registrationId": "reg-unsupported",
        "files": [
            {
                "type": 8,
                "name": "信用证明",
                "files": [{"uuid": "uuid-001"}],
            }
        ],
    }
    with patch("ocr_rel.services.submit_service.supported_types", return_value=[1, 2, 3]):
        response = client.post("/v1/document/analysis/submit", json=payload)
    assert response.status_code == 400
    assert 8 in response.json()["detail"]["unsupportedTypes"]


@patch("ocr_rel.services.recognition_service.get_ocr_engine", return_value=FakeOcrEngine())
@patch("ocr_rel.services.recognition_service.PlatformCallbackClient.send_callback", new_callable=AsyncMock)
@patch("ocr_rel.services.recognition_service.PlatformFileClient.download_file", new_callable=AsyncMock)
def test_document_analysis_submit(mock_download, mock_callback, mock_engine, client: TestClient) -> None:
    mock_download.return_value = ("license.pdf", _make_pdf_bytes())

    payload = {
        "registrationId": "123456",
        "files": [
            {
                "type": 1,
                "name": "营业执照",
                "files": [{"uuid": "uuid-001"}],
            }
        ],
    }
    response = client.post("/v1/document/analysis/submit", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == "0"
    assert body["message"] == "accepted"
    assert body["data"]["registrationId"] == "123456"
    task_id = body["data"]["taskId"]

    final = _wait_task(client, task_id)
    assert final["status"] == "success"
    mock_download.assert_awaited_once()
    mock_callback.assert_awaited_once()


@patch("ocr_rel.services.recognition_service.get_ocr_engine", return_value=FakeAuditReportOcrEngine())
@patch("ocr_rel.services.recognition_service.PlatformCallbackClient.send_callback", new_callable=AsyncMock)
@patch("ocr_rel.services.recognition_service.PlatformFileClient.download_file", new_callable=AsyncMock)
def test_document_analysis_callback_serializes_total_assets(
    mock_download,
    mock_callback,
    mock_engine,
    client: TestClient,
) -> None:
    mock_download.return_value = (
        "audit.pdf",
        _make_multi_page_pdf(
            [
                "审计报告 cover",
                "资产负债表 资产总计 25000000",
            ]
        ),
    )

    payload = {
        "registrationId": "reg-audit",
        "files": [
            {
                "type": 3,
                "name": "审计报告",
                "files": [{"uuid": "uuid-audit"}],
            }
        ],
    }
    response = client.post("/v1/document/analysis/submit", json=payload)
    task_id = response.json()["data"]["taskId"]
    final = _wait_task(client, task_id)
    assert final["status"] == "success"

    callback_payload = mock_callback.await_args.args[0]
    callback_body = serialize_callback_payload(callback_payload)
    detail = callback_body["results"][0]["detail"][0]
    assert callback_body["results"][0]["name"] == "审计报告"
    assert detail["totalAssets"] == 25000000
    assert isinstance(detail["totalAssets"], int)
