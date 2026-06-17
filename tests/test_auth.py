import pytest
from fastapi.testclient import TestClient

from ocr_rel.auth.token import compute_auth_token
from ocr_rel.config import settings


@pytest.fixture
def auth_settings(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "auth_username", "testuser")
    monkeypatch.setattr(settings, "auth_password", "testpass")
    monkeypatch.setattr(settings, "auth_secret_key", "secret-key")
    token = compute_auth_token("testuser", "testpass", "secret-key")
    return {"token": token}


def test_compute_auth_token() -> None:
    token = compute_auth_token("user", "pass", "key")
    assert len(token) == 32
    assert token == compute_auth_token("user", "pass", "key")


def test_auth_token_endpoint_success(client: TestClient, auth_settings: dict[str, str]) -> None:
    response = client.post(
        "/api/v1/auth/token",
        json={"username": "testuser", "password": "testpass"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["token"] == auth_settings["token"]


def test_auth_token_endpoint_rejects_invalid_credentials(
    client: TestClient, auth_settings: dict[str, str]
) -> None:
    response = client.post(
        "/api/v1/auth/token",
        json={"username": "testuser", "password": "wrong"},
    )
    assert response.status_code == 401


def test_protected_endpoint_requires_token_when_auth_enabled(
    client: TestClient, auth_settings: dict[str, str]
) -> None:
    response = client.get("/api/v1/tasks?page=1&pageSize=10")
    assert response.status_code == 401

    response = client.get(
        "/api/v1/tasks?page=1&pageSize=10",
        headers={"token": auth_settings["token"]},
    )
    assert response.status_code == 200


def test_test_config_is_public(client: TestClient, auth_settings: dict[str, str]) -> None:
    response = client.get("/api/v1/test/config")
    assert response.status_code == 200
    assert response.json()["data"]["authEnabled"] is True


def test_health_is_public(client: TestClient, auth_settings: dict[str, str]) -> None:
    response = client.get("/health")
    assert response.status_code == 200
