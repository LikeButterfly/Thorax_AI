"""
Главный файл приложения ThoraxAI
"""

from fastapi import FastAPI

from app.core.config import settings
from app.core.lifespan import lifespan
from app.core.logging import setup_logging
from app.core.middleware import setup_middleware
from app.core.routes import setup_routes

# Настройка логирования
setup_logging()

# Создание приложения FastAPI
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Система автоматического анализа КТ органов грудной клетки",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Настройка middleware
setup_middleware(app)

# Настройка роутеров
setup_routes(app)
