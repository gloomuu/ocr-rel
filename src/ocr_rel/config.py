from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "ocr-rel"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "info"
    log_dir: str = "logs"
    log_file_name: str = "ocr-rel.log"
    log_file_enabled: bool = True
    log_max_bytes: int = 10 * 1024 * 1024
    log_backup_count: int = 5

    api_key: str = ""
    auth_enabled: bool = False
    auth_username: str = ""
    auth_password: str = ""
    auth_secret_key: str = ""

    ocr_engine: str = "local"
    ocr_server_url: str = "http://127.0.0.1:6006"
    ocr_confidence_threshold: float = 0.6
    ocr_timeout: float = 180.0

    aliyun_access_key_id: str = ""
    aliyun_access_key_secret: str = ""
    aliyun_ocr_endpoint: str = "ocr-api.cn-hangzhou.aliyuncs.com"

    # Test page defaults (frontend reads via /api/v1/test/config)
    test_page_default_ocr_engine: str = "local"

    extraction_strategy: str = "llm"
    llm_api_key: str = ""
    llm_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    llm_model: str = "qwen-vl-plus"
    llm_timeout: float = 60.0
    llm_temperature: float = 0.0
    llm_fallback_to_regex: bool = True

    platform_base_url: str = "http://localhost:8080"
    platform_api_key: str = ""
    platform_callback_enabled: bool = False
    platform_callback_retry_count: int = 3
    platform_callback_retry_interval: int = 30

    pdf_render_dpi: int = 200
    database_path: str = "data/ocr-rel.db"
    upload_storage_path: str = "data/uploads"
    max_upload_file_size: int = 10 * 1024 * 1024
    max_stored_files: int = Field(default=100, ge=1)

    # Task execution queue: max concurrent recognition workers; excess tasks wait in queue
    max_concurrent_tasks: int = Field(default=2, ge=1)

    @field_validator("database_path", "upload_storage_path", mode="before")
    @classmethod
    def _normalize_storage_path(cls, value: str) -> str:
        return str(value)

    @field_validator("ocr_engine", "test_page_default_ocr_engine", mode="before")
    @classmethod
    def _normalize_ocr_engine(cls, value: str) -> str:
        normalized = str(value).strip().lower()
        if normalized not in {"local", "paddle", "aliyun"}:
            raise ValueError(f"Invalid OCR engine: {value}. Supported: local, paddle, aliyun")
        return normalized


settings = Settings()
settings.database_path = str(Path(settings.database_path))
settings.upload_storage_path = str(Path(settings.upload_storage_path))
