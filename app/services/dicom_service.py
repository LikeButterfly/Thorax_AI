"""
Сервис для работы с DICOM файлами
"""

import logging
import os
import tempfile
import warnings
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
import pydicom
from pydicom.errors import InvalidDicomError

# Отключаем предупреждения pydicom о некорректных UID и других проблемах
warnings.filterwarnings("ignore", category=UserWarning, module="pydicom")
warnings.filterwarnings("ignore", message=".*Invalid value for VR.*")
warnings.filterwarnings("ignore", message=".*Please see.*dicom.nema.org.*")

logger = logging.getLogger(__name__)


class DicomService:
    """Сервис для обработки DICOM файлов"""

    def __init__(self, upload_dir: str):
        self.upload_dir = Path(upload_dir)
        self.upload_dir.mkdir(exist_ok=True)

    async def extract_zip(
        self, zip_path: str, extract_to: str
    ) -> bool:  # FIXME не используется нигде?
        """
        Извлекает ZIP архив с DICOM файлами

        Args:
            zip_path: Путь к ZIP файлу
            extract_to: Путь для извлечения

        Returns:
            bool: True если успешно, False если ошибка
        """
        try:
            extract_path = Path(extract_to)
            extract_path.mkdir(parents=True, exist_ok=True)

            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(extract_path)

            logger.info(f"ZIP файл {zip_path} успешно извлечен в {extract_to}")
            return True

        except Exception as e:
            logger.error(f"Ошибка при извлечении ZIP файла {zip_path}: {str(e)}")
            return False

    def is_dicom_file(self, file_path: str) -> bool:
        """
        Проверяет, является ли файл DICOM файлом по содержимому

        Args:
            file_path: Путь к файлу

        Returns:
            bool: True если это DICOM файл
        """
        try:
            # Пытаемся прочитать файл как DICOM
            ds = pydicom.dcmread(file_path, force=True)

            # Проверяем наличие обязательных DICOM тегов
            required_tags = [
                "StudyInstanceUID",  # (0020,000D)
                "SeriesInstanceUID",  # (0020,000E)
                "SOPClassUID",  # (0008,0016)
            ]

            for tag in required_tags:
                if not hasattr(ds, tag):
                    return False

            return True

        except Exception as e:
            logger.debug(f"Файл {file_path} не является DICOM: {str(e)}")
            # TODO обработать
            return False

    def find_dicom_files(self, directory: str) -> List[str]:
        """
        Находит все DICOM файлы в директории (включая файлы без расширений)

        Args:
            directory: Путь к директории

        Returns:
            List[str]: Список путей к DICOM файлам
        """
        dicom_files = []
        directory_path = Path(directory)

        if not directory_path.exists():
            return dicom_files

        # Сначала ищем файлы с расширениями DICOM
        dicom_extensions = {".dcm", ".DCM", ".dicom", ".DICOM"}
        # FIXME такого не будет и можно убрать (но оставить коммент на всякий, на будущее)

        for file_path in directory_path.rglob("*"):
            if file_path.is_file():
                # Проверяем расширение или содержимое файла
                if file_path.suffix in dicom_extensions or self.is_dicom_file(str(file_path)):
                    dicom_files.append(str(file_path))

        logger.info(f"Найдено {len(dicom_files)} DICOM файлов в {directory}")
        return dicom_files

    def is_valid_chest_ct(self, dicom_path: str) -> Tuple[bool, str]:
        """
        Проверяет, является ли DICOM файл валидным КТ грудной клетки
        Поддерживает как обычные, так и multi-frame DICOM файлы

        Args:
            dicom_path: Путь к DICOM файлу

        Returns:
            Tuple[bool, str]: (валидный, сообщение об ошибке)
        """
        try:
            ds = pydicom.dcmread(dicom_path)

            # Проверяем Modality = 'CT'
            modality = getattr(ds, "Modality", "")
            if modality != "CT":
                return False, f"Modality: '{modality}', ожидается 'CT'"

            # Проверяем Body Part Examined (более гибкая проверка)
            body_part = getattr(ds, "BodyPartExamined", "").upper()
            if body_part and body_part not in ["CHEST", "THORAX", "LUNG"]:
                return False, f"Body Part Examined: '{body_part}', ожидается CHEST/THORAX/LUNG"

            # Для multi-frame DICOM файлов некоторые теги могут отсутствовать
            # Проверяем только если тег присутствует
            if hasattr(ds, "ImageOrientationPatient"):
                image_orientation = getattr(ds, "ImageOrientationPatient", [])
                # Более гибкая проверка ориентации
                if len(image_orientation) >= 6:
                    # Проверяем только первые 6 значений
                    orientation_check = image_orientation[:6]
                    # Допускаем небольшие отклонения
                    expected_orientation = [1, 0, 0, 0, 1, 0]
                    if not all(
                        abs(a - b) < 0.1
                        for a, b in zip(orientation_check, expected_orientation, strict=False)
                    ):
                        logger.debug(
                            f"Image Orientation (Patient): {image_orientation} "
                            "(не стандартная, но допустимая)"
                        )

            # Проверяем наличие пиксельных данных
            if not hasattr(ds, "pixel_array"):
                return False, "Отсутствуют пиксельные данные"

            # Проверяем, что можем прочитать пиксельные данные
            try:
                pixel_array = ds.pixel_array
                if pixel_array is None or pixel_array.size == 0:
                    return False, "Пустые пиксельные данные"
            except Exception as e:
                return False, f"Ошибка чтения пиксельных данных: {str(e)}"

            return True, "Валидный КТ грудной клетки"

        except Exception as e:
            return False, f"Ошибка при проверке файла: {str(e)}"

    def read_dicom_metadata(self, dicom_path: str) -> Optional[Dict]:
        """
        Читает метаданные из DICOM файла

        Args:
            dicom_path: Путь к DICOM файлу

        Returns:
            Dict: Словарь с метаданными или None при ошибке
        """
        try:
            ds = pydicom.dcmread(dicom_path)

            metadata = {
                "study_uid": getattr(ds, "StudyInstanceUID", ""),
                "series_uid": getattr(ds, "SeriesInstanceUID", ""),
                "patient_name": getattr(ds, "PatientName", ""),
                "patient_id": getattr(ds, "PatientID", ""),
                "study_date": getattr(ds, "StudyDate", ""),
                "study_time": getattr(ds, "StudyTime", ""),
                "modality": getattr(ds, "Modality", ""),
                "study_description": getattr(ds, "StudyDescription", ""),
                "series_description": getattr(ds, "SeriesDescription", ""),
                "rows": getattr(ds, "Rows", 0),
                "columns": getattr(ds, "Columns", 0),
                "slices": getattr(ds, "NumberOfFrames", 1),
            }

            return metadata

        except InvalidDicomError as e:
            logger.error(f"Неверный DICOM файл {dicom_path}: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Ошибка при чтении DICOM файла {dicom_path}: {str(e)}")
            return None

    def get_pixels_hu(self, ds) -> np.ndarray:
        """
        Конвертация PixelData в HU (Hounsfield Units)

        Args:
            ds: DICOM dataset

        Returns:
            np.ndarray: Изображение в HU
        """
        image = ds.pixel_array.astype(np.int16)

        # Убираем padding (если есть)
        if "PixelPaddingValue" in ds:
            image[image == int(ds.PixelPaddingValue)] = 0

        # Применяем slope и intercept
        intercept = ds.RescaleIntercept if "RescaleIntercept" in ds else 0
        slope = ds.RescaleSlope if "RescaleSlope" in ds else 1
        image = image * slope + intercept

        return image

    def apply_window(
        self,
        image: np.ndarray,
        window_level: float,
        window_width: float,
    ) -> np.ndarray:
        """
        Применение window level / width для визуализации

        Args:
            image: Изображение в HU
            window_level: Уровень окна
            window_width: Ширина окна

        Returns:
            np.ndarray: Обработанное изображение
        """
        min_window = window_level - window_width // 2
        max_window = window_level + window_width // 2
        windowed = np.clip(image, min_window, max_window)
        windowed = ((windowed - min_window) / (max_window - min_window)) * 255.0
        return windowed.astype(np.uint8)

    def extract_images_to_png(self, dicom_files: List[str], output_dir: str) -> bool:
        """
        Извлекает изображения из DICOM файлов в PNG формат.
        Поддерживает как обычные DICOM файлы, так и multi-frame DICOM файлы.
        Для каждого DICOM файла создает 3 PNG с разными режимами визуализации

        Args:
            dicom_files: Список путей к DICOM файлам
            output_dir: Директория для сохранения PNG файлов

        Returns:
            bool: True если успешно
        """
        try:
            os.makedirs(output_dir, exist_ok=True)

            # Параметры для трех режимов визуализации
            WINDOW_MODES = {
                "lung": {"level": -400.0, "width": 1500.0},  # легочный
                "bone": {"level": 300.0, "width": 1500.0},  # костный
                "soft": {"level": 55.0, "width": 435.0},  # мягкотканный
            }

            processed_count = 0
            total_images = 0

            for dicom_file in dicom_files:
                try:
                    ds = pydicom.dcmread(dicom_file)
                    hu_images = self.get_pixels_hu(ds)

                    # Получаем оригинальное имя файла
                    original_name = Path(dicom_file).stem

                    # Проверяем, является ли это multi-frame DICOM
                    if hu_images.ndim == 3:
                        # Multi-frame DICOM: (N, H, W)
                        num_slices = hu_images.shape[0]
                        logger.info(f"Multi-frame DICOM: {num_slices} срезов в файле {dicom_file}")

                        for i in range(num_slices):
                            hu_image = hu_images[i]
                            for mode_name, params in WINDOW_MODES.items():
                                processed = self.apply_window(
                                    hu_image, params["level"], params["width"]
                                )
                                filename = f"{original_name}_slice_{i:03d}_{mode_name}.png"
                                output_path = os.path.join(output_dir, filename)
                                cv2.imwrite(output_path, processed)
                                total_images += 1
                    else:
                        # Обычный DICOM: (H, W)
                        # logger.info(f"Обычный DICOM: 1 срез в файле {dicom_file}")
                        for mode_name, params in WINDOW_MODES.items():
                            processed = self.apply_window(
                                hu_images, params["level"], params["width"]
                            )
                            filename = f"{original_name}_{mode_name}.png"
                            output_path = os.path.join(output_dir, filename)
                            cv2.imwrite(output_path, processed)
                            total_images += 3

                    processed_count += 1

                except Exception as e:
                    logger.error(f"Ошибка с {dicom_file}: {str(e)}")
                    continue

            if processed_count == 0:
                logger.error("Не удалось обработать ни одного DICOM файла")
                return False

            logger.info(
                f"Извлечение завершено: {processed_count} DICOM файлов, "
                f"{total_images} PNG изображений"
            )
            return True

        except Exception as e:
            logger.error(f"Ошибка при извлечении изображений: {str(e)}")
            return False

    def validate_dicom_series(self, dicom_files: List[str]) -> Tuple[bool, str]:
        """
        Валидирует серию DICOM файлов с фильтрацией по тегам

        Args:
            dicom_files: Список путей к DICOM файлам

        Returns:
            Tuple[bool, str]: (успех, сообщение об ошибке)
        """
        if not dicom_files:
            return False, "Не найдено DICOM файлов"

        # Фильтруем файлы по тегам
        valid_files = []
        for dicom_file in dicom_files:
            is_valid, message = self.is_valid_chest_ct(dicom_file)
            if is_valid:
                valid_files.append(dicom_file)
            else:
                logger.info(f"Файл {dicom_file} отфильтрован: {message}")

        if not valid_files:
            return False, "Нет валидных КТ файлов грудной клетки после фильтрации"

        # Проверяем первый валидный файл для получения метаданных
        first_metadata = self.read_dicom_metadata(valid_files[0])
        if not first_metadata:
            return False, "Не удалось прочитать метаданные первого DICOM файла"

        study_uid = first_metadata.get("study_uid")
        series_uid = first_metadata.get("series_uid")

        if not study_uid:
            return False, "Отсутствует StudyInstanceUID"

        # Проверяем остальные файлы на соответствие серии
        for dicom_file in valid_files[1:]:
            metadata = self.read_dicom_metadata(dicom_file)
            if not metadata:
                return False, f"Ошибка чтения файла {dicom_file}"

            if metadata.get("study_uid") != study_uid:
                return False, f"Файл {dicom_file} не принадлежит к тому же исследованию"

            if metadata.get("series_uid") != series_uid:
                return False, f"Файл {dicom_file} не принадлежит к той же серии"

        logger.info(
            f"Валидация прошла успешно: {len(valid_files)} валидных файлов из {len(dicom_files)}"
        )
        return True, f"Валидация прошла успешно: {len(valid_files)} валидных файлов"

    def get_study_info(self, dicom_files: List[str]) -> Optional[Dict]:
        """
        Получает информацию об исследовании из DICOM файлов

        Args:
            dicom_files: Список путей к DICOM файлам

        Returns:
            Dict: Информация об исследовании
        """
        if not dicom_files:
            return None

        # Читаем метаданные первого файла
        metadata = self.read_dicom_metadata(dicom_files[0])
        if not metadata:
            return None

        return {
            "study_uid": metadata.get("study_uid"),
            "series_uid": metadata.get("series_uid"),
            "patient_name": str(metadata.get("patient_name", "")),
            "patient_id": metadata.get("patient_id", ""),
            "study_date": metadata.get("study_date", ""),
            "modality": metadata.get("modality", ""),
            "total_files": len(dicom_files),
            "image_dimensions": {
                "rows": metadata.get("rows", 0),
                "columns": metadata.get("columns", 0),
                "slices": len(dicom_files),
            },
        }
