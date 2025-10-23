"""
Главный файл ML сервиса ThoraxAI
"""

from api import health, predictions
from core.config import settings
from core.lifespan import lifespan
from core.logging import setup_logging
from core.middleware import setup_middleware
from fastapi import FastAPI

# Настройка логирования
setup_logging()

# Создание приложения FastAPI
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Сервис для предсказания патологий с использованием Swin Transformer",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Настройка middleware
setup_middleware(app)

# Подключение роутеров
app.include_router(health.router, tags=["health"])
app.include_router(predictions.router, tags=["predictions"])
