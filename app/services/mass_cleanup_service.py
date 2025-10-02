"""
Сервис для массового удаления файлов исследований
"""

import json
import logging
import shutil
from pathlib import Path
from typing import List, Tuple

from sqlalchemy.orm import Session

from app.models.study import Series, Study
from app.services.active_analysis_service import ActiveAnalysisService

logger = logging.getLogger(__name__)


class MassCleanupService:
    """Сервис для массового удаления файлов исследований"""

    def __init__(self, db: Session):
        self.db = db
        self.active_analysis_service = ActiveAnalysisService(db)

    def can_cleanup_files(self) -> Tuple[bool, str]:
        """
        Проверяет, можно ли удалять файлы (нет активных анализов)

        Returns:
            Tuple[bool, str]: (можно удалять, сообщение)
        """
        try:
            if self.active_analysis_service.has_active_analyses():
                return False, "Нельзя удалять файлы во время активных анализов"

            return True, "Можно безопасно удалять файлы"

        except Exception as e:
            logger.error(f"Ошибка при проверке возможности удаления файлов: {str(e)}")
            return False, f"Ошибка при проверке активных анализов: {str(e)}"

    def get_cleanup_statistics(self) -> dict:
        """
        Получает простую статистику файлов для удаления

        Returns:
            dict: Статистика файлов
        """
        try:
            # Получаем количество исследований с файлами
            studies_with_files = (
                self.db.query(Study)
                .filter(~Study.is_files_deleted)  # type: ignore
                .filter(Study.is_active)  # type: ignore
                .count()
            )

            return {"total_studies": studies_with_files}

        except Exception as e:
            logger.error(f"Ошибка при получении статистики файлов: {str(e)}")
            return {"total_studies": 0}

    def cleanup_all_files(self) -> Tuple[bool, str, dict]:
        """
        Удаляет все файлы всех исследований

        Returns:
            Tuple[bool, str, dict]: (успех, сообщение, статистика)
        """
        try:
            # Проверяем, можно ли удалять файлы
            can_cleanup, message = self.can_cleanup_files()
            if not can_cleanup:
                return False, message, {}

            # Получаем статистику до удаления
            stats_before = self.get_cleanup_statistics()

            if stats_before["total_studies"] == 0:
                return True, "Нет файлов для удаления", stats_before

            deleted_paths = []
            errors = []
            studies_processed = 0

            # Получаем все исследования с файлами
            studies_with_files = (
                self.db.query(Study)
                .filter(~Study.is_files_deleted)  # type: ignore
                .filter(Study.is_active)  # type: ignore
                .all()
            )

            for study in studies_with_files:
                try:
                    # Удаляем ZIP файл
                    if study.zip_path and Path(study.zip_path).exists():  # type: ignore
                        Path(study.zip_path).unlink()  # type: ignore
                        deleted_paths.append(f"ZIP: {study.zip_path}")  # type: ignore
                        logger.info(f"Удален ZIP файл: {study.zip_path}")  # type: ignore

                    # Получаем серии исследования
                    series_list = (
                        self.db.query(Series)
                        .filter(Series.study_id == study.id)
                        .filter(Series.is_active)  # type: ignore
                        .all()
                    )

                    for series in series_list:
                        # Удаляем папку с изображениями
                        if series.images_dir and Path(series.images_dir).exists():  # type: ignore
                            shutil.rmtree(series.images_dir)  # type: ignore
                            deleted_paths.append(f"Images: {series.images_dir}")  # type: ignore
                            logger.info(f"Удалена папка изображений: {series.images_dir}")  # type: ignore

                        # Удаляем папку с DICOM файлами
                        if series.dicom_dir and Path(series.dicom_dir).exists():  # type: ignore
                            shutil.rmtree(series.dicom_dir)  # type: ignore
                            deleted_paths.append(f"DICOM: {series.dicom_dir}")  # type: ignore
                            logger.info(f"Удалена папка DICOM: {series.dicom_dir}")  # type: ignore

                    # Удаляем папку исследования целиком
                    study_dir = Path("uploads/studies") / str(study.internal_id)  # type: ignore
                    if study_dir.exists():
                        shutil.rmtree(study_dir)
                        deleted_paths.append(f"Study dir: {study_dir}")
                        logger.info(f"Удалена папка исследования: {study_dir}")

                    # Обновляем флаг в базе
                    study.is_files_deleted = True  # type: ignore
                    studies_processed += 1

                except Exception as e:
                    error_msg = f"Ошибка при удалении файлов исследования {study.id}: {str(e)}"
                    errors.append(error_msg)
                    logger.error(error_msg)

            # Сохраняем изменения в базе
            self.db.commit()

            # Формируем статистику
            stats_after = self.get_cleanup_statistics()

            if errors:
                message = (
                    f"Удалено {len(deleted_paths)} объектов из {studies_processed} исследований, "
                    f"ошибок: {len(errors)}. Ошибки: {'; '.join(errors[:5])}"
                )
                logger.warning(f"Частичное удаление файлов: {message}")
                return (
                    True,
                    message,
                    {
                        "studies_processed": studies_processed,
                        "objects_deleted": len(deleted_paths),
                        "errors_count": len(errors),
                        "errors": errors[:10],  # Первые 10 ошибок
                        "stats_before": stats_before,
                        "stats_after": stats_after,
                    },
                )
            else:
                message = (
                    f"Успешно удалено {len(deleted_paths)} объектов из "
                    f"{studies_processed} исследований"
                )
                logger.info(f"Полное удаление файлов: {message}")
                return (
                    True,
                    message,
                    {
                        "studies_processed": studies_processed,
                        "objects_deleted": len(deleted_paths),
                        "errors_count": 0,
                        "stats_before": stats_before,
                        "stats_after": stats_after,
                    },
                )

        except Exception as e:
            self.db.rollback()
            error_msg = f"Критическая ошибка при массовом удалении файлов: {str(e)}"
            logger.error(error_msg)
            return False, error_msg, {}
