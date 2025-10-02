"""
Настройка роутеров приложения
"""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import cleanup, healthcheck, studies_router, web
from app.core.config import settings


def setup_routes(app: FastAPI) -> None:
    """Настройка роутеров и статических файлов"""
    # Подключение статических файлов
    app.mount("/static", StaticFiles(directory="app/static"), name="static")

    # Подключение роутеров
    app.include_router(web.router, tags=["web"])
    app.include_router(healthcheck.router, tags=["health"])
    app.include_router(studies_router, prefix=settings.api_v1_prefix)
    app.include_router(cleanup.router, prefix=settings.api_v1_prefix)
