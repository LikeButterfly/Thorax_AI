"""
Настройка логирования для приложения
"""

import logging
import logging.config
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.core.config import settings


class UTCPlus3Formatter(logging.Formatter):
    """
    Форматтер логов с временной зоной UTC+3
    """

    def formatTime(self, record, datefmt=None):
        # Получаем время в UTC+3
        utc_plus_3 = timezone(timedelta(hours=3))
        dt = datetime.fromtimestamp(record.created, tz=utc_plus_3)

        if datefmt:
            return dt.strftime(datefmt)
        else:
            return dt.strftime("%Y-%m-%d %H:%M:%S")


def setup_logging() -> None:
    """
    Настройка логирования для приложения
    """
    # Создаем директорию для логов только если нужно сохранять в файлы
    if settings.log_to_file:
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
    else:
        log_dir = None

    # Базовые обработчики
    handlers = {
        "console": {
            "class": "logging.StreamHandler",
            "level": settings.log_level,
            "formatter": "default",
            "stream": sys.stdout,
        },
    }

    # Добавляем файловые обработчики только если включено сохранение в файлы
    if settings.log_to_file and log_dir:
        handlers.update(
            {
                "file": {
                    "class": "logging.handlers.RotatingFileHandler",
                    "level": "INFO",
                    "formatter": "detailed",
                    "filename": str(log_dir / "thoraxai.log"),
                    "maxBytes": 10485760,  # 10MB
                    "backupCount": 5,
                },
                "error_file": {
                    "class": "logging.handlers.RotatingFileHandler",
                    "level": "ERROR",
                    "formatter": "detailed",
                    "filename": str(log_dir / "thoraxai_errors.log"),
                    "maxBytes": 10485760,  # 10MB
                    "backupCount": 5,
                },
            }
        )

    # Определяем обработчики для логгеров
    app_handlers = ["console"]
    if settings.log_to_file:
        app_handlers.extend(["file", "error_file"])

    sqlalchemy_handlers = ["console"]
    if settings.log_to_file:
        sqlalchemy_handlers.append("file")

    uvicorn_handlers = ["console"]
    if settings.log_to_file:
        uvicorn_handlers.append("file")

    root_handlers = ["console"]
    if settings.log_to_file:
        root_handlers.append("file")

    log_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "()": "app.core.logging.UTCPlus3Formatter",
                "format": settings.log_format,
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
            "detailed": {
                "()": "app.core.logging.UTCPlus3Formatter",
                "format": (
                    "%(asctime)s - %(name)s - %(levelname)s - %(module)s - "
                    "%(funcName)s:%(lineno)d - %(message)s"
                ),
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
            "json": {
                "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
                "format": (
                    "%(asctime)s %(name)s %(levelname)s %(module)s "
                    "%(funcName)s %(lineno)d %(message)s"
                ),
            },
        },
        "handlers": handlers,
        "loggers": {
            "app": {
                "level": settings.log_level,
                "handlers": app_handlers,
                "propagate": False,
            },
            "sqlalchemy.engine": {
                "level": "WARNING",
                "handlers": sqlalchemy_handlers,
                "propagate": False,
            },
            "uvicorn": {
                "level": "INFO",
                "handlers": uvicorn_handlers,
                "propagate": False,
            },
        },
        "root": {
            "level": settings.log_level,
            "handlers": root_handlers,
        },
    }

    # Применяем конфигурацию
    logging.config.dictConfig(log_config)

    # Настраиваем логирование для внешних библиотек
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("pydicom").setLevel(logging.WARNING)

    # Логируем информацию о настройке
    logger = logging.getLogger(__name__)
    logger.info(f"Logging configured for {settings.environment} environment")
    logger.info(f"Log level: {settings.log_level}")
    logger.info(f"Log to file: {settings.log_to_file}")
    if settings.log_to_file and log_dir:
        logger.info(f"Log files: {log_dir.absolute()}")
    else:
        logger.info("Log files disabled - only console output")
