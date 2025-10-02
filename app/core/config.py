"""
Конфигурация приложения
"""

from typing import List

from pydantic import Field, validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Настройки приложения ThoraxAI

    Все настройки могут быть переопределены через переменные окружения.
    Для переменных с префиксом THORAX_ используется автоматическое сопоставление.
    """

    # Основные настройки
    app_name: str = "ThoraxAI"
    app_version: str = "1.0.0"
    debug: bool = False
    environment: str = "development"

    # База данных
    database_url: str = "postgresql://thoraxai:thoraxai@localhost:5432/thoraxai"
    database_pool_size: int = 10
    database_max_overflow: int = 20
    database_pool_timeout: int = 30
    database_pool_recycle: int = 3600

    # Файловая система
    upload_dir: str = "uploads"
    max_file_size: int = Field(default=2 * 1024 * 1024 * 1024, description="2GB")
    allowed_extensions: set = {".zip"}

    # Флаги для сохранения файлов
    save_zip_files: bool = False
    save_extracted_data: bool = True  # always True
    save_images: bool = True  # always True

    # Настройки обработки
    max_concurrent_processing: int = 5

    # Безопасность
    secret_key: str = "your-secret-key-change-in-production"
    cors_origins: List[str] = ["http://localhost:3000", "http://localhost:8000"]
    cors_allow_credentials: bool = True
    cors_allow_methods: List[str] = ["GET", "POST", "PUT", "DELETE"]
    cors_allow_headers: List[str] = ["*"]

    # API
    api_v1_prefix: str = "/api/v1"
    api_rate_limit: str = "100/minute"

    # ML Service
    ml_service_url: str = "http://ml-service:8001"
    ml_service_timeout: int = 300
    ml_service_retry_attempts: int = 3

    # Логирование
    log_level: str = "INFO"
    log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    log_to_file: bool = False

    # # Кэширование
    # cache_ttl: int = 3600  # 1 час
    # cache_max_size: int = 1000

    @validator("cors_origins", pre=True)
    def parse_cors_origins(cls, v):
        """Парсит CORS origins из строки или списка"""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v

    @validator("environment")
    def validate_environment(cls, v):
        """Валидирует окружение"""
        allowed = {"development", "staging", "production"}
        if v not in allowed:
            raise ValueError(f"Environment must be one of {allowed}")
        return v

    @validator("secret_key")
    def validate_secret_key(cls, v):
        """Валидирует секретный ключ"""
        if v == "your-secret-key-change-in-production":
            import warnings

            warnings.warn(
                "Using default secret key! Change it in production!",
                UserWarning,
                stacklevel=2,
            )
        return v

    class Config:
        env_file = ".env"
        case_sensitive = False
        env_prefix = "THORAX_"


# Глобальный экземпляр настроек
settings = Settings()
