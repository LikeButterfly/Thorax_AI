"""
Сервис для работы с батчами загрузки
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.study import UploadBatch
from app.services.base_service import BaseService
from app.utils.helpers import get_current_time

logger = logging.getLogger(__name__)


class UploadBatchService(BaseService[UploadBatch]):
    """
    Сервис для работы с батчами загрузки

    Расширяет базовый сервис специфичными методами для батчей загрузки.
    """

    def __init__(self, db: Session):
        super().__init__(db, UploadBatch)

    def create_batch(self) -> int:
        """
        Создать новый батч загрузки и вернуть его ID

        Returns:
            int: ID созданного батча
        """
        try:
            batch_data = {
                "upload_date": get_current_time(),
                "total_studies": 0,
                "processed_studies": 0,
                "failed_studies": 0,
            }

            batch = self.create(**batch_data)
            self.commit()

            logger.info(f"Создан батч загрузки {batch.id}")
            return batch.id  # type: ignore
        except Exception as e:
            logger.error(f"Ошибка при создании батча: {e}")
            self.rollback()
            raise

    def get_batch(self, batch_id: int) -> Optional[UploadBatch]:
        """
        Получить батч по ID

        Args:
            batch_id: ID батча

        Returns:
            UploadBatch: Батч или None
        """
        return self.get_by_id(batch_id)

    def get_batches(self, limit: int = 50, offset: int = 0) -> List[UploadBatch]:
        """
        Получить список батчей с пагинацией

        Args:
            limit: Максимальное количество записей
            offset: Количество пропущенных записей

        Returns:
            List[UploadBatch]: Список батчей
        """
        try:
            return (
                self.db.query(UploadBatch)
                .filter(UploadBatch.is_active)
                .order_by(UploadBatch.upload_date.desc())
                .offset(offset)
                .limit(limit)
                .all()
            )
        except Exception as e:
            logger.error(f"Ошибка при получении списка батчей: {e}")
            return []

    def update_batch_stats(self, batch_id: int, total: int, processed: int, failed: int) -> bool:
        """
        Обновить статистику батча

        Args:
            batch_id: ID батча
            total: Общее количество исследований
            processed: Обработано исследований
            failed: Исследований с ошибками

        Returns:
            bool: True если успешно
        """
        try:
            # Валидируем данные
            if total < 0 or processed < 0 or failed < 0:
                logger.error("Отрицательные значения в статистике батча")
                return False

            if processed + failed > total:
                logger.error("Сумма обработанных и неудачных превышает общее количество")
                return False

            # Обновляем статистику
            success = self.update(
                batch_id, total_studies=total, processed_studies=processed, failed_studies=failed
            )

            if success:
                self.commit()
                logger.info(f"Обновлена статистика батча {batch_id}")

            return success is not None
        except Exception as e:
            logger.error(f"Ошибка при обновлении статистики батча {batch_id}: {e}")
            self.rollback()
            return False

    def get_batch_studies(self, batch_id: int) -> List:
        """
        Получить исследования батча

        Args:
            batch_id: ID батча

        Returns:
            List: Список исследований батча
        """
        try:
            batch = self.get_batch(batch_id)
            if batch:
                return batch.studies
            return []
        except Exception as e:
            logger.error(f"Ошибка при получении исследований батча {batch_id}: {e}")
            return []

    def get_batch_statistics(self, batch_id: int) -> Dict[str, int]:
        """
        Получить статистику батча

        Args:
            batch_id: ID батча

        Returns:
            Dict[str, int]: Статистика батча
        """
        try:
            batch = self.get_batch(batch_id)
            if not batch:
                return {}

            return {
                "total_studies": batch.total_studies,  # type: ignore
                "processed_studies": batch.processed_studies,  # type: ignore
                "failed_studies": batch.failed_studies,  # type: ignore
                "success_rate": int(
                    (batch.processed_studies / batch.total_studies * 100)  # type: ignore
                    if batch.total_studies > 0  # type: ignore
                    else 0
                ),
            }
        except Exception as e:
            logger.error(f"Ошибка при получении статистики батча {batch_id}: {e}")
            return {}

    def validate_data(self, data: Dict[str, Any]) -> bool:
        """
        Валидирует данные батча

        Args:
            data: Данные для валидации

        Returns:
            bool: True если данные валидны
        """
        try:
            # Проверяем обязательные поля
            required_fields = ["upload_date"]
            for field in required_fields:
                if field not in data:
                    logger.error(f"Отсутствует обязательное поле: {field}")
                    return False

            # Валидируем числовые поля
            numeric_fields = ["total_studies", "processed_studies", "failed_studies"]
            for field in numeric_fields:
                if field in data and data[field] is not None:
                    value = data[field]
                    if not isinstance(value, int) or value < 0:
                        logger.error(f"Некорректное значение поля {field}: {value}")
                        return False

            # Проверяем логику статистики
            if all(field in data for field in numeric_fields):
                total = data.get("total_studies", 0)
                processed = data.get("processed_studies", 0)
                failed = data.get("failed_studies", 0)

                if processed + failed > total:
                    logger.error("Сумма обработанных и неудачных превышает общее количество")
                    return False

            return True
        except Exception as e:
            logger.error(f"Ошибка при валидации данных батча: {e}")
            return False
