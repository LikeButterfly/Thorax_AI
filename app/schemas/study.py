"""
Pydantic схемы для API с валидацией данных
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class UploadBatchResponse(BaseModel):
    """
    Схема ответа с данными батча загрузки

    Полная информация о батче загрузки с метаданными.
    """

    id: int = Field(description="Уникальный ID батча")
    upload_date: datetime = Field(description="Дата загрузки")
    total_studies: int = Field(ge=0, description="Общее количество исследований")
    processed_studies: int = Field(ge=0, description="Обработано исследований")
    failed_studies: int = Field(ge=0, description="Исследований с ошибками")
    is_active: bool = Field(description="Активность батча")
    is_cancelled: bool = Field(default=False, description="Отменен ли батч")
    processing_start_time: Optional[datetime] = Field(None, description="Время начала обработки")
    processing_end_time: Optional[datetime] = Field(None, description="Время окончания обработки")
    created_at: datetime = Field(description="Дата создания")
    updated_at: Optional[datetime] = Field(None, description="Дата обновления")

    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda v: v.isoformat()}


class UploadBatchListResponse(BaseModel):
    """
    Схема для списка батчей загрузки

    Краткая информация о батчах для списков.
    """

    id: int = Field(description="Уникальный ID батча")
    upload_date: datetime = Field(description="Дата загрузки")
    total_studies: int = Field(ge=0, description="Общее количество исследований")
    processed_studies: int = Field(ge=0, description="Обработано исследований")
    failed_studies: int = Field(ge=0, description="Исследований с ошибками")
    is_cancelled: bool = Field(default=False, description="Отменен ли батч")
    processing_start_time: Optional[datetime] = Field(None, description="Время начала обработки")
    processing_end_time: Optional[datetime] = Field(None, description="Время окончания обработки")

    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda v: v.isoformat()}


class SeriesResponse(BaseModel):
    """
    Схема ответа с данными серии

    Содержит информацию о серии DICOM файлов с результатами анализа.
    """

    id: int = Field(description="Уникальный ID серии")
    internal_id: str = Field(description="Внутренний UUID серии")
    series_uid: Optional[str] = Field(None, description="DICOM SeriesInstanceUID")
    dicom_dir: Optional[str] = Field(None, description="Путь к DICOM файлам")
    images_dir: Optional[str] = Field(None, description="Путь к изображениям")
    probability_of_pathology: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Вероятность патологии"
    )
    pathology: Optional[bool] = Field(None, description="Наличие патологии")
    processing_status: str = Field(description="Статус обработки")
    processing_time: Optional[float] = Field(None, ge=0.0, description="Время обработки в секундах")
    dicom_count: int = Field(ge=0, description="Количество DICOM файлов")
    created_at: datetime = Field(description="Дата создания")
    updated_at: Optional[datetime] = Field(None, description="Дата обновления")
    is_active: bool = Field(description="Активность записи")
    error_message: Optional[str] = Field(None, description="Сообщение об ошибке")

    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda v: v.isoformat()}


class StudyBase(BaseModel):
    """Базовая схема исследования"""

    pass


class StudyCreate(StudyBase):
    """Схема для создания исследования"""

    pass


class StudyUpdate(BaseModel):
    """
    Схема для обновления исследования

    Все поля опциональны для частичного обновления.
    """

    probability_of_pathology: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Вероятность патологии от 0.0 до 1.0",
    )
    pathology: Optional[bool] = Field(
        None,
        description="Наличие патологии: True/False/None",
    )
    processing_status: Optional[str] = Field(
        None,
        description="Статус обработки: Pending, Processing, Success, Failure",
    )
    processing_time: Optional[float] = Field(
        None,
        ge=0.0,
        description="Время обработки в секундах",
    )
    most_dangerous_pathology_type: Optional[str] = Field(
        None,
        max_length=255,
        description="Тип наиболее опасной патологии",
    )
    pathology_localization: Optional[str] = Field(
        None,
        description="JSON строка с координатами патологий",
    )
    error_message: Optional[str] = Field(
        None,
        description="Сообщение об ошибке обработки",
    )

    @field_validator("processing_status")
    @classmethod
    def validate_processing_status(cls, v):
        """Валидирует статус обработки"""
        if v is not None:
            allowed_statuses = {"Pending", "Processing", "Success", "Failure"}
            if v not in allowed_statuses:
                raise ValueError(f"processing_status must be one of {allowed_statuses}")
        return v

    @field_validator("most_dangerous_pathology_type")
    @classmethod
    def validate_pathology_type(cls, v):
        """Валидирует тип патологии"""
        if v is not None and len(v.strip()) == 0:
            raise ValueError("pathology_type cannot be empty string")
        return v.strip() if v else v


class StudyResponse(StudyBase):
    """
    Схема ответа с данными исследования

    Полная информация об исследовании включая результаты анализа
    и метаданные обработки.
    """

    # fmt: off
    id: int = Field(description="Уникальный ID исследования")
    internal_id: str = Field(description="Внутренний UUID исследования")
    study_uid: Optional[str] = Field(None, description="DICOM StudyInstanceUID")
    zip_path: Optional[str] = Field(None, description="Путь к ZIP архиву")
    path_to_study: str = Field(description="Название ZIP файла для отчета")
    study_path: Optional[str] = Field(None, description="Путь к основной папке с DICOM файлами в ZIP")  # noqa: E501
    probability_of_pathology: Optional[float] = Field(None, ge=0.0, le=1.0, description="Вероятность патологии")  # noqa: E501
    pathology: Optional[bool] = Field(None, description="Наличие патологии")
    ci_95: Optional[str] = Field(None, description="Доверительный интервал 95% для доли положительных кадров")  # noqa: E501
    is_single_dicom: bool = Field(False, description="Флаг: 1 DICOM файл в исследовании")
    processing_status: str = Field(description="Статус обработки")
    processing_start_time: Optional[datetime] = Field(None, description="Время начала обработки")
    processing_time: Optional[float] = Field(None, description="Время обработки в секундах")
    most_dangerous_pathology_type: Optional[str] = Field(None, description="Тип наиболее опасной патологии")  # noqa: E501
    pathology_localization: Optional[str] = Field(None, description="JSON с координатами патологий")  # noqa: E501
    # fmt: on

    # Статистика обработки
    total_files_found: int = Field(ge=0, description="Всего файлов в архиве")
    dicom_files_found: int = Field(ge=0, description="Найдено DICOM файлов")
    valid_ct_files: int = Field(ge=0, description="Валидных CT файлов")
    processed_series_count: int = Field(ge=0, description="Обработано серий")
    skipped_series_count: int = Field(ge=0, description="Пропущено серий")

    # Метаданные
    created_at: datetime = Field(description="Дата создания")
    updated_at: Optional[datetime] = Field(None, description="Дата обновления")
    is_active: bool = Field(description="Активность записи")
    error_message: Optional[str] = Field(None, description="Сообщение об ошибке")

    # Связанные данные
    series: List[SeriesResponse] = Field(default_factory=list, description="Список серий")

    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda v: v.isoformat()}


class StudyListResponse(BaseModel):
    """
    Схема для списка исследований с пагинацией

    Содержит список исследований и метаданные пагинации.
    """

    studies: List[StudyResponse] = Field(description="Список исследований")
    total: int = Field(ge=0, description="Общее количество исследований")
    page: int = Field(ge=1, description="Номер страницы")
    size: int = Field(ge=1, le=100, description="Размер страницы")

    @field_validator("page")
    @classmethod
    def validate_page(cls, v, info):
        """Валидирует номер страницы"""
        if info.data and "total" in info.data and "size" in info.data:
            max_pages = (info.data["total"] + info.data["size"] - 1) // info.data["size"]
            if v > max_pages and max_pages > 0:
                raise ValueError(f"Page {v} exceeds maximum pages {max_pages}")
        return v


class UploadResponse(BaseModel):
    """
    Схема ответа при загрузке исследований

    Содержит информацию о результатах загрузки и обработки файлов.
    """

    message: str = Field(description="Сообщение о результате загрузки")
    batch_id: int = Field(ge=1, description="ID батча загрузки")
    total_files: int = Field(ge=0, description="Общее количество файлов")
    processed_files: int = Field(ge=0, description="Успешно обработано файлов")
    failed_files: int = Field(ge=0, description="Файлов с ошибками")
    processing_status: str = Field(description="Статус обработки")

    @field_validator("processing_status")
    @classmethod
    def validate_processing_status(cls, v):
        """Валидирует статус обработки"""
        allowed_statuses = {"Completed", "Partial", "Failed"}
        if v not in allowed_statuses:
            raise ValueError(f"processing_status must be one of {allowed_statuses}")
        return v

    @field_validator("processed_files", "failed_files")
    @classmethod
    def validate_file_counts(cls, v, info):
        """Валидирует количество файлов"""
        if info.data and "total_files" in info.data:
            if v > info.data["total_files"]:
                raise ValueError("Processed/failed files cannot exceed total files")
        return v


class AsyncUploadResponse(BaseModel):
    """
    Схема ответа при асинхронной загрузке исследований

    Возвращается немедленно после постановки задач в очередь.
    """

    message: str = Field(description="Сообщение о результате")
    batch_id: int = Field(ge=1, description="ID батча загрузки")
    total_files: int = Field(ge=0, description="Общее количество файлов")
    queued_tasks: int = Field(ge=0, description="Задач поставлено в очередь")
    task_ids: List[str] = Field(description="ID задач Celery")


class TaskStatusResponse(BaseModel):
    """
    Схема статуса одной задачи
    """

    task_id: str = Field(description="ID задачи Celery")
    filename: str = Field(description="Имя файла")
    status: str = Field(description="Статус задачи")
    study_id: Optional[int] = Field(None, description="ID исследования")
    error_message: Optional[str] = Field(None, description="Сообщение об ошибке")
    created_at: datetime = Field(description="Время создания задачи")
    started_at: Optional[datetime] = Field(None, description="Время начала выполнения")
    completed_at: Optional[datetime] = Field(None, description="Время завершения")

    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda v: v.isoformat()}


class BatchStatusResponse(BaseModel):
    """
    Схема статуса батча с задачами
    """

    batch_id: int = Field(description="ID батча")
    total_tasks: int = Field(ge=0, description="Всего задач")
    pending_tasks: int = Field(ge=0, description="Ожидают выполнения")
    started_tasks: int = Field(ge=0, description="Выполняются")
    success_tasks: int = Field(ge=0, description="Успешно завершены")
    failed_tasks: int = Field(ge=0, description="Завершены с ошибкой")
    progress_percentage: float = Field(ge=0, le=100, description="Процент выполнения")
    tasks: List[TaskStatusResponse] = Field(description="Детали задач")
