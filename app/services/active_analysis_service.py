"""
Сервис для управления активными загрузками
"""

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models.study import ActiveAnalysis
from app.utils.helpers import get_current_time

logger = logging.getLogger(__name__)


class ActiveAnalysisService:
    """Сервис для управления активными загрузками"""

    def __init__(self, db: Session):
        self.db = db

    def start_upload(self) -> bool:
        """
        Запускает отслеживание активной загрузки

        Returns:
            bool: Успешность создания записи
        """
        try:
            # Создаем запись об активной загрузке
            active_analysis = ActiveAnalysis(started_at=get_current_time())

            self.db.add(active_analysis)
            self.db.commit()

            logger.info("Запущена активная загрузка")
            return True

        except Exception as e:
            self.db.rollback()
            logger.error(f"Ошибка при запуске отслеживания загрузки: {str(e)}")
            return False

    def complete_upload(self) -> bool:
        """
        Завершает отслеживание активной загрузки

        Returns:
            bool: Успешность завершения
        """
        try:
            # Удаляем все активные записи
            deleted_count = self.db.query(ActiveAnalysis).delete()
            self.db.commit()

            logger.info(f"Завершена активная загрузка, удалено записей: {deleted_count}")
            return True

        except Exception as e:
            self.db.rollback()
            logger.error(f"Ошибка при завершении отслеживания загрузки: {str(e)}")
            return False

    def has_active_analyses(self) -> bool:
        """
        Проверяет, есть ли активные загрузки

        Returns:
            bool: True если есть активные загрузки
        """
        try:
            count = self.db.query(ActiveAnalysis).count()
            return count > 0
        except Exception as e:
            logger.error(f"Ошибка при проверке активных загрузок: {str(e)}")
            return True  # В случае ошибки считаем, что есть активные загрузки (безопасность)
