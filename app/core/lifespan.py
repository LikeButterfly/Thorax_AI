"""
Управление жизненным циклом приложения
"""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from sqlalchemy import text

from app.core.config import settings
from app.db.database import create_tables, engine
from app.models import Study

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Управление жизненным циклом приложения

    Выполняет инициализацию при запуске и очистку при остановке.
    """
    # Startup
    logger.info(f"Запуск {settings.app_name} v{settings.app_version}")
    logger.info(f"Окружение: {settings.environment}")
    logger.info(f"Режим отладки: {settings.debug}")
    logger.info(f"Директория загрузок: {settings.upload_dir}")

    try:
        # Проверяем подключение к базе данных
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("Подключение к базе данных успешно")

        # Создание таблиц базы данных
        create_tables()
        logger.info("Таблицы базы данных созданы/обновлены")

        # Создание необходимых директорий
        directories = [
            settings.upload_dir,
            "app/static",
            "logs",
            "reports",
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

        logger.info("Инициализация приложения завершена успешно")

    except Exception as e:
        logger.error(f"Ошибка при инициализации приложения: {e}")
        raise

    yield

    # Shutdown
    logger.info("Начинаем остановку приложения...")

    try:
        # Закрываем соединения с базой данных
        engine.dispose()
        logger.info("Соединения с базой данных закрыты")

        # Очищаем временные файлы
        temp_dir = Path("temp")
        if temp_dir.exists():
            for temp_file in temp_dir.glob("*"):
                try:
                    if temp_file.is_file():
                        temp_file.unlink()
                except Exception as e:
                    logger.warning(f"Не удалось удалить временный файл {temp_file}: {e}")

        logger.info("Остановка приложения завершена")

    except Exception as e:
        logger.error(f"Ошибка при остановке приложения: {e}")
