"""
Сервис для работы с исследованиями
"""

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.models.study import Series, Study
from app.schemas.study import StudyCreate, StudyUpdate
from app.services.base_service import BaseService
from app.utils.helpers import get_current_time

logger = logging.getLogger(__name__)


class StudyService(BaseService[Study]):
    """
    Сервис для работы с исследованиями

    Расширяет базовый сервис специфичными методами для исследований.
    """

    def __init__(self, db: Session):
        super().__init__(db, Study)

    def create_study(
        self, path_to_study: str, zip_path: Optional[str] = None, batch_id: Optional[int] = None
    ) -> Study:
        """
        Создает новое исследование в базе данных

        Args:
            path_to_study: Название ZIP файла для отчета
            zip_path: Путь к ZIP файлу (может быть None)
            batch_id: ID батча загрузки (может быть None)

        Returns:
            Study: Созданное исследование
        """
        # Начинаем измерение времени обработки
        processing_start_time = get_current_time()

        study_data = {
            "path_to_study": path_to_study,
            "zip_path": zip_path,
            "upload_batch_id": batch_id,
            "processing_status": "Processing",
            "processing_start_time": processing_start_time,
        }

        study = self.create(**study_data)
        self.commit()

        logger.info(f"Создано исследование {study.id} для файла {path_to_study}")
        return study

    def get_study_with_series(self, study_id: int) -> Optional[Study]:
        """
        Получает исследование с сериями по ID

        Args:
            study_id: ID исследования

        Returns:
            Study: Исследование с сериями или None
        """
        try:
            return (
                self.db.query(Study)
                .options(joinedload(Study.series))
                .filter(Study.id == study_id, Study.is_active)
                .first()
            )
        except Exception as e:
            logger.error(f"Ошибка при получении исследования {study_id}: {e}")
            return None

    def get_study_by_path(self, path_to_study: str) -> Optional[Study]:
        """
        Получает исследование по пути к файлу

        Args:
            path_to_study: Путь к файлу исследования

        Returns:
            Study: Исследование или None
        """
        return self.get_by_field("path_to_study", path_to_study)

    def get_studies(
        self,
        skip: int = 0,
        limit: int = 100,
        status: Optional[str] = None,
        pathology: Optional[bool] = None,
        search: Optional[str] = None,
        batch_id: Optional[int] = None,
    ) -> Tuple[List[Study], int]:
        """
        Получает список исследований с фильтрацией

        Args:
            skip: Количество пропущенных записей
            limit: Максимальное количество записей
            status: Фильтр по статусу
            pathology: Фильтр по наличию патологии
            search: Поиск по названию
            batch_id: Фильтр по батчу

        Returns:
            Tuple[List[Study], int]: (список исследований, общее количество)
        """
        try:
            query = self.db.query(Study).filter(Study.is_active)

            # Применяем фильтры
            if status:
                query = query.filter(Study.processing_status == status)

            if pathology is not None:
                query = query.filter(Study.pathology == pathology)

            if search:
                query = query.filter(Study.path_to_study.ilike(f"%{search}%"))

            if batch_id:
                query = query.filter(Study.upload_batch_id == batch_id)

            # Получаем общее количество записей
            total = query.count()

            # Получаем данные с пагинацией
            studies = query.order_by(Study.created_at.desc()).offset(skip).limit(limit).all()

            return studies, total
        except Exception as e:
            logger.error(f"Ошибка при получении списка исследований: {e}")
            return [], 0

    def update_study(self, study_id: int, study_data: StudyUpdate) -> Optional[Study]:
        """
        Обновляет исследование

        Args:
            study_id: ID исследования
            study_data: Данные для обновления

        Returns:
            Study: Обновленное исследование или None
        """
        try:
            # Преобразуем Pydantic модель в словарь
            update_data = study_data.dict(exclude_unset=True)

            # Обновляем запись
            study = self.update(study_id, **update_data)
            if study:
                self.commit()
                logger.info(f"Обновлено исследование {study_id}")
            return study
        except Exception as e:
            logger.error(f"Ошибка при обновлении исследования {study_id}: {e}")
            self.rollback()
            return None

    def complete_processing(
        self, study_id: int, success: bool = True, error_message: Optional[str] = None
    ) -> Optional[Study]:
        """
        Завершает обработку исследования и вычисляет время обработки

        Args:
            study_id: ID исследования
            success: Успешность обработки
            error_message: Сообщение об ошибке (если есть)

        Returns:
            Study: Обновленное исследование или None
        """
        try:
            study = self.get_by_id(study_id)
            if not study:
                logger.error(f"Исследование {study_id} не найдено")
                return None

            # Вычисляем время обработки
            processing_time = None
            if study.processing_start_time:  # type: ignore
                processing_end_time = get_current_time()
                processing_time = (
                    processing_end_time - study.processing_start_time
                ).total_seconds()
                logger.info(
                    f"Время обработки исследования {study_id}: {processing_time:.2f} секунд"
                )
            else:
                logger.warning(f"Время начала обработки не найдено для исследования {study_id}")

            # Обновляем статус и время обработки
            update_data = {
                "processing_status": "Success" if success else "Failure",
                "processing_time": processing_time,
            }

            if error_message:
                update_data["error_message"] = error_message

            study = self.update(study_id, **update_data)
            if study:
                self.commit()
                logger.info(
                    f"Завершена обработка исследования {study_id}, "
                    f"статус: {update_data['processing_status']}"
                )
            return study
        except Exception as e:
            logger.error(f"Ошибка при завершении обработки исследования {study_id}: {e}")
            self.rollback()
            return None

    def delete_study(self, study_id: int) -> bool:
        """
        Удаляет исследование (мягкое удаление)

        Args:
            study_id: ID исследования

        Returns:
            bool: True если успешно
        """
        try:
            success = self.delete(study_id)
            if success:
                self.commit()
                logger.info(f"Удалено исследование {study_id}")
            return success
        except Exception as e:
            logger.error(f"Ошибка при удалении исследования {study_id}: {e}")
            self.rollback()
            return False

    def get_series_by_study(self, study_id: int) -> List[Series]:
        """
        Получает все серии для исследования

        Args:
            study_id: ID исследования

        Returns:
            List[Series]: Список серий
        """
        try:
            return (
                self.db.query(Series)
                .filter(Series.study_id == study_id, Series.is_active)
                .order_by(Series.created_at)
                .all()
            )
        except Exception as e:
            logger.error(f"Ошибка при получении серий для исследования {study_id}: {e}")
            return []

    def get_series(self, series_id: int) -> Optional[Series]:
        """
        Получает серию по ID

        Args:
            series_id: ID серии

        Returns:
            Series: Серия или None
        """
        try:
            return self.db.query(Series).filter(Series.id == series_id, Series.is_active).first()
        except Exception as e:
            logger.error(f"Ошибка при получении серии {series_id}: {e}")
            return None

    def update_series(self, series_id: int, **kwargs) -> Optional[Series]:
        """
        Обновляет серию

        Args:
            series_id: ID серии
            **kwargs: Поля для обновления

        Returns:
            Series: Обновленная серия или None
        """
        try:
            series = self.get_series(series_id)
            if not series:
                return None

            for field, value in kwargs.items():
                if hasattr(series, field):
                    setattr(series, field, value)

            self.db.commit()
            self.db.refresh(series)

            logger.info(f"Обновлена серия {series_id}")
            return series
        except Exception as e:
            logger.error(f"Ошибка при обновлении серии {series_id}: {e}")
            self.db.rollback()
            return None

    def get_studies_statistics(self) -> Dict[str, int]:
        """
        Получает статистику по исследованиям

        Returns:
            Dict[str, int]: Статистика исследований
        """
        try:
            total = self.count()
            active = self.count({"is_active": True})
            with_pathology = self.count({"pathology": True})
            processed = self.count({"processing_status": "Success"})

            return {
                "total": total,
                "active": active,
                "with_pathology": with_pathology,
                "processed": processed,
                "pending": total - processed,
            }
        except Exception as e:
            logger.error(f"Ошибка при получении статистики: {e}")
            return {}

    def validate_data(self, data: Dict[str, Any]) -> bool:
        """
        Валидирует данные исследования

        Args:
            data: Данные для валидации

        Returns:
            bool: True если данные валидны
        """
        try:
            # Проверяем обязательные поля
            required_fields = ["path_to_study"]
            for field in required_fields:
                if field not in data or not data[field]:
                    logger.error(f"Отсутствует обязательное поле: {field}")
                    return False

            # Валидируем вероятность патологии
            if "probability_of_pathology" in data and data["probability_of_pathology"] is not None:
                prob = data["probability_of_pathology"]
                if not (0.0 <= prob <= 1.0):
                    logger.error(f"Некорректная вероятность патологии: {prob}")
                    return False

            # Валидируем время обработки
            if "processing_time" in data and data["processing_time"] is not None:
                time_val = data["processing_time"]
                if time_val < 0:
                    logger.error(f"Отрицательное время обработки: {time_val}")
                    return False

            # Валидируем статус обработки
            if "processing_status" in data and data["processing_status"] is not None:
                status = data["processing_status"]
                allowed_statuses = {"Pending", "Processing", "Success", "Failure"}
                if status not in allowed_statuses:
                    logger.error(f"Некорректный статус обработки: {status}")
                    return False

            return True
        except Exception as e:
            logger.error(f"Ошибка при валидации данных: {e}")
            return False
