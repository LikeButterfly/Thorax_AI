"""
Конфигурация ML сервиса
"""

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Настройки ML сервиса

    Все настройки могут быть переопределены через переменные окружения.
    Для переменных с префиксом ML_ используется автоматическое сопоставление.
    """

    # Основные настройки
    app_name: str = "ML Pathology Detection Service"
    app_version: str = "1.0.0"
    debug: bool = False
    environment: str = "development"

    # ML настройки
    model_path: str = Field(
        default="models/swin_model_weights.pth",
        description="Путь к файлу модели",
    )
    model_name: str = Field(
        default="swin_base_patch4_window7_224",
        description="Название модели",
    )
    num_classes: int = Field(
        default=2,
        description="Количество классов",
    )
    device: str = Field(
        default="auto",
        description="Устройство для вычислений (auto, cpu, cuda)",
    )

    # Настройки API
    api_host: str = Field(
        default="0.0.0.0",
        description="Хост для API",
    )
    api_port: int = Field(
        default=8001,
        description="Порт для API",
    )

    # Логирование
    log_level: str = Field(
        default="INFO",
        description="Уровень логирования",
    )
    log_format: str = Field(
        default="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        description="Формат логов",
    )
    log_to_file: bool = Field(
        default=False,
        description="Сохранять логи в файл",
    )

    # Настройки анализа патологий
    threshold_frame_prob: float = Field(
        default=0.6,  # TODO in const
        description="Порог вероятности патологии на кадре",
    )
    threshold_frac: float = Field(
        default=0.12,  # TODO in const
        description="Минимальная доля положительных кадров для исследования",
    )

    def get_device(self) -> str:
        """Определяет устройство для вычислений"""
        if self.device == "auto":
            try:
                import torch

                return "cuda" if torch.cuda.is_available() else "cpu"
            except ImportError:
                return "cpu"
        return self.device

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v):
        """Валидирует окружение"""
        allowed = {"development", "production"}
        if v not in allowed:
            raise ValueError(f"Environment must be one of {allowed}")
        return v

    @field_validator("device")
    @classmethod
    def validate_device(cls, v):
        """Валидирует устройство"""
        allowed = {"auto", "cpu", "cuda"}
        if v not in allowed:
            raise ValueError(f"Device must be one of {allowed}")
        return v

    class Config:
        env_file = ".env"
        case_sensitive = False
        env_prefix = "ML_"


# Глобальный экземпляр настроек
settings = Settings()
