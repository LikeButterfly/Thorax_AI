"""
Конфигурация приложения
"""

from typing import List

from pydantic import Field, field_validator
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

    # Флаги для сохранения файлов
    save_zip_files: bool = False
    save_extracted_data: bool = True  # always True
    save_images: bool = True  # always True

    # # Настройки обработки
    # max_concurrent_processing: int = 5

    # Безопасность
    # secret_key: str = "your-secret-key-change-in-production"
    cors_origins: List[str] = [
        "http://localhost:3000",
        "http://localhost:8000",
    ]
    cors_allow_credentials: bool = True
    cors_allow_methods: List[str] = ["GET", "POST", "PUT", "DELETE"]
    cors_allow_headers: List[str] = ["*"]

    # API
    api_v1_prefix: str = "/api/v1"

    # ML Service
    ml_service_url: str = "http://ml-service:8001"
    ml_service_timeout: int = 900
    ml_service_retry_attempts: int = 3

    # Celery & Redis
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = Field(
        default="", description="Celery broker URL (auto from redis_url)"
    )
    celery_result_backend: str = Field(
        default="", description="Celery result backend (auto from redis_url)"
    )
    celery_task_track_started: bool = True
    celery_task_time_limit: int = 1800  # 30 минут на задачу
    celery_worker_prefetch_multiplier: int = 1
    celery_worker_max_tasks_per_child: int = 50

    # Логирование
    log_level: str = "INFO"
    log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    log_to_file: bool = False

    # # Кэширование
    # cache_ttl: int = 3600  # 1 час
    # cache_max_size: int = 1000

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        """Парсит CORS origins из строки или списка"""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v

    def __init__(self, **kwargs):
        """Инициализация с автозаполнением Celery URLs"""
        super().__init__(**kwargs)
        # Автоматически устанавливаем broker и backend из redis_url если не указаны
        if not self.celery_broker_url:
            self.celery_broker_url = self.redis_url
        if not self.celery_result_backend:
            self.celery_result_backend = self.redis_url

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v):
        """Валидирует окружение"""
        allowed = {"development", "production"}
        if v not in allowed:
            raise ValueError(f"Environment must be one of {allowed}")
        return v

    # @field_validator("secret_key")
    # @classmethod
    # def validate_secret_key(cls, v):
    #     """Валидирует секретный ключ"""
    #     if v == "your-secret-key-change-in-production":
    #         import warnings

    #         warnings.warn(
    #             "Using default secret key! Change it in production!",
    #             UserWarning,
    #             stacklevel=2,
    #         )
    #     return v

    class Config:
        env_file = ".env"
        case_sensitive = False
        env_prefix = "THORAX_"


# Глобальный экземпляр настроек
settings = Settings()
