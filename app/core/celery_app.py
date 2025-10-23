"""
Конфигурация Celery для асинхронной обработки задач
"""

import logging

from celery import Celery

from app.core.config import settings

logger = logging.getLogger(__name__)

# Создаем экземпляр Celery
celery_app = Celery(
    "thoraxai",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

# Конфигурация Celery
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=settings.celery_task_track_started,
    task_time_limit=settings.celery_task_time_limit,
    worker_prefetch_multiplier=settings.celery_worker_prefetch_multiplier,
    worker_max_tasks_per_child=settings.celery_worker_max_tasks_per_child,
    # Retry настройки
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    # Результаты
    result_expires=3600 * 24,  # 24 часа
    result_persistent=True,
    # Логирование
    worker_log_format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    worker_task_log_format="%(asctime)s - %(task_name)s[%(task_id)s] - %(levelname)s - %(message)s",
)

# Автоматическое обнаружение задач
celery_app.autodiscover_tasks(["app.tasks"])

logger.info("Celery app initialized")
