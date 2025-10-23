"""
Health check endpoints для ML сервиса
"""

import logging
from typing import Any, Dict

from fastapi import APIRouter, Request

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/health")
async def health_check(request: Request) -> Dict[str, Any]:
    """
    Проверка здоровья ML сервиса

    Returns:
        Dict с информацией о состоянии сервиса
    """
    # Получаем ML сервис из состояния приложения
    ml_service = getattr(request.app.state, "ml_service", None)

    return {
        "status": "healthy",
        "service": "ml-service",
        "model_loaded": ml_service is not None and ml_service._model_loaded,
        "device": ml_service.device if ml_service else None,
    }
