"""
Сервис для работы с маппингом внутренних ID и DICOM UID
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.study import Series, SeriesDicomMapping, Study, StudyDicomMapping
from app.utils.helpers import get_current_time


class MappingService:
    """Сервис для работы с маппингом ID"""

    def __init__(self, db: Session):
        self.db = db

    def create_study(
        self,
        path_to_study: str,
        zip_path: Optional[str] = None,
        batch_id: Optional[int] = None,
    ) -> Study:
        """
        Создает новое исследование с внутренним ID

        Args:
            path_to_study: Название ZIP файла для отчета
            zip_path: Путь к ZIP файлу (может быть None)
            batch_id: ID батча загрузки (может быть None)

        Returns:
            Study: Созданное исследование
        """
        internal_id = str(uuid.uuid4())

        # Начинаем измерение времени обработки
        processing_start_time = get_current_time()
        current_time = get_current_time()

        study = Study(
            internal_id=internal_id,
            zip_path=zip_path,
            path_to_study=path_to_study,
            processing_status="Processing",
            processing_start_time=processing_start_time,
            updated_at=current_time,
            upload_batch_id=batch_id,
        )

        self.db.add(study)
        self.db.flush()

        return study

    def create_series(self, study_id: int) -> Series:
        """
        Создает новую серию с внутренним ID

        Args:
            study_id: ID исследования

        Returns:
            Series: Созданная серия
        """
        internal_id = str(uuid.uuid4())
        current_time = get_current_time()

        series = Series(
            study_id=study_id,
            internal_id=internal_id,
            processing_status="Pending",
            updated_at=current_time,
        )

        self.db.add(series)
        self.db.flush()

        return series

    def map_study_to_dicom_uid(self, study_id: int, study_instance_uid: str) -> StudyDicomMapping:
        """
        Создает маппинг исследования к DICOM StudyInstanceUID

        Args:
            study_id: ID исследования
            study_instance_uid: DICOM StudyInstanceUID

        Returns:
            StudyDicomMapping: Созданный маппинг
        """
        # Проверяем, существует ли уже маппинг
        existing_mapping = (
            self.db.query(StudyDicomMapping)
            .filter(StudyDicomMapping.study_instance_uid == study_instance_uid)
            .first()
        )

        if existing_mapping:
            # Если маппинг уже существует, возвращаем его
            return existing_mapping

        mapping = StudyDicomMapping(study_id=study_id, study_instance_uid=study_instance_uid)

        self.db.add(mapping)
        self.db.flush()

        return mapping

    def map_series_to_dicom_uid(
        self,
        series_id: int,
        series_instance_uid: str,
    ) -> SeriesDicomMapping:
        """
        Создает маппинг серии к DICOM SeriesInstanceUID

        Args:
            series_id: ID серии
            series_instance_uid: DICOM SeriesInstanceUID

        Returns:
            SeriesDicomMapping: Созданный маппинг
        """
        mapping = SeriesDicomMapping(series_id=series_id, series_instance_uid=series_instance_uid)

        self.db.add(mapping)
        self.db.flush()

        return mapping

    def get_study_by_internal_id(self, internal_id: str) -> Optional[Study]:
        """
        Получает исследование по внутреннему ID

        Args:
            internal_id: Внутренний ID исследования

        Returns:
            Study: Исследование или None
        """
        return self.db.query(Study).filter(Study.internal_id == internal_id).first()

    def get_study_by_dicom_uid(self, study_instance_uid: str) -> Optional[Study]:
        """
        Получает исследование по DICOM StudyInstanceUID

        Args:
            study_instance_uid: DICOM StudyInstanceUID

        Returns:
            Study: Исследование или None
        """
        mapping = (
            self.db.query(StudyDicomMapping)
            .filter(StudyDicomMapping.study_instance_uid == study_instance_uid)
            .first()
        )

        if mapping:
            return self.db.query(Study).filter(Study.id == mapping.study_id).first()

        return None

    def get_series_by_internal_id(self, internal_id: str) -> Optional[Series]:
        """
        Получает серию по внутреннему ID

        Args:
            internal_id: Внутренний ID серии

        Returns:
            Series: Серия или None
        """
        return self.db.query(Series).filter(Series.internal_id == internal_id).first()

    def get_series_by_dicom_uid(self, series_instance_uid: str) -> Optional[Series]:
        """
        Получает серию по DICOM SeriesInstanceUID

        Args:
            series_instance_uid: DICOM SeriesInstanceUID

        Returns:
            Series: Серия или None
        """
        mapping = (
            self.db.query(SeriesDicomMapping)
            .filter(SeriesDicomMapping.series_instance_uid == series_instance_uid)
            .first()
        )

        if mapping:
            return self.db.query(Series).filter(Series.id == mapping.series_id).first()

        return None

    def get_study_dicom_uid(self, study_id: int) -> Optional[str]:
        """
        Получает DICOM StudyInstanceUID для исследования

        Args:
            study_id: ID исследования

        Returns:
            str: DICOM StudyInstanceUID или None
        """
        mapping = (
            self.db.query(StudyDicomMapping).filter(StudyDicomMapping.study_id == study_id).first()
        )

        return mapping.study_instance_uid if mapping else None  # type: ignore

    def get_series_dicom_uid(self, series_id: int) -> Optional[str]:
        """
        Получает DICOM SeriesInstanceUID для серии

        Args:
            series_id: ID серии

        Returns:
            str: DICOM SeriesInstanceUID или None
        """
        mapping = (
            self.db.query(SeriesDicomMapping)
            .filter(SeriesDicomMapping.series_id == series_id)
            .first()
        )

        return mapping.series_instance_uid if mapping else None  # type: ignore
