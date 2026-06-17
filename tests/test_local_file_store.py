import pytest

from ocr_rel.config import settings
from ocr_rel.services.local_file_store import local_file_store


@pytest.fixture
async def initialized_store(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "store.db"
    upload_dir = tmp_path / "uploads"
    monkeypatch.setattr(settings, "database_path", str(db_path))
    monkeypatch.setattr(settings, "upload_storage_path", str(upload_dir))
    local_file_store._root = upload_dir
    await local_file_store.init_db()


async def test_save_and_get_file(initialized_store) -> None:
    await local_file_store.save("task-1", file_name="demo.pdf", content=b"%PDF-demo")
    stored = await local_file_store.get_file_path("task-1")
    assert stored is not None
    path, name = stored
    assert name == "demo.pdf"
    assert path.exists()
    assert path.read_bytes() == b"%PDF-demo"
    assert await local_file_store.has_file("task-1") is True


async def test_retention_deletes_oldest_files(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "retention.db"
    upload_dir = tmp_path / "uploads"
    monkeypatch.setattr(settings, "database_path", str(db_path))
    monkeypatch.setattr(settings, "upload_storage_path", str(upload_dir))
    monkeypatch.setattr(settings, "max_stored_files", 3)
    local_file_store._root = upload_dir
    await local_file_store.init_db()

    for index in range(5):
        await local_file_store.save(
            f"task-{index}",
            file_name=f"file-{index}.pdf",
            content=f"content-{index}".encode(),
        )

    remaining = []
    for index in range(5):
        if await local_file_store.has_file(f"task-{index}"):
            remaining.append(index)

    assert remaining == [2, 3, 4]
    assert not await local_file_store.has_file("task-0")
    assert not await local_file_store.has_file("task-1")
