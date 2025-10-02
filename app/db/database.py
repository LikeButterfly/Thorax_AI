"""
Настройка базы данных с connection pooling и оптимизацией
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator, Generator

from sqlalchemy import create_engine, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

from app.core.config import settings

# Создание движка базы данных с connection pooling
engine = create_engine(
    settings.database_url,
    poolclass=QueuePool,
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
    pool_timeout=settings.database_pool_timeout,
    pool_recycle=settings.database_pool_recycle,
    pool_pre_ping=True,  # Проверка соединений перед использованием
    echo=settings.debug,  # Логирование SQL запросов в debug режиме
)

# Создание фабрики сессий
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False,  # Не истекают объекты после commit
)

# Базовый класс для моделей
Base = declarative_base()


def get_db() -> Generator:
    """
    Получение сессии базы данных

    Yields:
        Session: Сессия базы данных
    """
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@asynccontextmanager
async def get_async_db() -> AsyncGenerator:
    """
    Асинхронное получение сессии базы данных

    Yields:
        Session: Сессия базы данных
    """
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def create_tables():
    """Создание всех таблиц в базе данных"""
    Base.metadata.create_all(bind=engine)


def drop_tables():
    """Удаление всех таблиц из базы данных"""
    Base.metadata.drop_all(bind=engine)


# TODO: Добавить индексы для часто используемых полей
# TODO: Добавить constraints для валидации данных
