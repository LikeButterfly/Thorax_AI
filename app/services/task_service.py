"""
Сервис для работы с Celery задачами и их статусами
"""

import json
import logging
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.study import CeleryTaskStatus
from app.utils.helpers import get_current_time

logger = logging.getLogger(__name__)


class TaskService:
    """Сервис для управления статусами Celery задач"""

    def __init__(self, db: Session):
        self.db = db

    def create_task_status(
        self,
        task_id: str,
        batch_id: int,
        filename: str,
        status: str = "PENDING",
    ) -> CeleryTaskStatus:
        """
        Создает запись о статусе задачи

        Args:
            task_id: ID задачи Celery
            batch_id: ID батча загрузки
            filename: Имя файла
            status: Начальный статус

        Returns:
            CeleryTaskStatus: Созданная запись
        """
        task_status = CeleryTaskStatus(
            task_id=task_id,
            batch_id=batch_id,
            filename=filename,
            status=status,
        )
        self.db.add(task_status)
        self.db.commit()
        self.db.refresh(task_status)
        logger.info(f"Создан статус для задачи {task_id}: {filename}")
        return task_status

    def update_task_status(
        self,
        task_id: str,
        status: str,
        result: Optional[Dict] = None,
        error_message: Optional[str] = None,
        study_id: Optional[int] = None,
    ) -> bool:
        """
        Обновляет статус задачи

        Args:
            task_id: ID задачи Celery
            status: Новый статус
            result: Результат выполнения
            error_message: Сообщение об ошибке
            study_id: ID созданного исследования

        Returns:
            bool: True если обновление успешно
        """
        task_status = self.db.query(CeleryTaskStatus).filter_by(task_id=task_id).first()

        if not task_status:
            logger.warning(f"Задача {task_id} не найдена для обновления статуса")
            return False

        task_status.status = status  # type: ignore

        if result:
            task_status.result = json.dumps(result)  # type: ignore

        if error_message:
            task_status.error_message = error_message  # type: ignore

        if study_id:
            task_status.study_id = study_id  # type: ignore

        # Обновляем timestamps
        if status == "STARTED" and task_status.started_at is None:
            task_status.started_at = get_current_time()  # type: ignore

        if status in ("SUCCESS", "FAILURE", "REVOKED"):
            task_status.completed_at = get_current_time()  # type: ignore

        self.db.commit()
        logger.info(f"Обновлен статус задачи {task_id}: {status}")
        return True

    def get_task_status(self, task_id: str) -> Optional[CeleryTaskStatus]:
        """
        Получает статус задачи по ID

        Args:
            task_id: ID задачи Celery

        Returns:
            Optional[CeleryTaskStatus]: Статус задачи или None
        """
        return self.db.query(CeleryTaskStatus).filter_by(task_id=task_id).first()

    def get_batch_tasks(self, batch_id: int) -> List[CeleryTaskStatus]:
        """
        Получает все задачи батча

        Args:
            batch_id: ID батча

        Returns:
            List[CeleryTaskStatus]: Список задач батча
        """
        return (
            self.db.query(CeleryTaskStatus)
            .filter_by(batch_id=batch_id)
            .order_by(CeleryTaskStatus.created_at)
            .all()
        )

    def get_batch_statistics(self, batch_id: int) -> Dict:
        """
        Получает статистику по батчу

        Args:
            batch_id: ID батча

        Returns:
            Dict: Статистика батча
        """
        # Считаем количество задач по статусам
        stats = (
            self.db.query(CeleryTaskStatus.status, func.count(CeleryTaskStatus.id).label("count"))
            .filter_by(batch_id=batch_id)
            .group_by(CeleryTaskStatus.status)
            .all()
        )

        # Формируем словарь статистики
        status_counts = {status: count for status, count in stats}

        total = sum(status_counts.values())
        pending = status_counts.get("PENDING", 0)
        started = status_counts.get("STARTED", 0)
        success = status_counts.get("SUCCESS", 0)
        failed = status_counts.get("FAILURE", 0) + status_counts.get("REVOKED", 0)

        # Вычисляем процент выполнения
        completed = success + failed
        progress = (completed / total * 100) if total > 0 else 0

        return {
            "total_tasks": total,
            "pending_tasks": pending,
            "started_tasks": started,
            "success_tasks": success,
            "failed_tasks": failed,
            "progress_percentage": round(progress, 2),
        }

    def cleanup_old_tasks(self, days: int = 30) -> int:
        """
        Удаляет старые задачи

        Args:
            days: Возраст задач в днях для удаления

        Returns:
            int: Количество удаленных задач
        """
        from datetime import timedelta

        cutoff_date = get_current_time() - timedelta(days=days)

        deleted = (
            self.db.query(CeleryTaskStatus)
            .filter(CeleryTaskStatus.created_at < cutoff_date)
            .delete()
        )

        self.db.commit()
        logger.info(f"Удалено {deleted} старых задач (старше {days} дней)")
        return deleted
