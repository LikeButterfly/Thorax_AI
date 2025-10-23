"""
Celery задачи для обработки исследований
"""

import asyncio
import logging
import os

from celery import Task

from app.core.celery_app import celery_app
from app.core.config import settings
from app.db.database import SessionLocal
from app.services.pathology_detection_service import PathologyDetectionService
from app.services.study_processing_service import StudyProcessingService
from app.services.study_service import StudyService
from app.services.task_service import TaskService

logger = logging.getLogger(__name__)


class DatabaseTask(Task):
    """Базовый класс задачи с подключением к БД и обновлением статуса"""

    _db = None

    def before_start(self, task_id, args, kwargs):
        """Обновляем статус при начале выполнения"""
        try:
            db = SessionLocal()
            task_service = TaskService(db)
            task_service.update_task_status(task_id, "STARTED")
            db.close()
        except Exception as e:
            logger.warning(f"Не удалось обновить статус задачи {task_id} на STARTED: {str(e)}")

    def on_success(self, retval, task_id, args, kwargs):
        """Обновляем статус при успешном выполнении"""
        try:
            db = SessionLocal()
            task_service = TaskService(db)
            task_service.update_task_status(
                task_id,
                "SUCCESS",
                result=retval,
                study_id=retval.get("study_id") if isinstance(retval, dict) else None,
            )
            db.close()
            logger.info(f"Задача {task_id} успешно завершена")
        except Exception as e:
            logger.error(f"Ошибка обновления статуса задачи {task_id} на SUCCESS: {str(e)}")

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Обновляем статус при ошибке"""
        try:
            db = SessionLocal()
            task_service = TaskService(db)
            task_service.update_task_status(task_id, "FAILURE", error_message=str(exc))
            db.close()
            logger.error(f"Задача {task_id} завершена с ошибкой: {str(exc)}")
        except Exception as e:
            logger.error(f"Ошибка обновления статуса задачи {task_id} на FAILURE: {str(e)}")

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """Обновляем статус при повторной попытке"""
        try:
            db = SessionLocal()
            task_service = TaskService(db)
            task_service.update_task_status(task_id, "RETRY", error_message=str(exc))
            db.close()
            logger.warning(f"Задача {task_id} повторяется: {str(exc)}")
        except Exception as e:
            logger.error(f"Ошибка обновления статуса задачи {task_id} на RETRY: {str(e)}")

    def after_return(self, *args, **kwargs):
        """Закрываем сессию БД после выполнения задачи"""
        if self._db is not None:
            self._db.close()


@celery_app.task(
    bind=True,
    base=DatabaseTask,
    name="app.tasks.study_tasks.process_single_study_task",
    max_retries=3,
    default_retry_delay=60,
)
def process_single_study_task(
    self,
    filename: str,
    file_content_base64: str,
    batch_id: int,
    save_zip: bool = False,
) -> dict:
    """
    Celery задача для обработки одного исследования

    Args:
        self: Celery task instance
        filename: Имя ZIP файла
        file_content_base64: Содержимое файла в base64
        batch_id: ID батча загрузки
        save_zip: Сохранять ли ZIP файл

    Returns:
        Dict с результатом обработки
    """
    try:
        logger.info(f"Начинаем обработку исследования: {filename} (задача: {self.request.id})")

        # Создаем сессию БД
        db = SessionLocal()
        self._db = db

        # Декодируем содержимое файла из base64
        import base64

        file_content = base64.b64decode(file_content_base64)
        file_size = len(file_content)

        logger.info(f"Файл {filename} размером {file_size} байт декодирован")

        # Проверяем размер файла
        if file_size > settings.max_file_size:
            error_msg = f"Файл {filename} слишком большой ({file_size} bytes)"
            logger.warning(error_msg)
            return {
                "success": False,
                "filename": filename,
                "error": error_msg,
                "study_id": None,
            }

        # Определяем путь для сохранения (если нужно)
        zip_path = None
        if save_zip and settings.save_zip_files:
            import uuid

            file_extension = os.path.splitext(filename)[1]
            unique_filename = f"{uuid.uuid4()}{file_extension}"
            zip_path = os.path.join(settings.upload_dir, unique_filename)

            # Сохраняем файл
            os.makedirs(os.path.dirname(zip_path), exist_ok=True)
            with open(zip_path, "wb") as f:
                f.write(file_content)
            logger.info(f"Файл {filename} сохранен в {zip_path}")

        # Инициализируем сервисы
        processing_service = StudyProcessingService(db)

        # Обрабатываем исследование
        try:
            success, message, study_id = processing_service.process_study(
                filename=filename,
                zip_path=zip_path,
                batch_id=batch_id,
                zip_content=file_content if not zip_path else None,
            )

            if not success or not study_id:
                logger.error(f"Ошибка обработки {filename}: {message}")
                return {
                    "success": False,
                    "filename": filename,
                    "error": message,
                    "study_id": study_id,
                }

            logger.info(f"Исследование {filename} обработано успешно, study_id={study_id}")

            # Запускаем ML анализ асинхронно
            pathology_service = PathologyDetectionService(db)
            study_service = StudyService(db)

            try:
                # Используем asyncio для запуска async функции
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                has_pathology = loop.run_until_complete(
                    pathology_service.detect_pathologies_in_study(study_id)
                )
                loop.close()

                # Завершаем обработку с успехом
                study_service.complete_processing(study_id, success=True)

                logger.info(
                    f"ML анализ для {filename} завершен. "
                    f"Патологии: {has_pathology}, study_id={study_id}"
                )

                return {
                    "success": True,
                    "filename": filename,
                    "study_id": study_id,
                    "has_pathology": has_pathology,
                }

            except Exception as pathology_error:
                # Завершаем обработку с ошибкой
                error_msg = str(pathology_error)
                study_service.complete_processing(study_id, success=False, error_message=error_msg)
                logger.error(f"Ошибка ML анализа для {filename}: {error_msg}")

                return {
                    "success": False,
                    "filename": filename,
                    "error": f"ML анализ не удался: {error_msg}",
                    "study_id": study_id,
                }

        except Exception as processing_error:
            logger.error(f"Ошибка при обработке исследования {filename}: {str(processing_error)}")
            db.rollback()
            return {
                "success": False,
                "filename": filename,
                "error": str(processing_error),
                "study_id": None,
            }

    except Exception as e:
        logger.error(f"Критическая ошибка при обработке файла {filename}: {str(e)}")
        # Повторяем задачу при критической ошибке
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e) from e
        return {
            "success": False,
            "filename": filename,
            "error": f"Критическая ошибка: {str(e)}",
            "study_id": None,
        }
    finally:
        # Закрываем сессию
        if db:
            db.close()
