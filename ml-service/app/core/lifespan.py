"""
Управление жизненным циклом ML сервиса
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from core.config import settings
from fastapi import FastAPI
from services.ml_service import MLModelService

logger = logging.getLogger(__name__)

# Глобальная переменная для сервиса ML
ml_service: MLModelService | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Управление жизненным циклом ML сервиса

    Выполняет инициализацию при запуске и очистку при остановке.
    """
    global ml_service

    # Startup
    logger.info(f"Запуск {settings.app_name} v{settings.app_version}")
    logger.info(f"Окружение: {settings.environment}")
    logger.info(f"Режим отладки: {settings.debug}")
    logger.info(f"Устройство: {settings.get_device()}")
    logger.info(f"Модель: {settings.model_name}")
    logger.info(f"Путь к модели: {settings.model_path}")

    try:
        # Создание необходимых директорий
        directories = [
            "logs",
            "models",
            "temp",
        ]

        for directory in directories:
            Path(directory).mkdir(parents=True, exist_ok=True)
            logger.info(f"Директория создана/проверена: {directory}")

        # Проверяем права на запись в директории
        for directory in directories:
            test_file = Path(directory) / ".write_test"
            try:
                test_file.write_text("test")
                test_file.unlink()
                logger.debug(f"Права на запись в {directory}: OK")
            except Exception as e:
                logger.error(f"Нет прав на запись в {directory}: {e}")
                raise

        # Загружаем ML модель
        logger.info("Загружаем ML модель...")
        ml_service = MLModelService()
        await ml_service.load_model()
        logger.info("ML модель загружена успешно")

        # Сохраняем ссылку на сервис в состоянии приложения
        app.state.ml_service = ml_service

        logger.info("Инициализация ML сервиса завершена успешно")

    except Exception as e:
        logger.error(f"Ошибка при инициализации ML сервиса: {e}")
        raise

    yield

    # Shutdown
    logger.info("Начинаем остановку ML сервиса...")

    try:
        # Очищаем ресурсы модели
        if ml_service:
            await ml_service.cleanup()
            logger.info("ML модель очищена")

        # Очищаем временные файлы
        temp_dir = Path("temp")
        if temp_dir.exists():
            for temp_file in temp_dir.glob("*"):
                try:
                    if temp_file.is_file():
                        temp_file.unlink()
                except Exception as e:
                    logger.warning(f"Не удалось удалить временный файл {temp_file}: {e}")

        logger.info("Остановка ML сервиса завершена")

    except Exception as e:
        logger.error(f"Ошибка при остановке ML сервиса: {e}")
