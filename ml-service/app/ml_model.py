"""
Сервис для работы с ML моделью Swin Transformer
"""

import asyncio
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd
import timm
import torch
import torch.nn.functional as F
from PIL import Image
from statsmodels.stats.proportion import proportion_confint
from torchvision import transforms

from app.config import settings

logger = logging.getLogger(__name__)


class MLModelService:
    """Сервис для работы с ML моделью"""

    def __init__(self):
        self.model: Optional[torch.nn.Module] = None
        self.device: str = settings.get_device()
        self.transform = None
        self.class_names = ["normal", "pathologies"]
        self._model_loaded = False

        # Константы для анализа патологий
        self.THRESHOLD_FRAME_PROB = 0.6  # порог вероятности патологии на кадре
        self.THRESHOLD_FRAC = 0.12  # минимальная доля положительных кадров для исследования

    async def load_model(self):
        """Асинхронная загрузка модели"""
        try:
            logger.info(f"Загружаем модель на устройство: {self.device}")

            # Загружаем модель в отдельном потоке
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._load_model_sync)

            self._model_loaded = True
            logger.info("Модель загружена успешно")

        except Exception as e:
            logger.error(f"Ошибка загрузки модели: {str(e)}")
            raise

    def _load_model_sync(self):
        """Синхронная загрузка модели"""
        # Создаем модель
        self.model = timm.create_model(
            settings.MODEL_NAME, pretrained=False, num_classes=settings.NUM_CLASSES
        )

        # Загружаем веса
        model_path = Path(settings.MODEL_PATH)
        if not model_path.exists():
            raise FileNotFoundError(f"Файл модели не найден: {model_path}")

        state_dict = torch.load(model_path, map_location=self.device)
        self.model.load_state_dict(state_dict)

        # Переводим в режим оценки
        self.model.to(self.device)
        self.model.eval()

        # Настраиваем трансформации
        self.transform = transforms.Compose(
            [
                transforms.Resize((224, 224)),
                transforms.ToTensor(),
                transforms.Normalize([0.5, 0.5, 0.5], [0.5, 0.5, 0.5]),
            ]
        )

        logger.info(f"Модель {settings.MODEL_NAME} загружена с {settings.NUM_CLASSES} классами")

    async def predict_image(self, image_path: str) -> Dict[str, Any]:
        """
        Предсказание для одного изображения

        Args:
            image_path: Путь к изображению

        Returns:
            Словарь с результатами предсказания
        """
        if not self._model_loaded:
            raise RuntimeError("Модель не загружена")

        try:
            # Загружаем и обрабатываем изображение
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, self._predict_image_sync, image_path)

            return result

        except Exception as e:
            logger.error(f"Ошибка предсказания для {image_path}: {str(e)}")
            raise

    def _predict_image_sync(self, image_path: str) -> Dict[str, Any]:
        """Синхронное предсказание изображения"""
        # Загружаем изображение
        image = Image.open(image_path).convert("RGB")

        # Применяем трансформации
        image_tensor = self.transform(image).unsqueeze(0).to(self.device)  # type: ignore

        # Предсказание
        with torch.no_grad():
            outputs = self.model(image_tensor)  # type: ignore
            probabilities = F.softmax(outputs, dim=1)

            # Получаем предсказанный класс и вероятности
            predicted_class = torch.argmax(probabilities, dim=1).item()
            probs = probabilities.cpu().numpy()[0]

            # Извлекаем вероятность патологии
            pathology_probability = float(probs[1])  # Индекс 1 = "pathologies"
            has_pathology = pathology_probability > settings.PATHOLOGY_THRESHOLD

            return {
                "image_path": image_path,
                "predicted_class": self.class_names[predicted_class],  # type: ignore
                "pathology_probability": pathology_probability,
                "normal_probability": float(probs[0]),
                "has_pathology": has_pathology,
                "probabilities": {"normal": float(probs[0]), "pathologies": float(probs[1])},  # type: ignore  # noqa E501
            }

    async def predict_batch(self, image_paths: list) -> list:
        """
        Батчевое предсказание для нескольких изображений

        Args:
            image_paths: Список путей к изображениям

        Returns:
            Список результатов предсказаний
        """
        if not self._model_loaded:
            raise RuntimeError("Модель не загружена")

        results = []
        for image_path in image_paths:
            try:
                result = await self.predict_image(image_path)
                results.append(result)
            except Exception as e:
                logger.error(f"Ошибка обработки {image_path}: {str(e)}")
                # Добавляем результат с ошибкой
                results.append(
                    {
                        "image_path": image_path,
                        "error": str(e),
                        "pathology_probability": 0.0,
                        "has_pathology": False,
                    }
                )

        return results

    def extract_study_id(self, filename: str) -> str:
        """
        Извлекает study_id из имени файла

        Args:
            filename: Имя файла

        Returns:
            str: study_id
        """
        base = str(filename).split(".")[0]
        m = re.match(r"^(.*?)[_-]?\d+$", base)  # удаляем финальные номера "_0123"
        if m:
            return m.group(1)
        for sep in ["_", "-"]:
            if sep in base:
                return base.split(sep)[0]
        return base

    def compute_ci_interval(self, probs: np.ndarray, alpha: float = 0.05) -> str:
        """
        Вычисляет доверительный интервал для доли положительных кадров

        Args:
            probs: Массив вероятностей патологии
            alpha: Уровень значимости

        Returns:
            str: Строка с доверительным интервалом
        """
        preds = (probs >= self.THRESHOLD_FRAME_PROB).astype(int)
        successes = preds.sum()
        n = len(preds)
        ci_low, ci_high = proportion_confint(successes, n, method="wilson", alpha=alpha)
        return f"[{ci_low:.3f} ; {ci_high:.3f}]"

    async def analyze_study_with_new_logic(self, image_paths: list) -> Dict[str, Any]:
        """
        Анализ исследования с новой логикой (агрегация на уровне исследования)

        Args:
            image_paths: Список путей к изображениям

        Returns:
            Dict с результатами анализа
        """
        if not self._model_loaded:
            raise RuntimeError("Модель не загружена")

        try:
            # Получаем предсказания для всех изображений
            results = await self.predict_batch(image_paths)

            # Создаем DataFrame из результатов
            rows = []
            for result in results:
                if "error" not in result:
                    rows.append(
                        {
                            "filename": os.path.basename(result["image_path"]),
                            "predicted_class_frame": result["predicted_class"],
                            "prob_normal": result["probabilities"]["normal"],
                            "prob_pathologies": result["probabilities"]["pathologies"],
                        }
                    )

            if not rows:
                return {"error": "Нет валидных изображений для анализа"}

            df = pd.DataFrame(rows)
            df["study_id"] = df["filename"].apply(self.extract_study_id)

            # Агрегация на уровне исследования
            group = df.groupby("study_id")["prob_pathologies"]

            study_level = group.agg(
                n_frames="count", mean_prob="mean", max_prob="max"
            ).reset_index()

            # Доля положительных кадров
            study_level["frac_positive"] = group.apply(
                lambda x: (x >= self.THRESHOLD_FRAME_PROB).mean()
            ).values

            # Бинарное решение на уровне исследования
            study_level["predicted_class"] = (
                study_level["frac_positive"] >= self.THRESHOLD_FRAC
            ).astype(int)

            # CI для доли положительных кадров
            ci_df = group.apply(lambda x: self.compute_ci_interval(x)).reset_index()
            ci_df.rename(columns={"prob_pathologies": "CI_95"}, inplace=True)

            study_level = study_level.merge(ci_df, on="study_id", how="left")

            # Получаем изображения с патологиями (>= THRESHOLD_FRAME_PROB)
            pathology_images = []
            for result in results:
                if (
                    "error" not in result
                    and result["probabilities"]["pathologies"] >= self.THRESHOLD_FRAME_PROB
                ):
                    pathology_images.append(result["image_path"])

            # Возвращаем результат для первого (и единственного) исследования
            study_result = study_level.iloc[0]

            return {
                "mean_prob": float(study_result["mean_prob"]),
                "predicted_class": int(study_result["predicted_class"]),
                "ci_95": study_result["CI_95"],
                "n_frames": int(study_result["n_frames"]),
                "frac_positive": float(study_result["frac_positive"]),
                "pathology_images": pathology_images,
            }

        except Exception as e:
            logger.error(f"Ошибка анализа исследования: {str(e)}")
            return {"error": str(e)}

    def get_model_info(self) -> Dict[str, Any]:
        """Возвращает информацию о модели"""
        return {
            "model_name": settings.MODEL_NAME,
            "num_classes": settings.NUM_CLASSES,
            "device": self.device,
            "model_loaded": self._model_loaded,
            "pathology_threshold": settings.PATHOLOGY_THRESHOLD,
        }
