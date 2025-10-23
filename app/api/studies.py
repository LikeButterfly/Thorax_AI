"""
API endpoints для работы с исследованиями
"""

import base64
import logging
import os
import uuid
from typing import List, Optional

import aiofiles
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import get_db
from app.models.study import Study
from app.schemas.study import (
    AsyncUploadResponse,
    BatchStatusResponse,
    StudyListResponse,
    StudyResponse,
    StudyUpdate,
    TaskStatusResponse,
    UploadBatchListResponse,
    UploadResponse,
)
from app.services.active_analysis_service import ActiveAnalysisService
from app.services.ml_client_service import MLClientService
from app.services.pathology_detection_service import PathologyDetectionService
from app.services.report_service import ReportService
from app.services.study_processing_service import StudyProcessingService
from app.services.study_service import StudyService
from app.services.task_service import TaskService
from app.services.upload_batch_service import UploadBatchService
from app.tasks.study_tasks import process_single_study_task

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/studies", tags=["studies"])


@router.post("/upload-async", response_model=AsyncUploadResponse)
async def upload_studies_async(
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    """
    Асинхронная загрузка множественных ZIP файлов с DICOM исследованиями

    Ставит файлы в очередь на обработку и немедленно возвращает ответ.
    Используйте /batches/{batch_id}/status для проверки прогресса.

    Args:
        files: Список ZIP файлов с DICOM исследованиями
        db: Сессия базы данных

    Returns:
        AsyncUploadResponse: Результат постановки задач в очередь
    """
    try:
        # Валидация входных данных
        if not files:
            raise HTTPException(status_code=400, detail="Необходимо загрузить хотя бы один файл")

        if len(files) > 400:
            raise HTTPException(status_code=400, detail="Максимум 400 файлов за раз")

        # Проверяем файлы
        for file in files:
            if not file.filename:
                raise HTTPException(status_code=400, detail="Файл без имени не поддерживается")

            if not file.filename.endswith(".zip"):
                raise HTTPException(
                    status_code=400, detail=f"Файл {file.filename} не является ZIP архивом"
                )

        # Проверяем доступность ML сервиса в самом начале
        ml_client = MLClientService()
        ml_health = await ml_client.check_ml_service_health()
        if not ml_health.get("available"):
            raise HTTPException(
                status_code=503,
                detail=(
                    "ML сервис недоступен. Анализ патологий невозможен. "
                    "Проверьте, что ML сервис запущен и доступен."
                ),
            )

        # Проверяем, нет ли уже активных загрузок (синхронных)
        active_analysis_service = ActiveAnalysisService(db)
        if active_analysis_service.has_active_analyses():
            raise HTTPException(
                status_code=409,
                detail=(
                    "Уже выполняется синхронная загрузка и обработка исследований. "
                    "Дождитесь завершения текущей операции."
                ),
            )

        # Создаем батч загрузки
        batch_service = UploadBatchService(db)
        batch_id = batch_service.create_batch()

        # Устанавливаем время начала обработки
        batch_service.set_processing_start(batch_id)

        # Инициализируем TaskService
        task_service = TaskService(db)

        task_ids = []
        queued_count = 0

        # Ставим каждый файл в очередь Celery
        for file in files:
            try:
                # Читаем содержимое файла
                content = await file.read()
                file_size = len(content)

                # Проверяем размер файла
                if file_size > settings.max_file_size:
                    logger.warning(
                        f"Файл {file.filename} слишком большой ({file_size} bytes), пропускаем"
                    )
                    continue

                # Кодируем содержимое в base64 для передачи в Celery
                file_content_base64 = base64.b64encode(content).decode("utf-8")

                # Создаем задачу Celery
                task = process_single_study_task.apply_async(
                    args=[
                        file.filename,
                        file_content_base64,
                        batch_id,
                        settings.save_zip_files,
                    ],
                )

                # Сохраняем статус задачи в БД
                task_service.create_task_status(
                    task_id=task.id,
                    batch_id=batch_id,
                    filename=file.filename or "unknown.zip",
                    status="PENDING",
                )

                task_ids.append(task.id)
                queued_count += 1

                logger.info(f"Файл {file.filename} поставлен в очередь (task_id: {task.id})")

            except Exception as e:
                logger.error(f"Ошибка при постановке файла {file.filename} в очередь: {str(e)}")
                continue

        # Обновляем статистику батча (пока все задачи pending)
        batch_service.update_batch_stats(batch_id, len(files), 0, 0)

        message = (
            f"Всего файлов: {len(files)}. "
            f"Задач поставлено в очередь: {queued_count}. "
            f"Используйте /batches/{batch_id}/status для проверки прогресса."
        )

        return AsyncUploadResponse(
            message=message,
            batch_id=batch_id,
            total_files=len(files),
            queued_tasks=queued_count,
            task_ids=task_ids,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при асинхронной загрузке файлов: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Ошибка при постановке файлов в очередь: {str(e)}"
        ) from e


@router.post("/upload", response_model=UploadResponse)
async def upload_studies(
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    """
    Загружает множественные ZIP файлы с DICOM исследованиями

    Обрабатывает загрузку и анализ медицинских исследований.
    Поддерживает до 400 файлов за раз с максимальным размером 2GB.

    Args:
        files: Список ZIP файлов с DICOM исследованиями
        db: Сессия базы данных

    Returns:
        UploadResponse: Результат загрузки и обработки

    Raises:
        HTTPException: Ошибки валидации или обработки
    """
    try:
        # Проверяем, нет ли уже активных загрузок
        active_analysis_service = ActiveAnalysisService(db)
        if active_analysis_service.has_active_analyses():
            raise HTTPException(
                status_code=409,
                detail=(
                    "Уже выполняется загрузка и обработка исследований. "
                    "Дождитесь завершения текущей операции."
                ),
            )

        # Запускаем отслеживание активной загрузки
        if not active_analysis_service.start_upload():
            raise HTTPException(status_code=500, detail="Ошибка при запуске отслеживания загрузки")

        # Проверяем доступность ML сервиса в самом начале
        ml_client = MLClientService()
        if not await ml_client.check_ml_service_health():
            raise HTTPException(
                status_code=503,
                detail=(
                    "ML сервис недоступен. Анализ патологий невозможен. "
                    "Проверьте, что ML сервис запущен и доступен.",
                ),
            )

        # Валидация входных данных
        if not files:
            raise HTTPException(status_code=400, detail="Необходимо загрузить хотя бы один файл")

        if len(files) > 400:
            raise HTTPException(status_code=400, detail="Максимум 400 файлов за раз")

        # Проверяем размер каждого файла
        for file in files:
            if not file.filename:
                raise HTTPException(status_code=400, detail="Файл без имени не поддерживается")

            if not file.filename.endswith(".zip"):
                raise HTTPException(
                    status_code=400, detail=f"Файл {file.filename} не является ZIP архивом"
                )

        # Создаем батч загрузки
        batch_service = UploadBatchService(db)
        batch_id = batch_service.create_batch()

        # Инициализируем сервисы
        processing_service = StudyProcessingService(db)
        pathology_service = PathologyDetectionService(db)

        processed_count = 0
        failed_count = 0
        skipped_count = 0
        skipped_files = []

        # TODO добавить проверку что ml-service доступен

        # Обрабатываем каждый файл
        for file in files:
            try:
                # Проверяем, не загружалось ли уже это исследование
                study_service = StudyService(db)
                if file.filename:
                    existing_study = study_service.get_study_by_path(file.filename)
                    if existing_study:
                        skipped_count += 1
                        skipped_files.append(file.filename)
                        logger.info(f"Исследование {file.filename} уже загружено ранее, пропускаем")
                        continue

                # Читаем содержимое файла
                content = await file.read()
                file_size = len(content)

                # Проверяем размер файла
                if file_size > settings.max_file_size:
                    logger.warning(
                        f"Файл {file.filename} слишком большой ({file_size} bytes), пропускаем"
                    )
                    failed_count += 1
                    continue

                # Создаем уникальное имя файла только если нужно сохранять ZIP
                if file.filename:
                    file_extension = os.path.splitext(file.filename)[1]
                    unique_filename = f"{uuid.uuid4()}{file_extension}"
                else:
                    unique_filename = f"{uuid.uuid4()}.zip"
                file_path = os.path.join(settings.upload_dir, unique_filename)

                # Сохраняем файл только если включен флаг save_zip_files
                if settings.save_zip_files:
                    os.makedirs(os.path.dirname(file_path), exist_ok=True)
                    async with aiofiles.open(file_path, "wb") as buffer:
                        await buffer.write(content)
                    logger.info(f"Файл {file.filename} сохранен в {file_path}")
                else:
                    logger.info(f"Файл {file.filename} не сохраняется (save_zip_files=False)")
                    file_path = None

                # Обрабатываем исследование
                try:
                    if settings.save_zip_files:
                        success, message, study_id = processing_service.process_study(
                            file.filename or "unknown.zip", file_path, batch_id
                        )
                    else:
                        success, message, study_id = processing_service.process_study(
                            file.filename or "unknown.zip", None, batch_id, content
                        )
                except Exception as processing_error:
                    logger.error(
                        f"Ошибка при обработке исследования {file.filename}: "
                        f"{str(processing_error)}"
                    )
                    db.rollback()
                    failed_count += 1
                    continue

                if success and study_id:
                    try:
                        # Ищем патологии
                        await pathology_service.detect_pathologies_in_study(study_id)

                        # Завершаем обработку с успехом
                        study_service.complete_processing(study_id, success=True)
                        processed_count += 1
                        logger.info(f"Исследование {file.filename} успешно обработано")
                    except Exception as pathology_error:
                        # Завершаем обработку с ошибкой
                        study_service.complete_processing(
                            study_id, success=False, error_message=str(pathology_error)
                        )
                        failed_count += 1
                        logger.error(
                            f"Ошибка ML анализа для {file.filename}: {str(pathology_error)}"
                        )
                else:
                    # Если обработка не удалась, завершаем с ошибкой
                    if study_id:
                        study_service.complete_processing(
                            study_id, success=False, error_message=message
                        )
                    failed_count += 1
                    logger.error(f"Ошибка при обработке {file.filename}: {message}")

            except Exception as e:
                logger.error(f"Ошибка при обработке файла {file.filename}: {str(e)}")
                failed_count += 1
                continue

        # Обновляем статистику батча
        batch_service.update_batch_stats(batch_id, len(files), processed_count, failed_count)

        # Формируем сообщение с учетом пропущенных файлов
        message_parts = []
        if processed_count > 0:
            message_parts.append(f"Обработано: {processed_count}")
        if skipped_count > 0:
            message_parts.append(f"Пропущено (уже загружены): {skipped_count}")
        if failed_count > 0:
            message_parts.append(f"Ошибок: {failed_count}")

        message = f"Всего исследований: {len(files)}. " + ", ".join(message_parts)

        if skipped_files:
            message += f"\nПропущенные исследования: {', '.join(skipped_files)}"

        # Добавляем информацию об ошибках
        if failed_count > 0:
            message += "\n\n⚠️ Внимание: Некоторые исследования не удалось проанализировать."

        # Определяем статус обработки
        if failed_count == 0:
            processing_status = "Completed"
        elif processed_count > 0:
            processing_status = "Partial"
        else:
            processing_status = "Failed"

        # Завершаем отслеживание активной загрузки
        active_analysis_service.complete_upload()

        return UploadResponse(
            message=message,
            batch_id=batch_id,
            total_files=len(files),
            processed_files=processed_count,
            failed_files=failed_count,
            processing_status=processing_status,
        )

    except HTTPException:
        # Завершаем отслеживание при ошибке
        active_analysis_service.complete_upload()
        raise
    except Exception as e:
        # Завершаем отслеживание при ошибке
        active_analysis_service.complete_upload()
        logger.error(f"Ошибка при загрузке файлов: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ошибка при обработке файлов: {str(e)}") from e


@router.get("/batches", response_model=List[UploadBatchListResponse])
async def get_upload_batches(
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """Получить список батчей загрузки"""
    batch_service = UploadBatchService(db)
    batches = batch_service.get_batches(limit=limit, offset=offset)
    return batches


@router.get("/batches/{batch_id}/studies", response_model=List[StudyResponse])
async def get_batch_studies(
    batch_id: int,
    db: Session = Depends(get_db),
):
    """Получить исследования конкретного батча"""
    batch_service = UploadBatchService(db)
    studies = batch_service.get_batch_studies(batch_id)
    return studies


@router.get("/batches/{batch_id}/status", response_model=BatchStatusResponse)
async def get_batch_status(
    batch_id: int,
    db: Session = Depends(get_db),
):
    """
    Получить статус обработки батча с детальной информацией о задачах

    Args:
        batch_id: ID батча
        db: Сессия базы данных

    Returns:
        BatchStatusResponse: Статус батча с задачами
    """
    try:
        # Проверяем существование батча
        batch_service = UploadBatchService(db)
        batch = batch_service.get_batch(batch_id)

        if not batch:
            raise HTTPException(status_code=404, detail="Батч не найден")

        # Получаем статистику и задачи
        task_service = TaskService(db)
        statistics = task_service.get_batch_statistics(batch_id)
        tasks = task_service.get_batch_tasks(batch_id)

        # Проверяем, завершена ли обработка батча
        if statistics["progress_percentage"] >= 100 and batch.processing_end_time is None:
            batch_service.set_processing_end(batch_id)
            db.refresh(batch)

        # Формируем ответ
        return BatchStatusResponse(
            batch_id=batch_id,
            total_tasks=statistics["total_tasks"],
            pending_tasks=statistics["pending_tasks"],
            started_tasks=statistics["started_tasks"],
            success_tasks=statistics["success_tasks"],
            failed_tasks=statistics["failed_tasks"],
            progress_percentage=statistics["progress_percentage"],
            tasks=[
                TaskStatusResponse(
                    task_id=str(task.task_id),
                    filename=str(task.filename),
                    status=str(task.status),
                    study_id=int(task.study_id) if task.study_id is not None else None,  # type: ignore  # noqa: E501
                    error_message=str(task.error_message)
                    if task.error_message is not None
                    else None,  # noqa: E501
                    created_at=task.created_at,  # type: ignore
                    started_at=task.started_at,  # type: ignore
                    completed_at=task.completed_at,  # type: ignore
                )
                for task in tasks
            ],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при получении статуса батча {batch_id}: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Ошибка при получении статуса: {str(e)}"
        ) from e


@router.post("/batches/{batch_id}/cancel")
async def cancel_batch(
    batch_id: int,
    db: Session = Depends(get_db),
):
    """
    Отменить обработку батча

    Args:
        batch_id: ID батча
        db: Сессия базы данных

    Returns:
        Dict: Сообщение о результате отмены
    """
    try:
        from app.core.celery_app import celery_app

        # Проверяем существование батча
        batch_service = UploadBatchService(db)
        batch = batch_service.get_batch(batch_id)

        if not batch:
            raise HTTPException(status_code=404, detail="Батч не найден")

        # Получаем все задачи батча
        task_service = TaskService(db)
        tasks = task_service.get_batch_tasks(batch_id)

        # Отменяем задачи Celery
        cancelled_count = 0
        for task in tasks:
            if task.status in ["PENDING", "STARTED"]:
                try:
                    celery_app.control.revoke(str(task.task_id), terminate=True, signal="SIGKILL")
                    task_service.update_task_status(
                        task_id=str(task.task_id),
                        status="FAILURE",
                        error_message="Отменено пользователем",
                    )
                    cancelled_count += 1
                except Exception as e:
                    logger.error(f"Ошибка при отмене задачи {task.task_id}: {str(e)}")

        # Помечаем батч как отмененный
        batch_service.cancel_batch(batch_id)

        return {
            "message": f"Батч #{batch_id} отменен. Отменено задач: {cancelled_count}",
            "cancelled_tasks": cancelled_count,
            "total_tasks": len(tasks),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при отмене батча {batch_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ошибка при отмене батча: {str(e)}") from e


@router.get("/tasks/{task_id}/status", response_model=TaskStatusResponse)
async def get_task_status(
    task_id: str,
    db: Session = Depends(get_db),
):
    """
    Получить статус конкретной задачи

    Args:
        task_id: ID задачи Celery
        db: Сессия базы данных

    Returns:
        TaskStatusResponse: Статус задачи
    """
    try:
        task_service = TaskService(db)
        task = task_service.get_task_status(task_id)

        if not task:
            raise HTTPException(status_code=404, detail="Задача не найдена")

        return TaskStatusResponse(
            task_id=str(task.task_id),
            filename=str(task.filename),
            status=str(task.status),
            study_id=int(task.study_id) if task.study_id is not None else None,  # type: ignore
            error_message=str(task.error_message) if task.error_message is not None else None,
            created_at=task.created_at,  # type: ignore
            started_at=task.started_at,  # type: ignore
            completed_at=task.completed_at,  # type: ignore
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при получении статуса задачи {task_id}: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Ошибка при получении статуса задачи: {str(e)}"
        ) from e


@router.get("/batches/{batch_id}/report")
async def download_batch_report(
    batch_id: int,
    db: Session = Depends(get_db),
):
    """Скачать итоговый отчет по батчу"""
    try:
        batch_service = UploadBatchService(db)
        batch = batch_service.get_batch(batch_id)

        if not batch:
            raise HTTPException(status_code=404, detail="Батч не найден")

        # Создаем отчет
        report_service = ReportService(db)
        report_path = await report_service.generate_batch_report(batch_id)

        if not report_path:
            raise HTTPException(status_code=500, detail="Ошибка при создании отчета")

        # Возвращаем файл
        return FileResponse(
            path=report_path,
            filename=f"report_{batch.upload_date.strftime('%Y%m%d_%H%M%S')}.xlsx",
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при создании отчета: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ошибка при создании отчета: {str(e)}") from e


# Остальные роутеры остаются без изменений
@router.get("/", response_model=StudyListResponse)
async def get_studies(
    page: int = 1,
    size: int = 20,
    status: Optional[str] = None,
    pathology: Optional[str] = None,
    search: Optional[str] = None,
    batch_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """
    Получить список исследований с фильтрацией и пагинацией

    Поддерживает фильтрацию по статусу, наличию патологий, поиску и батчу.

    Args:
        page: Номер страницы (начиная с 1)
        size: Размер страницы (1-100)
        status: Фильтр по статусу обработки
        pathology: Фильтр по наличию патологий (true/false)
        search: Поиск по названию файла
        batch_id: Фильтр по ID батча
        db: Сессия базы данных

    Returns:
        StudyListResponse: Список исследований с метаданными пагинации

    Raises:
        HTTPException: Ошибки валидации параметров
    """
    # Валидация параметров
    if page < 1:
        raise HTTPException(status_code=400, detail="Номер страницы должен быть >= 1")

    if size < 1 or size > 100:
        raise HTTPException(status_code=400, detail="Размер страницы должен быть от 1 до 100")

    # Валидация статуса
    if status is not None:
        allowed_statuses = {"Pending", "Processing", "Success", "Failure"}
        if status not in allowed_statuses:
            raise HTTPException(
                status_code=400,
                detail=f"Статус должен быть одним из: {', '.join(allowed_statuses)}",
            )

    # Валидация pathology
    if pathology is not None:
        if pathology.lower() not in {"true", "false"}:
            raise HTTPException(
                status_code=400, detail="Параметр pathology должен быть 'true' или 'false'"
            )

    study_service = StudyService(db)

    # Преобразуем pathology из строки в boolean
    pathology_bool = None
    if pathology is not None:
        pathology_bool = pathology.lower() == "true"

    # Вычисляем skip и limit для пагинации
    skip = (page - 1) * size
    limit = size

    try:
        studies, total = study_service.get_studies(
            skip=skip,
            limit=limit,
            status=status,
            pathology=pathology_bool,
            search=search,
            batch_id=batch_id,
        )

        # Преобразуем Study в StudyResponse
        study_responses = [StudyResponse.model_validate(study) for study in studies]

        return StudyListResponse(studies=study_responses, total=total, page=page, size=size)
    except Exception as e:
        logger.error(f"Ошибка при получении списка исследований: {e}")
        raise HTTPException(
            status_code=500, detail="Ошибка при получении списка исследований"
        ) from e


@router.get("/{study_id}", response_model=StudyResponse)
async def get_study(
    study_id: int,
    db: Session = Depends(get_db),
):
    """
    Получить детальную информацию об исследовании

    Args:
        study_id: ID исследования
        db: Сессия базы данных

    Returns:
        StudyResponse: Детальная информация об исследовании

    Raises:
        HTTPException: Исследование не найдено
    """
    if study_id < 1:
        raise HTTPException(
            status_code=400, detail="ID исследования должен быть положительным числом"
        )

    study_service = StudyService(db)
    study = study_service.get_study_with_series(study_id)

    if not study:
        raise HTTPException(status_code=404, detail="Исследование не найдено")

    return StudyResponse.model_validate(study)


@router.put("/{study_id}", response_model=StudyResponse)
async def update_study(
    study_id: int,
    study_update: StudyUpdate,
    db: Session = Depends(get_db),
):
    """
    Обновить информацию об исследовании

    Args:
        study_id: ID исследования
        study_update: Данные для обновления
        db: Сессия базы данных

    Returns:
        StudyResponse: Обновленное исследование

    Raises:
        HTTPException: Исследование не найдено или ошибка валидации
    """
    if study_id < 1:
        raise HTTPException(
            status_code=400, detail="ID исследования должен быть положительным числом"
        )

    study_service = StudyService(db)

    try:
        study = study_service.update_study(study_id, study_update)
        if not study:
            raise HTTPException(status_code=404, detail="Исследование не найдено")

        return StudyResponse.model_validate(study)
    except Exception as e:
        logger.error(f"Ошибка при обновлении исследования {study_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при обновлении исследования") from e


@router.delete("/{study_id}")
async def delete_study(
    study_id: int,
    db: Session = Depends(get_db),
):
    """
    Удалить исследование (мягкое удаление)

    Args:
        study_id: ID исследования
        db: Сессия базы данных

    Returns:
        Dict[str, str]: Сообщение об успешном удалении

    Raises:
        HTTPException: Исследование не найдено
    """
    if study_id < 1:
        raise HTTPException(
            status_code=400, detail="ID исследования должен быть положительным числом"
        )

    study_service = StudyService(db)

    try:
        success = study_service.delete_study(study_id)
        if not success:
            raise HTTPException(status_code=404, detail="Исследование не найдено")

        return {"message": "Исследование успешно удалено"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при удалении исследования {study_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при удалении исследования") from e


@router.get("/{study_id}/download/pathology-images")
async def download_pathology_images(
    study_id: int,
    db: Session = Depends(get_db),
):
    """Скачать ZIP архив с изображениями патологий"""
    try:
        # Проверяем, не удалены ли файлы
        study = db.query(Study).filter(Study.id == study_id).first()
        if not study:
            raise HTTPException(status_code=404, detail="Исследование не найдено")

        if study.is_files_deleted:  # type: ignore
            raise HTTPException(
                status_code=410, detail="Файлы исследования удалены. Скачивание невозможно."
            )

        pathology_service = PathologyDetectionService(db)
        zip_path = pathology_service.create_pathology_images_zip(study_id)

        if not zip_path:
            raise HTTPException(status_code=404, detail="Изображения патологий не найдены")

        # Проверяем существование файла
        if not os.path.exists(zip_path):
            logger.error(f"ZIP файл не найден: {zip_path}")
            raise HTTPException(status_code=404, detail="ZIP файл не найден")

        logger.info(f"Отправляем ZIP файл: {zip_path}")

        # Создаем StreamingResponse с автоматическим удалением файла
        def cleanup_temp_file():
            try:
                if os.path.exists(zip_path):
                    os.remove(zip_path)
                    logger.info(f"Временный файл удален: {zip_path}")
            except Exception as e:
                logger.warning(f"Не удалось удалить временный файл {zip_path}: {str(e)}")

        # Читаем файл и отправляем с удалением
        def generate():
            try:
                with open(zip_path, "rb") as f:
                    while chunk := f.read(8192):
                        yield chunk
            finally:
                cleanup_temp_file()

        return StreamingResponse(
            generate(),
            media_type="application/zip",
            headers={
                "Content-Disposition": f"attachment; filename=pathology_images_{study_id}.zip"
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при создании архива: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ошибка при создании архива: {str(e)}") from e


@router.get("/{study_id}/download/pathology-dicom")
async def download_pathology_dicom(
    study_id: int,
    db: Session = Depends(get_db),
):
    """Скачать ZIP архив с DICOM файлами патологий"""
    try:
        # Проверяем, не удалены ли файлы
        study = db.query(Study).filter(Study.id == study_id).first()
        if not study:
            raise HTTPException(status_code=404, detail="Исследование не найдено")

        if study.is_files_deleted:  # type: ignore
            raise HTTPException(
                status_code=410, detail="Файлы исследования удалены. Скачивание невозможно."
            )

        pathology_service = PathologyDetectionService(db)

        # Сначала создаем список DICOM файлов по запросу
        if not pathology_service.create_pathology_dicom_files(study_id):
            raise HTTPException(status_code=500, detail="Ошибка при создании списка DICOM файлов")

        # Затем создаем ZIP архив
        zip_path = pathology_service.create_pathology_dicom_zip(study_id)

        if not zip_path:
            raise HTTPException(status_code=404, detail="DICOM файлы патологий не найдены")

        # Проверяем существование файла
        if not os.path.exists(zip_path):
            logger.error(f"ZIP файл не найден: {zip_path}")
            raise HTTPException(status_code=404, detail="ZIP файл не найден")

        logger.info(f"Отправляем ZIP файл: {zip_path}")

        # Создаем StreamingResponse с автоматическим удалением файла
        def cleanup_temp_file():
            try:
                if os.path.exists(zip_path):
                    os.remove(zip_path)
                    logger.info(f"Временный файл удален: {zip_path}")
            except Exception as e:
                logger.warning(f"Не удалось удалить временный файл {zip_path}: {str(e)}")

        # Читаем файл и отправляем с удалением
        def generate():
            try:
                with open(zip_path, "rb") as f:
                    while chunk := f.read(8192):
                        yield chunk
            finally:
                cleanup_temp_file()

        return StreamingResponse(
            generate(),
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename=pathology_dicom_{study_id}.zip"},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при создании архива: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ошибка при создании архива: {str(e)}") from e
