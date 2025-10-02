"""
Сервис для обработки исследований с поддержкой множественных серий
"""

import io
import logging
import os
import shutil
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from zipfile import ZipFile

import pydicom
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.study import Series, Study
from app.services.dicom_service import DicomService
from app.services.mapping_service import MappingService

logger = logging.getLogger(__name__)


class StudyProcessingService:
    """Сервис для обработки исследований с поддержкой множественных серий"""

    def __init__(self, db: Session):
        self.db = db
        self.dicom_service = DicomService(settings.upload_dir)
        self.mapping_service = MappingService(db)

    def process_study(
        self,
        filename: str,
        zip_path: Optional[str],
        batch_id: Optional[int] = None,
        zip_content: Optional[bytes] = None,
    ) -> Tuple[bool, str, Optional[int]]:
        """
        Обрабатывает ZIP архив с исследованием

        Args:
            zip_path: Путь к ZIP файлу (может быть None если save_zip_files=False)
            filename: Имя ZIP файла
            batch_id: ID батча загрузки
            zip_content: Содержимое ZIP файла в памяти (если zip_path=None)

        Returns:
            Tuple[bool, str, Optional[int]]: (успех, сообщение, study_id)
        """
        try:
            # Создаем уникальный ID для исследования
            study_id = str(uuid.uuid4())
            study_dir = Path(settings.upload_dir) / "studies" / study_id

            # Создаем директории
            study_dir.mkdir(parents=True, exist_ok=True)

            # Распаковываем ZIP
            extract_dir = study_dir / "extracted"
            extract_dir.mkdir(exist_ok=True)

            if zip_path and os.path.exists(zip_path):
                # Используем сохраненный файл
                with ZipFile(zip_path, "r") as zip_ref:
                    zip_ref.extractall(extract_dir)
            elif zip_content:
                # Используем содержимое из памяти
                with ZipFile(io.BytesIO(zip_content), "r") as zip_ref:
                    zip_ref.extractall(extract_dir)
            else:
                raise ValueError("Не предоставлен ни путь к файлу, ни содержимое ZIP")

            logger.info(f"ZIP файл {filename} распакован в {extract_dir}")

            # Создаем запись об исследовании в БД с внутренним ID
            study = self.mapping_service.create_study(
                path_to_study=filename,
                zip_path=zip_path if settings.save_zip_files else None,
                batch_id=batch_id,
            )

            # Находим все DICOM файлы и группируем по сериям
            series_data, file_stats = self._find_and_group_dicom_files(extract_dir)

            # Сохраняем статистику в исследование
            study.total_files_found = file_stats["total_files"]  # type: ignore
            study.dicom_files_found = file_stats["dicom_files"]  # type: ignore
            study.valid_ct_files = file_stats["valid_files"]  # type: ignore

            if not series_data:
                study.processing_status = "Failure"  # type: ignore
                study.error_message = (  # type: ignore
                    f"Найдено {file_stats['dicom_files']} DICOM файлов, "
                    "но ни один не соответствует критериям CT грудной клетки"
                )
                self.db.commit()
                return False, study.error_message, study.id  # type: ignore

            # Создаем маппинг к DICOM StudyInstanceUID
            study_uid = self._get_study_uid_from_series(series_data)
            self.mapping_service.map_study_to_dicom_uid(study.id, study_uid)  # type: ignore

            # Собираем статистику для определения оптимальной серии
            # {folder_path: {'dicom_count': int, 'series_count': int, 'series_uid_set': set}}
            folder_stats = {}

            # Начинаем отсчет общего времени обработки исследования
            study_start_time = time.time()

            # Собираем статистику по всем сериям для определения оптимальной
            for series_uid, dicom_files in series_data.items():
                for dicom_file in dicom_files:
                    dicom_path = Path(dicom_file)
                    try:
                        # Получаем относительный путь от extract_dir
                        rel_path = dicom_path.relative_to(extract_dir)
                        # Берем родительскую папку
                        parent_folder = rel_path.parent
                        folder_str = str(parent_folder)

                        # Инициализируем статистику для папки
                        if folder_str not in folder_stats:
                            folder_stats[folder_str] = {
                                "dicom_count": 0,
                                "series_count": 0,
                                "series_uid_set": set(),
                            }

                        # Обновляем статистику
                        folder_stats[folder_str]["dicom_count"] += 1
                        folder_stats[folder_str]["series_uid_set"].add(series_uid)

                    except ValueError:
                        # Если файл не находится в extract_dir, пропускаем
                        continue

            # Определяем оптимальную серию
            optimal_series_uid = None
            optimal_dicom_files = []

            if folder_stats:
                # Обновляем количество уникальных серий для каждой папки
                for _folder_path, stats in folder_stats.items():
                    stats["series_count"] = len(stats["series_uid_set"])

                # Находим оптимальную папку по приоритету:
                # 1. Максимальное количество серий
                # 2. Максимальное количество DICOM файлов
                max_series_count = 0
                max_dicom_count = 0
                optimal_folder = None

                for folder_path, stats in folder_stats.items():
                    series_count = stats["series_count"]
                    dicom_count = stats["dicom_count"]

                    # Приоритет папкам с большим количеством серий
                    if series_count > max_series_count:
                        max_series_count = series_count
                        max_dicom_count = dicom_count
                        optimal_folder = folder_path
                    elif series_count == max_series_count and dicom_count > max_dicom_count:
                        # Если количество серий одинаковое, выбираем с большим количеством файлов
                        max_dicom_count = dicom_count
                        optimal_folder = folder_path

                if optimal_folder:
                    # Находим серию с наибольшим количеством файлов в оптимальной папке
                    max_files_in_series = 0
                    for series_uid, dicom_files in series_data.items():
                        files_in_optimal_folder = 0
                        for dicom_file in dicom_files:
                            try:
                                rel_path = Path(dicom_file).relative_to(extract_dir)
                                if str(rel_path.parent) == optimal_folder:
                                    files_in_optimal_folder += 1
                            except ValueError:
                                continue

                        if files_in_optimal_folder > max_files_in_series:
                            max_files_in_series = files_in_optimal_folder
                            optimal_series_uid = series_uid
                            optimal_dicom_files = dicom_files

                    # Устанавливаем study_path
                    full_study_path = f"{filename}/{optimal_folder}"
                    study.study_path = full_study_path  # type: ignore
                    logger.info(f"Установлен оптимальный путь исследования: {full_study_path}")
                else:
                    # Fallback: берем первую серию
                    optimal_series_uid = list(series_data.keys())[0]
                    optimal_dicom_files = series_data[optimal_series_uid]
                    study.study_path = filename  # type: ignore
                    logger.warning(
                        "Не удалось определить оптимальную папку, используем первую серию"
                    )
            else:
                # Fallback: берем первую серию
                optimal_series_uid = list(series_data.keys())[0]
                optimal_dicom_files = series_data[optimal_series_uid]
                study.study_path = filename  # type: ignore
                logger.warning("Не удалось собрать статистику по папкам, используем первую серию")

            # Обрабатываем только оптимальную серию
            processed_series = 0
            total_processing_time = 0.0

            if optimal_series_uid and optimal_dicom_files:
                logger.info(
                    f"Обрабатываем оптимальную серию: {optimal_series_uid} с "
                    f"{len(optimal_dicom_files)} файлами"
                )

                # Создаем запись о серии с внутренним ID
                series = self.mapping_service.create_series(study.id)  # type: ignore

                # Создаем маппинг к DICOM SeriesInstanceUID
                self.mapping_service.map_series_to_dicom_uid(series.id, optimal_series_uid)  # type: ignore

                # Создаем директории только если нужно сохранять данные
                series_dir = None
                if settings.save_extracted_data:
                    series_dir = study_dir / "series" / series.internal_id
                    series_dir.mkdir(parents=True, exist_ok=True)
                    logger.info(f"Создана директория для DICOM файлов: {series_dir}")
                else:
                    logger.info("Директория для DICOM файлов не создается")

                # Обновляем серию
                series.dicom_dir = str(series_dir) if settings.save_extracted_data else None  # type: ignore
                series.dicom_count = len(optimal_dicom_files)  # type: ignore
                series.processing_status = "Processing"  # type: ignore

                # Устанавливаем флаг для одного DICOM файла
                study.is_single_dicom = len(optimal_dicom_files) == 1  # type: ignore

                try:
                    # Копируем DICOM файлы в директорию серии только если включен флаг
                    if settings.save_extracted_data and series_dir:  # type: ignore
                        for dicom_file in optimal_dicom_files:
                            shutil.copy2(dicom_file, str(series_dir))  # type: ignore
                        logger.info(f"DICOM файлы скопированы в {series_dir}")
                    else:
                        logger.info("DICOM файлы не сохраняются (save_extracted_data=False)")

                    # Извлекаем изображения
                    if settings.save_images:
                        images_dir = study_dir / "images" / series.internal_id
                        images_dir.mkdir(parents=True, exist_ok=True)
                        series.images_dir = str(images_dir)  # type: ignore

                        start_time = time.time()
                        success = self.dicom_service.extract_images_to_png(
                            optimal_dicom_files, str(images_dir)
                        )
                        processing_time = time.time() - start_time

                        if success:
                            series.processing_status = "Success"  # type: ignore
                            series.processing_time = processing_time  # type: ignore
                            total_processing_time += processing_time
                            processed_series += 1

                            logger.info(
                                f"Оптимальная серия {optimal_series_uid}: "
                                f"{len(optimal_dicom_files)} файлов, "
                                f"{processing_time:.2f}с"
                            )
                        else:
                            series.processing_status = "Failure"  # type: ignore
                            series.error_message = "Ошибка при извлечении изображений"  # type: ignore  # noqa: E501
                            logger.error(
                                f"Ошибка при обработке оптимальной серии {optimal_series_uid}"
                            )
                    else:
                        series.processing_status = "Success"  # type: ignore
                        processed_series += 1

                except Exception as e:
                    series.processing_status = "Failure"  # type: ignore
                    series.error_message = str(e)  # type: ignore
                    logger.error(
                        f"Ошибка при обработке оптимальной серии {optimal_series_uid}: {str(e)}"
                    )
            else:
                logger.error("Не удалось определить оптимальную серию для обработки")

            # Обновляем статус исследования
            study.processed_series_count = processed_series  # type: ignore
            study.skipped_series_count = 0  # type: ignore

            if processed_series > 0:
                study.processing_status = "Success"  # type: ignore

                # Рассчитываем общее время обработки исследования
                study_total_time = time.time() - study_start_time

                # Логируем детали времени
                logger.info(
                    f"Время обработки исследования {study.id}: "
                    f"общее {study_total_time:.2f}с, "
                    f"извлечение изображений {total_processing_time:.2f}с, "
                    f"серий {processed_series}"
                )

                study.processing_time = study_total_time  # type: ignore
                # Не перезаписываем патологии - они устанавливаются PathologyDetectionService

            else:
                study.processing_status = "Failure"  # type: ignore
                study.error_message = "Не найдено ни одной серии DICOM файлов"  # type: ignore

            self.db.commit()

            # Очищаем временную директорию extracted после успешной обработки
            self._cleanup_extracted_dir(study_dir)

            return True, f"Обработано {processed_series} серий", study.id  # type: ignore

        except Exception as e:
            logger.error(f"Ошибка при обработке исследования: {str(e)}")
            # Очищаем временную директорию даже при ошибке
            if "study_dir" in locals():
                self._cleanup_extracted_dir(study_dir)
            return False, f"Ошибка при обработке: {str(e)}", None

    def _find_and_group_dicom_files(
        self, extract_dir: Path
    ) -> Tuple[Dict[str, List[str]], Dict[str, int]]:
        """
        Находит и группирует DICOM файлы по сериям

        Args:
            extract_dir: Директория с распакованными файлами

        Returns:
            Tuple[Dict[str, List[str]], Dict[str, int]]: (серии, статистика)
        """
        series_data = {}
        total_files = 0
        dicom_files = 0
        valid_files = 0

        # Рекурсивно ищем все файлы
        for file_path in extract_dir.rglob("*"):
            if file_path.is_file():
                total_files += 1
                # Проверяем, является ли файл DICOM
                if self.dicom_service.is_dicom_file(str(file_path)):
                    dicom_files += 1
                    try:
                        # Читаем метаданные
                        ds = pydicom.dcmread(str(file_path))

                        # Логируем информацию о файле для отладки
                        modality = getattr(ds, "Modality", "Unknown")
                        body_part = getattr(ds, "BodyPartExamined", "Unknown")
                        logger.debug(
                            f"Файл {file_path.name}: Modality={modality}, BodyPart={body_part}"
                        )

                        # Проверяем валидность для грудной клетки
                        is_valid, error_msg = self.dicom_service.is_valid_chest_ct(str(file_path))
                        if not is_valid:
                            logger.debug(f"Файл {file_path} не подходит: {error_msg}")
                            continue

                        valid_files += 1

                        # Получаем UID серии
                        series_uid = getattr(ds, "SeriesInstanceUID", None)
                        if not series_uid:
                            logger.warning(f"Файл {file_path} не содержит SeriesInstanceUID")
                            continue

                        # Добавляем в соответствующую серию
                        if series_uid not in series_data:
                            series_data[series_uid] = []
                        series_data[series_uid].append(str(file_path))

                    except Exception as e:
                        logger.debug(f"Ошибка при чтении {file_path}: {str(e)}")
                        continue

        logger.info(
            f"Анализ файлов: всего {total_files}, DICOM {dicom_files}, валидных CT {valid_files}"
        )

        if dicom_files == 0:
            logger.warning("DICOM файлы не найдены в архиве")
        elif valid_files == 0:
            logger.warning(
                f"Найдено {dicom_files} DICOM файлов, "
                "но ни один не соответствует критериям CT грудной клетки"
            )
        else:
            logger.info(f"Найдено {len(series_data)} серий DICOM файлов")
            for series_uid, files in series_data.items():
                logger.info(f"Серия {series_uid}: {len(files)} файлов")

        file_stats = {
            "total_files": total_files,
            "dicom_files": dicom_files,
            "valid_files": valid_files,
        }

        return series_data, file_stats

    def _get_study_uid_from_series(self, series_data: Dict[str, List[str]]) -> str:
        """
        Получает StudyInstanceUID из первой серии

        Args:
            series_data: Данные о сериях

        Returns:
            str: StudyInstanceUID
        """
        for _series_uid, dicom_files in series_data.items():
            if dicom_files:
                try:
                    ds = pydicom.dcmread(dicom_files[0])
                    study_uid = getattr(ds, "StudyInstanceUID", None)
                    if study_uid:
                        return study_uid
                except Exception as e:
                    logger.warning(f"Ошибка при получении StudyInstanceUID: {str(e)}")
                    continue

        # Если не удалось получить из DICOM, генерируем уникальный
        return str(uuid.uuid4())

    def _cleanup_extracted_dir(self, study_dir: Path) -> None:
        """
        Удаляет временную директорию extracted после обработки

        Args:
            study_dir: Директория исследования
        """
        try:
            extracted_dir = study_dir / "extracted"
            if extracted_dir.exists():
                shutil.rmtree(extracted_dir)
                logger.info(f"Временная директория {extracted_dir} успешно удалена")
            else:
                logger.debug(f"Директория {extracted_dir} не существует, пропускаем удаление")
        except Exception as e:
            logger.warning(f"Не удалось удалить временную директорию {extracted_dir}: {str(e)}")
            # Не поднимаем исключение, так как это не критично для работы системы
