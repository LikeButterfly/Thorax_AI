"""
Сервис для взаимодействия с ML сервисом
"""

import logging
from pathlib import Path
from typing import Any, Dict, List

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class MLClientService:
    """Клиент для взаимодействия с ML сервисом"""

    def __init__(self):
        self.ml_service_url = settings.ml_service_url
        self.timeout = 3600  # 60 минут для обработки исследования  # FIXMEЫ

    async def predict_study(self, study_id: int, image_paths: List[str]) -> Dict[str, Any]:
        """
        Отправляет исследование на обработку в ML сервис

        Args:
            study_id: ID исследования
            image_paths: Список путей к изображениям

        Returns:
            Результаты предсказаний
        """
        try:
            logger.info(
                f"Отправляем исследование {study_id} в ML сервис. Изображений: {len(image_paths)}"
            )

            # Проверяем, что все файлы существуют
            valid_paths = []
            for path in image_paths:
                if Path(path).exists():
                    valid_paths.append(path)
                else:
                    logger.warning(f"Файл не найден: {path}")

            if not valid_paths:
                raise ValueError("Нет доступных изображений для обработки")

            # Отправляем запрос в ML сервис
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.ml_service_url}/predict/study/{study_id}",
                    json={"study_id": study_id, "image_paths": valid_paths},
                )

                if response.status_code == 200:
                    result = response.json()
                    logger.info(
                        f"ML сервис обработал исследование {study_id}. "
                        f"Найдено патологий: {len(result.get('pathology_images', []))}"
                    )
                    return result
                else:
                    error_msg = f"ML сервис вернул ошибку {response.status_code}: {response.text}"
                    logger.error(error_msg)
                    raise Exception(error_msg)

        except httpx.TimeoutException as e:
            error_msg = f"Таймаут при обработке исследования {study_id} в ML сервисе"
            logger.error(error_msg)
            raise Exception(error_msg) from e
        except Exception as e:
            logger.error(f"Ошибка при обращении к ML сервису: {str(e)}")
            raise

    async def check_ml_service_health(self) -> bool:
        """
        Проверяет доступность ML сервиса

        Returns:
            True если сервис доступен, False иначе
        """
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(f"{self.ml_service_url}/health")
                return response.status_code == 200
        except Exception as e:
            logger.warning(f"ML сервис недоступен: {str(e)}")
            return False

    async def predict_single_image(self, image_path: str) -> Dict[str, Any]:
        """
        Предсказание для одного изображения (для тестирования)

        Args:
            image_path: Путь к изображению

        Returns:
            Результат предсказания
        """
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.get(f"{self.ml_service_url}/predict/image/{image_path}")

                if response.status_code == 200:
                    return response.json()
                else:
                    error_msg = f"Ошибка ML сервиса: {response.status_code}: {response.text}"
                    logger.error(error_msg)
                    raise Exception(error_msg)

        except Exception as e:
            logger.error(f"Ошибка при обращении к ML сервису: {str(e)}")
            raise
