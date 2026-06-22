from fastapi.testclient import TestClient

from ocr_rel.main import app


def test_health_check() -> None:
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ok"
        assert payload["service"] == "ocr-rel"
        assert "ocrEngine" in payload
        assert "extractionStrategy" in payload
        assert "databasePath" in payload
        assert payload["maxConcurrent"] >= 1
        assert "running" in payload
        assert "waiting" in payload


def test_test_page_available() -> None:
    with TestClient(app) as client:
        response = client.get("/test")
        assert response.status_code == 200
        assert "AI 识别联调测试页" in response.text
        assert "调用历史" in response.text
        assert "文件名" in response.text
        assert "加载中" in response.text
        assert "1 - 营业执照" not in response.text


def test_test_config_endpoint() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/test/config")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["ocrEngine"] == "aliyun"
        assert data["maxConcurrentTasks"] == 2
        assert data["maxUploadFileSize"] == 10 * 1024 * 1024
        assert data["maxStoredFiles"] == 100
        assert data["serverOcrEngine"] in {"local", "paddle", "aliyun"}
        assert data["supportedTypes"] == [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]
        assert [item["type"] for item in data["supportedTypeItems"]] == [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]
        assert data["supportedTypeItems"][7]["name"] == "信用证明"
        assert data["supportedTypeItems"][8]["name"] == "企业董事、监事、高级管理人员信用证明"
        assert data["supportedTypeItems"][9]["name"] == "股东信用证明"
