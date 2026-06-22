from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from ocr_rel import __version__
from ocr_rel.api.auth import router as auth_router
from ocr_rel.api.document_analysis import router as document_analysis_router
from ocr_rel.api.recognize import router as recognize_router
from ocr_rel.api.tasks import router as tasks_router
from ocr_rel.api.test_api import router as test_router
from ocr_rel.config import settings
from ocr_rel.db.database import init_db
from ocr_rel.logging_config import setup_logging
from ocr_rel.logging_config import get_logger
from ocr_rel.parsers.registry import supported_types
from ocr_rel.pdf.converter import COVER_PAGE_ONLY_TYPES
from ocr_rel.services.local_file_store import local_file_store
from ocr_rel.tasks.runner import background_runner

logger = get_logger(__name__)

_PACKAGE_STATIC_DIR = Path(__file__).resolve().parent / "static"
_MOUNTED_SRC_STATIC_DIR = Path("/app/src/ocr_rel/static")


def _resolve_static_dir() -> Path:
    """Prefer mounted dev source so Docker volume overrides image site-packages."""
    for candidate in (_MOUNTED_SRC_STATIC_DIR, _PACKAGE_STATIC_DIR):
        if (candidate / "test.html").exists():
            return candidate
    return _PACKAGE_STATIC_DIR


STATIC_DIR = _resolve_static_dir()

setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await local_file_store.init_db()
    background_runner.configure()
    logger.info(
        "OCR-REL started | version=%s | supportedTypes=%s | coverPageOnlyTypes=%s | staticDir=%s",
        __version__,
        supported_types(),
        sorted(COVER_PAGE_ONLY_TYPES),
        STATIC_DIR,
    )
    yield


app = FastAPI(
    title=settings.app_name,
    version=__version__,
    docs_url="/docs" if settings.app_env != "production" else None,
    redoc_url="/redoc" if settings.app_env != "production" else None,
    lifespan=lifespan,
)

app.include_router(auth_router)
app.include_router(document_analysis_router)
app.include_router(recognize_router)
app.include_router(tasks_router)
app.include_router(test_router)

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/health")
def health_check() -> dict[str, str | int]:
    queue_stats = background_runner.stats()
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": __version__,
        "env": settings.app_env,
        "ocrEngine": settings.ocr_engine,
        "extractionStrategy": settings.extraction_strategy,
        "databasePath": settings.database_path,
        **queue_stats,
    }


@app.get("/test")
def test_page() -> FileResponse:
    page = STATIC_DIR / "test.html"
    if not page.exists():
        raise HTTPException(status_code=404, detail="Test page is not available")
    return FileResponse(
        page,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "Pragma": "no-cache",
        },
    )
