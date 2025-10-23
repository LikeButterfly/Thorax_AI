"""
Middleware для ML сервиса
"""

import logging
import time
from typing import Callable

from fastapi import FastAPI, Request, Response

logger = logging.getLogger(__name__)


def setup_middleware(app: FastAPI) -> None:
    """
    Настройка middleware для ML сервиса

    Args:
        app: FastAPI приложение
    """

    # Middleware для логирования запросов
    @app.middleware("http")
    async def log_requests(request: Request, call_next: Callable) -> Response:
        """
        Middleware для логирования HTTP запросов

        Args:
            request: HTTP запрос
            call_next: Следующий middleware/handler

        Returns:
            Response: HTTP ответ
        """
        start_time = time.time()

        # Логируем входящий запрос
        logger.info(
            f"ML Request: {request.method} {request.url.path} "
            f"from {request.client.host if request.client else 'unknown'}"
        )

        # Обрабатываем запрос
        response = await call_next(request)

        # Вычисляем время обработки
        process_time = time.time() - start_time

        # Логируем ответ
        logger.info(f"ML Response: {response.status_code} in {process_time:.3f}s")

        # Добавляем заголовок с временем обработки
        response.headers["X-Process-Time"] = str(process_time)
        response.headers["X-Service"] = "ml-service"

        return response

    # Middleware для обработки ошибок
    @app.middleware("http")
    async def error_handler(request: Request, call_next: Callable) -> Response:
        """
        Middleware для обработки ошибок

        Args:
            request: HTTP запрос
            call_next: Следующий middleware/handler

        Returns:
            Response: HTTP ответ
        """
        try:
            return await call_next(request)
        except Exception as e:
            logger.error(
                f"Unhandled error in ML service {request.method} {request.url.path}: {str(e)}"
            )
            # В production здесь должен быть более детальный error handling
            raise
