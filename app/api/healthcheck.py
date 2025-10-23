"""
API endpoints для проверки состояния приложения
"""

import logging
import os
from datetime import datetime
from typing import Any, Dict

import aiofiles
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import engine, get_db
from app.services.ml_client_service import MLClientService
from app.utils.helpers import get_current_time

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """
    Проверка состояния приложения

    Returns:
        Dict[str, Any]: Статус приложения и метаданные
    """
    # Проверяем доступность ML сервиса
    ml_client = MLClientService()
    ml_service_health = await ml_client.check_ml_service_health()

    return {
        "status": "healthy",
        "app_name": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "timestamp": get_current_time().isoformat(),
        "ml_service": ml_service_health,
    }


@router.get("/health/detailed")
async def detailed_health_check(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    Детальная проверка состояния приложения

    Проверяет состояние базы данных и других компонентов.

    Args:
        db: Сессия базы данных

    Returns:
        Dict[str, Any]: Детальный статус приложения

    Raises:
        HTTPException: Ошибка при проверке компонентов
    """
    health_status = {
        "status": "healthy",
        "app_name": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "timestamp": get_current_time().isoformat(),
        "components": {},
    }

    # Проверка базы данных
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        health_status["components"]["database"] = {
            "status": "healthy",
            "message": "Database connection successful",
        }
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        health_status["components"]["database"] = {
            "status": "unhealthy",
            "message": f"Database connection failed: {str(e)}",
        }
        health_status["status"] = "unhealthy"

    # Проверка файловой системы
    try:
        # Проверяем права на запись в upload директорию
        test_file = os.path.join(settings.upload_dir, ".health_check")
        async with aiofiles.open(test_file, "w") as f:
            await f.write("health check")
        os.remove(test_file)

        health_status["components"]["filesystem"] = {
            "status": "healthy",
            "message": "File system accessible",
        }
    except Exception as e:
        logger.error(f"Filesystem health check failed: {e}")
        health_status["components"]["filesystem"] = {
            "status": "unhealthy",
            "message": f"File system error: {str(e)}",
        }
        health_status["status"] = "unhealthy"

    # Проверка ML сервиса
    try:
        ml_client = MLClientService()
        ml_service_health = await ml_client.check_ml_service_health()

        if ml_service_health["available"]:
            health_status["components"]["ml_service"] = {
                "status": "healthy",
                "message": "ML service is available",
                "model_loaded": ml_service_health["model_loaded"],
                "device": ml_service_health["device"],
            }
        else:
            health_status["components"]["ml_service"] = {
                "status": "unhealthy",
                "message": f"ML service unavailable: {ml_service_health['status']}",
                "model_loaded": False,
                "device": "unknown",
            }

            logger.warning(f"ML service is unavailable: {ml_service_health['status']}")
    except Exception as e:
        logger.error(f"ML service health check failed: {e}")
        health_status["components"]["ml_service"] = {
            "status": "unhealthy",
            "message": f"ML service check failed: {str(e)}",
            "model_loaded": False,
            "device": "unknown",
        }

        logger.warning(f"ML service health check failed: {str(e)}")

    # Если есть проблемы, возвращаем ошибку
    if health_status["status"] != "healthy":
        raise HTTPException(status_code=503, detail=health_status)

    return health_status
