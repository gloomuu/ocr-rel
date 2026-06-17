import pytest
from fastapi.testclient import TestClient

from ocr_rel.config import settings
from ocr_rel.main import app
from ocr_rel.services.local_file_store import local_file_store
from ocr_rel.tasks.runner import background_runner


@pytest.fixture(autouse=True)
def isolated_database(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(settings, "database_path", str(db_path))


@pytest.fixture(autouse=True)
def isolated_upload_storage(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    upload_dir = tmp_path / "uploads"
    monkeypatch.setattr(settings, "upload_storage_path", str(upload_dir))
    local_file_store._root = upload_dir


@pytest.fixture(autouse=True)
def configure_task_queue(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "max_concurrent_tasks", 2)
    monkeypatch.setattr(settings, "extraction_strategy", "regex")
    monkeypatch.setattr(settings, "llm_api_key", "")
    monkeypatch.setattr(settings, "auth_enabled", False)
    background_runner.configure(2)


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client
