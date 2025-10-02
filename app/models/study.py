"""
Модели для хранения данных о КТ исследованиях
"""

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.database import Base


class UploadBatch(Base):
    """
    Модель для группировки загрузок по дате

    Хранит информацию о батчах загрузки файлов с метаданными
    и статистикой обработки.
    """

    __tablename__ = "upload_batches"

    id = Column(Integer, primary_key=True, index=True)
    upload_date = Column(DateTime, nullable=False, default=func.now(), index=True)
    total_studies = Column(Integer, default=0, nullable=False)
    processed_studies = Column(Integer, default=0, nullable=False)
    failed_studies = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    # Constraints для валидации данных
    __table_args__ = (
        CheckConstraint("total_studies >= 0", name="check_total_studies_positive"),
        CheckConstraint("processed_studies >= 0", name="check_processed_studies_positive"),
        CheckConstraint("failed_studies >= 0", name="check_failed_studies_positive"),
        CheckConstraint(
            "processed_studies + failed_studies <= total_studies", name="check_studies_sum_valid"
        ),
        Index("idx_upload_batches_date_active", "upload_date", "is_active"),
    )

    # Связь с исследованиями
    studies = relationship("Study", back_populates="upload_batch")


class Study(Base):
    """
    Модель для хранения информации о КТ исследовании

    Основная модель для хранения данных о медицинских исследованиях
    с результатами анализа патологий и метаданными.
    """

    __tablename__ = "studies"

    id = Column(Integer, primary_key=True, index=True)
    internal_id = Column(
        String(36), unique=True, index=True, nullable=False
    )  # UUID для внутреннего использования

    # Пути к файлам
    zip_path = Column(String(500), nullable=True)  # Путь к ZIP архиву
    path_to_study = Column(
        String(500), nullable=False, index=True
    )  # Название ZIP файла для отчета (на самом деле это название zip)
    study_path = Column(
        String(1000), nullable=True
    )  # Путь к основной папке с DICOM файлами в ZIP (а это на самом деле path_to_study)

    # Результаты анализа (агрегированные по всем сериям)
    probability_of_pathology = Column(Float, nullable=True)  # null - не анализировалось
    pathology = Column(
        Boolean, nullable=True, index=True
    )  # null - не известно, False - норма, True - патология
    ci_95 = Column(
        String(50), nullable=True
    )  # Доверительный интервал 95% для доли положительных кадров
    processing_status = Column(
        String(50), default="Pending", nullable=False, index=True
    )  # Pending, Processing, Success, Failure
    processing_start_time = Column(
        DateTime(timezone=True), nullable=True
    )  # Время начала обработки  # noqa: E501
    processing_time = Column(Float, nullable=True)  # Время обработки в секундах
    is_files_deleted = Column(Boolean, default=False, nullable=False)  # Флаг удаления файлов

    # Дополнительная информация
    most_dangerous_pathology_type = Column(String(255), nullable=True)
    pathology_localization = Column(Text, nullable=True)  # JSON строка с координатами

    # Информация о найденных патологиях
    pathology_images = Column(
        Text, nullable=True
    )  # JSON список названий картинок с патологиями  # noqa: E501
    pathology_dicom_files = Column(Text, nullable=True)  # JSON список исходных DICOM файлов
    is_single_dicom = Column(
        Boolean, default=False, nullable=False
    )  # Флаг: 1 DICOM файл в исследовании

    # Статистика обработки
    total_files_found = Column(Integer, default=0, nullable=False)  # Всего файлов в архиве
    dicom_files_found = Column(Integer, default=0, nullable=False)  # Найдено DICOM файлов
    valid_ct_files = Column(Integer, default=0, nullable=False)  # Валидных CT файлов
    processed_series_count = Column(Integer, default=0, nullable=False)  # Обработано серий
    skipped_series_count = Column(Integer, default=0, nullable=False)  # Пропущено серий

    # Метаданные
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False, index=True)

    # Ошибки обработки
    error_message = Column(Text, nullable=True)

    # Связь с батчем загрузки
    upload_batch_id = Column(Integer, ForeignKey("upload_batches.id"), nullable=True, index=True)

    # Constraints для валидации данных
    __table_args__ = (
        CheckConstraint(
            "probability_of_pathology >= 0.0 AND probability_of_pathology <= 1.0",
            name="check_probability_range",
        ),
        CheckConstraint("processing_time >= 0.0", name="check_processing_time_positive"),
        CheckConstraint("total_files_found >= 0", name="check_total_files_positive"),
        CheckConstraint("dicom_files_found >= 0", name="check_dicom_files_positive"),
        CheckConstraint("valid_ct_files >= 0", name="check_valid_files_positive"),
        CheckConstraint("processed_series_count >= 0", name="check_processed_series_positive"),
        CheckConstraint("skipped_series_count >= 0", name="check_skipped_series_positive"),
        CheckConstraint(
            "processing_status IN ('Pending', 'Processing', 'Success', 'Failure')",
            name="check_processing_status_valid",
        ),
        Index("idx_studies_status_pathology", "processing_status", "pathology"),
        Index("idx_studies_created_active", "created_at", "is_active"),
        Index("idx_studies_batch", "upload_batch_id", "is_active"),
    )

    # Связь с сериями
    series = relationship("Series", back_populates="study", cascade="all, delete-orphan")
    # Связь с маппингом DICOM UID
    dicom_mappings = relationship(
        "StudyDicomMapping", back_populates="study", cascade="all, delete-orphan"
    )
    # Связь с батчем загрузки
    upload_batch = relationship("UploadBatch", back_populates="studies")


class Series(Base):
    """
    Модель для хранения информации о серии DICOM файлов

    Представляет отдельную серию DICOM файлов в рамках исследования
    с результатами анализа и метаданными.
    """

    __tablename__ = "series"

    id = Column(Integer, primary_key=True, index=True)
    study_id = Column(Integer, ForeignKey("studies.id"), nullable=False, index=True)
    internal_id = Column(
        String(36), unique=True, index=True, nullable=False
    )  # UUID для внутреннего использования

    # Пути к файлам
    dicom_dir = Column(String(500), nullable=True)  # Путь к DICOM файлам серии
    images_dir = Column(String(500), nullable=True)  # Путь к извлеченным изображениям

    # Результаты анализа для конкретной серии
    probability_of_pathology = Column(Float, nullable=True)  # null - не анализировалось
    pathology = Column(
        Boolean, nullable=True, index=True
    )  # null - не известно, False - норма, True - патология
    processing_status = Column(
        String(50), default="Pending", nullable=False, index=True
    )  # Pending, Processing, Success, Failure
    processing_time = Column(Float, nullable=True)  # Время обработки в секундах

    # Количество DICOM файлов в серии
    dicom_count = Column(Integer, default=0, nullable=False)

    # Метаданные
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False, index=True)

    # Ошибки обработки
    error_message = Column(Text, nullable=True)

    # Constraints для валидации данных
    __table_args__ = (
        CheckConstraint(
            "probability_of_pathology >= 0.0 AND probability_of_pathology <= 1.0",
            name="check_series_probability_range",
        ),
        CheckConstraint("processing_time >= 0.0", name="check_series_processing_time_positive"),
        CheckConstraint("dicom_count >= 0", name="check_dicom_count_positive"),
        CheckConstraint(
            "processing_status IN ('Pending', 'Processing', 'Success', 'Failure')",
            name="check_series_processing_status_valid",
        ),
        Index("idx_series_study_active", "study_id", "is_active"),
        Index("idx_series_status_pathology", "processing_status", "pathology"),
        Index("idx_series_created", "created_at"),
    )

    # Связь с исследованием
    study = relationship("Study", back_populates="series")
    # Связь с маппингом DICOM UID
    dicom_mappings = relationship(
        "SeriesDicomMapping", back_populates="series", cascade="all, delete-orphan"
    )


class StudyDicomMapping(Base):
    """
    Маппинг внутреннего ID исследования к DICOM StudyInstanceUID

    Связывает внутренние ID исследований с DICOM UID для совместимости
    с медицинскими стандартами.
    """

    __tablename__ = "study_dicom_mappings"

    id = Column(Integer, primary_key=True, index=True)
    study_id = Column(Integer, ForeignKey("studies.id"), nullable=False, index=True)
    study_instance_uid = Column(String(255), unique=True, index=True, nullable=False)

    # Метаданные
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Constraints для валидации данных
    __table_args__ = (
        CheckConstraint("LENGTH(study_instance_uid) > 0", name="check_study_uid_not_empty"),
        Index("idx_study_mapping_study", "study_id"),
    )

    # Связь с исследованием
    study = relationship("Study", back_populates="dicom_mappings")


class SeriesDicomMapping(Base):
    """
    Маппинг внутреннего ID серии к DICOM SeriesInstanceUID

    Связывает внутренние ID серий с DICOM UID для совместимости
    с медицинскими стандартами.
    """

    __tablename__ = "series_dicom_mappings"

    id = Column(Integer, primary_key=True, index=True)
    series_id = Column(Integer, ForeignKey("series.id"), nullable=False, index=True)
    series_instance_uid = Column(String(255), unique=True, index=True, nullable=False)

    # Метаданные
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Constraints для валидации данных
    __table_args__ = (
        CheckConstraint("LENGTH(series_instance_uid) > 0", name="check_series_uid_not_empty"),
        Index("idx_series_mapping_series", "series_id"),
    )

    # Связь с серией
    series = relationship("Series", back_populates="dicom_mappings")


class ActiveAnalysis(Base):
    """
    Модель для отслеживания активных загрузок

    Простой флаг для предотвращения удаления файлов во время обработки.
    """

    __tablename__ = "active_analyses"

    id = Column(Integer, primary_key=True, index=True)
    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
