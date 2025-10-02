"""
Конфигурация ML сервиса
"""

import os
from typing import Optional


class Settings:
    """Настройки ML сервиса"""

    # Основные настройки
    MODEL_PATH: str = os.getenv("MODEL_PATH", "models/swin_model_weights.pth")
    MODEL_NAME: str = os.getenv("MODEL_NAME", "swin_base_patch4_window7_224")
    NUM_CLASSES: int = int(os.getenv("NUM_CLASSES", "2"))

    # Настройки устройства
    DEVICE: str = os.getenv("DEVICE", "auto")  # auto, cpu, cuda

    # Настройки предсказания
    PATHOLOGY_THRESHOLD: float = float(os.getenv("PATHOLOGY_THRESHOLD", "0.9"))
    BATCH_SIZE: int = int(os.getenv("BATCH_SIZE", "1"))

    # Настройки логирования
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    # Настройки API
    API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
    API_PORT: int = int(os.getenv("API_PORT", "8001"))

    def get_device(self) -> str:
        """Определяет устройство для вычислений"""
        if self.DEVICE == "auto":
            try:
                import torch

                return "cuda" if torch.cuda.is_available() else "cpu"
            except ImportError:
                return "cpu"
        return self.DEVICE


settings = Settings()
