import asyncio
from dataclasses import dataclass


@dataclass
class StoredFile:
    file_name: str
    content: bytes


class TestFileStore:
    def __init__(self) -> None:
        self._files: dict[str, StoredFile] = {}
        self._lock = asyncio.Lock()

    async def put(self, file_uuid: str, *, file_name: str, content: bytes) -> None:
        async with self._lock:
            self._files[file_uuid] = StoredFile(file_name=file_name, content=content)

    async def get(self, file_uuid: str) -> tuple[str, bytes]:
        async with self._lock:
            stored = self._files.get(file_uuid)
            if stored is None:
                raise ValueError(f"Test file UUID not found: {file_uuid}")
            return stored.file_name, stored.content


test_file_store = TestFileStore()
