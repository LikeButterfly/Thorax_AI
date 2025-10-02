"""
Сервис для поиска патологий на изображениях с использованием ML модели
"""

import json
import logging
import tempfile
import zipfile
from pathlib import Path
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.study import Series, Study
from app.services.ml_client_service import MLClientService

logger = logging.getLogger(__name__)


class PathologyDetectionService:
    """Сервис для поиска патологий на изображениях"""

    def __init__(self, db: Session):
        self.db = db
        self.ml_client = MLClientService()

    async def detect_pathologies_in_study(self, study_id: int) -> bool:
        """
        Поиск патологий в исследовании с использованием ML сервиса

        Args:
            study_id: ID исследования

        Returns:
            bool: True если патологии найдены
        """
        try:
            logger.info(
                f"Начинаем поиск патологий для исследования {study_id} с использованием ML сервиса"
            )

            # Получаем исследование из базы
            study = self.db.query(Study).filter(Study.id == study_id).first()

            if not study:
                logger.error(f"Исследование {study_id} не найдено")
                return False

            # Получаем все серии исследования
            series_list = (
                self.db.query(Series).filter(Series.study_id == study_id, Series.is_active).all()
            )

            if not series_list:
                logger.warning(f"Нет активных серий для исследования {study_id}")
                return False

            logger.info(f"Найдено {len(series_list)} серий для исследования {study_id}")

            # Собираем все пути к изображениям
            image_paths = []
            for series in series_list:
                if series.images_dir and Path(series.images_dir).exists():  # type: ignore
                    image_dir = Path(series.images_dir)  # type: ignore
                    # Ищем все PNG изображения
                    png_files = list(image_dir.glob("*.png"))
                    for png_file in png_files:
                        image_paths.append(str(png_file))

            if not image_paths:
                logger.warning(f"Нет изображений для исследования {study_id}")
                return False

            logger.info(f"Найдено {len(image_paths)} изображений для анализа")

            # Проверяем доступность ML сервиса
            if not await self.ml_client.check_ml_service_health():
                error_msg = "ML сервис недоступен. Анализ патологий невозможен."
                logger.error(error_msg)
                raise Exception("ML сервис недоступен")

            # Начинаем отсчет времени ML анализа
            import time

            ml_start_time = time.time()

            # Отправляем на анализ в ML сервис
            ml_result = await self.ml_client.predict_study(study_id, image_paths)

            # Рассчитываем время ML анализа
            ml_processing_time = time.time() - ml_start_time

            # Проверяем наличие ошибки в результате ML
            if "error" in ml_result:
                error_msg = ml_result["error"]
                logger.error(f"Ошибка ML анализа для исследования {study_id}: {error_msg}")
                study.processing_status = "Failure"  # type: ignore
                study.error_message = f"ML анализ не удался: {error_msg}"  # type: ignore
                self.db.commit()
                return False

            # Обновляем исследование на основе результатов ML с новой логикой
            mean_prob = ml_result.get("mean_prob")
            predicted_class = ml_result.get("predicted_class")
            ci_95 = ml_result.get("ci_95")
            pathology_images = ml_result.get("pathology_images", [])
            # n_frames = ml_result.get("n_frames")
            # frac_positive = ml_result.get("frac_positive")

            # Проверяем, что все необходимые поля получены
            if mean_prob is None or predicted_class is None or ci_95 is None:
                logger.error(f"Неполные данные от ML сервиса для исследования {study_id}")
                study.processing_status = "Failure"  # type: ignore
                study.error_message = "ML сервис вернул неполные данные"  # type: ignore
                self.db.commit()
                return False

            # Обновляем поля исследования
            study.pathology = bool(predicted_class)  # type: ignore
            study.probability_of_pathology = mean_prob  # type: ignore
            study.ci_95 = ci_95  # type: ignore

            # Фильтруем только lung контрастирование и убираем дубликаты
            # В новой логике pathology_images уже содержат только изображения
            # с prob >= THRESHOLD_FRAME_PROB (0.6)
            lung_pathology_images = []
            seen_paths = set()

            for image_path in pathology_images:
                if "_lung.png" in image_path and image_path not in seen_paths:
                    lung_pathology_images.append(image_path)
                    seen_paths.add(image_path)

            study.pathology_images = json.dumps(lung_pathology_images)  # type: ignore

            logger.info(
                f"Обновлено исследование {study_id}: "
                f"pathology={study.pathology}, "
                f"probability_of_pathology={study.probability_of_pathology:.4f}, "
                f"ci_95={study.ci_95}, "
                f"pathology_images={len(lung_pathology_images)}"
            )

            # Обновляем серии на основе результатов ML (новая логика)
            # В новой логике все серии исследования имеют одинаковый статус патологии
            series_pathology_map = {}

            for series in series_list:
                series.pathology = bool(predicted_class)  # type: ignore
                series.probability_of_pathology = mean_prob  # type: ignore
                series.ci_95 = ci_95  # type: ignore

                # Запоминаем серии с патологиями
                if series.pathology:  # type: ignore
                    series_pathology_map[series.id] = series  # type: ignore

                logger.debug(
                    f"Серия {series.id}: патология = {series.pathology}, "
                    f"probability = {series.probability_of_pathology:.4f}, "
                    f"ci_95 = {series.ci_95}"  # type: ignore
                )

            # DICOM файлы будут создаваться по запросу, а не здесь
            # Это ускоряет основной процесс анализа патологий

            # Сохраняем изменения
            self.db.commit()

            # Логируем статус серий после обновления
            for series in series_list:
                logger.info(
                    f"Серия {series.id}: патология = {series.pathology}, "
                    f"images_dir = {series.images_dir}"
                )

            logger.info(
                f"ML анализ завершен для исследования {study_id} за {ml_processing_time:.2f}с. "
                f"Найдены патологии: {study.pathology}, "
                f"Изображений с патологиями (lung): {len(lung_pathology_images)}, "
                f"Серий с патологиями: {len(series_pathology_map)}"
            )

            return study.pathology  # type: ignore

        except Exception as e:
            logger.error(f"Ошибка при поиске патологий для исследования {study_id}: {str(e)}")
            self.db.rollback()
            return False

    def create_pathology_dicom_files(self, study_id: int) -> bool:
        """
        Создает список DICOM файлов с патологиями по запросу

        Args:
            study_id: ID исследования

        Returns:
            bool: True если успешно созданы
        """
        try:
            logger.info(f"Создаем список DICOM файлов с патологиями для исследования {study_id}")

            # Получаем исследование
            study = self.db.query(Study).filter(Study.id == study_id).first()
            if not study:
                logger.error(f"Исследование {study_id} не найдено")
                return False

            # Проверяем флаг одного DICOM файла
            if study.is_single_dicom:  # type: ignore
                logger.info(f"Исследование {study_id} содержит один DICOM файл - упрощенная логика")
                # Для одного DICOM файла берем все файлы из серии
                series_list = (
                    self.db.query(Series)
                    .filter(Series.study_id == study_id, Series.is_active)
                    .all()
                )

                if (
                    series_list
                    and series_list[0].dicom_dir
                    and Path(series_list[0].dicom_dir).exists()  # type: ignore
                ):
                    dicom_dir = Path(series_list[0].dicom_dir)  # type: ignore
                    all_dicom_files = [str(f) for f in dicom_dir.iterdir() if f.is_file()]
                    study.pathology_dicom_files = json.dumps(all_dicom_files)  # type: ignore
                    self.db.commit()
                    logger.info(f"Для одного DICOM файла найдено {len(all_dicom_files)} файлов")
                    return True
                else:
                    logger.warning(f"Не найдена директория DICOM для исследования {study_id}")
                    return False

            # Получаем изображения с патологиями
            pathology_images = []
            if study.pathology_images:  # type: ignore
                try:
                    pathology_images = json.loads(study.pathology_images)  # type: ignore
                except json.JSONDecodeError:
                    logger.error(f"Ошибка парсинга pathology_images для исследования {study_id}")
                    return False

            if not pathology_images:
                logger.warning(f"Нет изображений с патологиями для исследования {study_id}")
                study.pathology_dicom_files = json.dumps([])  # type: ignore
                self.db.commit()
                return True

            # Получаем серии исследования
            series_list = (
                self.db.query(Series).filter(Series.study_id == study_id, Series.is_active).all()
            )

            pathology_dicom_files = []

            # Для каждого изображения с патологией ищем соответствующий DICOM файл
            for image_path in pathology_images:
                image_name = Path(image_path).name
                base_name = image_name.replace("_lung.png", "")

                # Находим серию по пути к изображению
                for series in series_list:
                    if series.images_dir and image_path.startswith(series.images_dir):  # type: ignore  # noqa: E501
                        # Ищем соответствующий DICOM файл в этой серии
                        if series.dicom_dir and Path(series.dicom_dir).exists():  # type: ignore
                            dicom_dir = Path(series.dicom_dir)  # type: ignore
                            dicom_files = [f.name for f in dicom_dir.iterdir() if f.is_file()]

                            # Ищем DICOM файл с похожим именем
                            for dicom_file in dicom_files:
                                if base_name in dicom_file or dicom_file.startswith(base_name):
                                    full_dicom_path = str(dicom_dir / dicom_file)
                                    if full_dicom_path not in pathology_dicom_files:
                                        pathology_dicom_files.append(full_dicom_path)
                                        logger.debug(
                                            f"Найден DICOM файл: {full_dicom_path} для {image_name}"
                                        )
                                    break
                        break

            study.pathology_dicom_files = json.dumps(pathology_dicom_files)  # type: ignore
            self.db.commit()

            logger.info(f"Создан список из {len(pathology_dicom_files)} DICOM файлов с патологиями")
            return True

        except Exception as e:
            logger.error(f"Ошибка при создании DICOM файлов для исследования {study_id}: {str(e)}")
            self.db.rollback()
            return False

    def create_pathology_images_zip(self, study_id: int) -> Optional[str]:
        """
        Создает ZIP архив с изображениями патологий

        Args:
            study_id: ID исследования

        Returns:
            Путь к созданному ZIP файлу или None
        """
        try:
            logger.info(f"Создаем ZIP архив с изображениями патологий для исследования {study_id}")

            # Получаем исследование
            study = self.db.query(Study).filter(Study.id == study_id).first()
            if not study:
                logger.error(f"Исследование {study_id} не найдено")
                return None

            # Получаем список изображений с патологиями
            pathology_images = []
            if study.pathology_images:  # type: ignore
                try:
                    pathology_images = json.loads(study.pathology_images)  # type: ignore
                    logger.info(
                        f"Загружен список изображений с патологиями: {len(pathology_images)} файлов"
                    )
                except json.JSONDecodeError:
                    logger.error(f"Ошибка парсинга pathology_images для исследования {study_id}")
                    return None
            else:
                logger.warning(f"pathology_images не установлен для исследования {study_id}")

            if not pathology_images:
                logger.info(f"Нет изображений с патологиями для исследования {study_id}")
                return None

            # Получаем серии с патологиями
            series_with_pathology = (
                self.db.query(Series)
                .filter(Series.study_id == study_id, Series.pathology, Series.is_active)
                .all()
            )

            if not series_with_pathology:
                logger.info(f"Нет серий с патологиями для исследования {study_id}")
                return None

            # Создаем временный ZIP файл
            with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as temp_file:
                temp_path = temp_file.name

            files_added = 0
            with zipfile.ZipFile(temp_path, "w", zipfile.ZIP_DEFLATED) as zip_file:
                # Добавляем изображения по полным путям
                for image_path in pathology_images:
                    if Path(image_path).exists():
                        # Добавляем в ZIP с относительным путем
                        image_name = Path(image_path).name
                        zip_file.write(image_path, f"pathology_images/{image_name}")
                        files_added += 1

            if files_added == 0:
                logger.warning(
                    f"Не найдено изображений для добавления в архив для исследования {study_id}"
                )
                return None

            logger.info(
                f"Создан ZIP архив с изображениями патологий: {temp_path} "
                "(добавлено файлов: {files_added})"
            )
            return temp_path

        except Exception as e:
            logger.error(
                f"Ошибка при создании ZIP архива с изображениями для исследования "
                f"{study_id}: {str(e)}"
            )
            return None

    def create_pathology_dicom_zip(self, study_id: int) -> Optional[str]:
        """
        Создает ZIP архив с DICOM файлами патологий

        Args:
            study_id: ID исследования

        Returns:
            Путь к созданному ZIP файлу или None
        """
        try:
            logger.info(f"Создаем ZIP архив с DICOM файлами патологий для исследования {study_id}")

            # Получаем исследование
            study = self.db.query(Study).filter(Study.id == study_id).first()
            if not study:
                logger.error(f"Исследование {study_id} не найдено")
                return None

            # Получаем список DICOM файлов с патологиями
            pathology_dicom_files = []
            if study.pathology_dicom_files:  # type: ignore
                try:
                    pathology_dicom_files = json.loads(study.pathology_dicom_files)  # type: ignore
                    logger.info(
                        f"Загружен список DICOM файлов с патологиями: "
                        f"{len(pathology_dicom_files)} файлов"
                    )
                except json.JSONDecodeError:
                    logger.error(
                        f"Ошибка парсинга pathology_dicom_files для исследования {study_id}"
                    )
                    return None
            else:
                logger.warning(f"pathology_dicom_files не установлен для исследования {study_id}")

            if not pathology_dicom_files:
                logger.info(f"Нет DICOM файлов с патологиями для исследования {study_id}")
                # Не возвращаем None сразу, попробуем найти файлы в сериях с патологиями

            # Получаем серии с патологиями
            series_with_pathology = (
                self.db.query(Series)
                .filter(Series.study_id == study_id, Series.pathology, Series.is_active)
                .all()
            )

            if not series_with_pathology:
                logger.info(f"Нет серий с патологиями для исследования {study_id}")
                return None

            # Создаем временный ZIP файл
            with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as temp_file:
                temp_path = temp_file.name

            files_added = 0
            with zipfile.ZipFile(temp_path, "w", zipfile.ZIP_DEFLATED) as zip_file:
                # Добавляем DICOM файлы по полным путям
                for dicom_path in pathology_dicom_files:
                    if Path(dicom_path).exists():
                        # Добавляем в ZIP с относительным путем
                        dicom_name = Path(dicom_path).name
                        zip_file.write(dicom_path, f"pathology_dicom/{dicom_name}")
                        files_added += 1

            if files_added == 0:
                logger.warning(
                    f"Не найдено DICOM файлов для добавления в архив для исследования {study_id}"
                )
                return None

            logger.info(
                f"Создан ZIP архив с DICOM файлами патологий: {temp_path} "
                "(добавлено файлов: {files_added})"
            )
            return temp_path

        except Exception as e:
            logger.error(
                f"Ошибка при создании ZIP архива с DICOM файлами для исследования "
                f"{study_id}: {str(e)}"
            )
            return None
