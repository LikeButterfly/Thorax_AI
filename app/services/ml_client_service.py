"""
Сервис для взаимодействия с ML сервисом
"""

import asyncio
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
        self.timeout = settings.ml_service_timeout
        self.retry_attempts = settings.ml_service_retry_attempts
        self.retry_delay = 5  # секунды между попытками

    async def predict_study(self, study_id: int, image_paths: List[str]) -> Dict[str, Any]:
        """
        Отправляет исследование на обработку в ML сервис с retry логикой

        Args:
            study_id: ID исследования
            image_paths: Список путей к изображениям

        Returns:
            Результаты предсказаний
        """
        # Проверяем, что все файлы существуют
        valid_paths = []
        for path in image_paths:
            if Path(path).exists():
                valid_paths.append(path)
            else:
                logger.warning(f"Файл не найден: {path}")

        if not valid_paths:
            raise ValueError("Нет доступных изображений для обработки")

        logger.info(
            f"Отправляем исследование {study_id} в ML сервис. Изображений: {len(valid_paths)}"
        )

        # Retry логика
        last_exception = None
        for attempt in range(1, self.retry_attempts + 1):
            try:
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
                        error_msg = (
                            f"ML сервис вернул ошибку {response.status_code}: {response.text}"
                        )
                        logger.error(error_msg)
                        raise Exception(error_msg)

            except httpx.TimeoutException as e:
                error_msg = (
                    f"Таймаут при обработке исследования {study_id} в ML сервисе "
                    f"(попытка {attempt}/{self.retry_attempts})"
                )
                logger.error(error_msg)
                last_exception = e

                if attempt < self.retry_attempts:
                    logger.info(f"Повторная попытка через {self.retry_delay} секунд...")
                    await asyncio.sleep(self.retry_delay)
                else:
                    raise Exception(f"Превышено количество попыток ({self.retry_attempts})") from e

            except Exception as e:
                error_msg = (
                    f"Ошибка при обращении к ML сервису "
                    f"(попытка {attempt}/{self.retry_attempts}): {str(e)}"
                )
                logger.error(error_msg)
                last_exception = e

                if attempt < self.retry_attempts:
                    logger.info(f"Повторная попытка через {self.retry_delay} секунд...")
                    await asyncio.sleep(self.retry_delay)
                else:
                    raise Exception(f"Превышено количество попыток ({self.retry_attempts})") from e

        # Если дошли до сюда, значит все попытки исчерпаны
        raise Exception(
            f"Не удалось обработать исследование {study_id} после {self.retry_attempts} попыток"
        ) from last_exception

    async def check_ml_service_health(self) -> Dict[str, Any]:
        """
        Проверяет доступность ML сервиса и возвращает детальную информацию

        Returns:
            Dict с информацией о состоянии ML сервиса
        """
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(f"{self.ml_service_url}/health")

                if response.status_code == 200:
                    health_data = response.json()
                    logger.debug(f"ML сервис доступен: {health_data}")
                    return {
                        "available": True,
                        "status": health_data.get("status", "unknown"),
                        "model_loaded": health_data.get("model_loaded", False),
                        "device": health_data.get("device", "unknown"),
                    }
                else:
                    logger.warning(f"ML сервис вернул статус {response.status_code}")
                    return {
                        "available": False,
                        "status": f"HTTP {response.status_code}",
                        "model_loaded": False,
                        "device": "unknown",
                    }
        except httpx.TimeoutException:
            logger.warning("ML сервис недоступен: таймаут")
            return {
                "available": False,
                "status": "timeout",
                "model_loaded": False,
                "device": "unknown",
            }
        except Exception as e:
            logger.warning(f"ML сервис недоступен: {str(e)}")
            return {
                "available": False,
                "status": f"error: {str(e)}",
                "model_loaded": False,
                "device": "unknown",
            }
