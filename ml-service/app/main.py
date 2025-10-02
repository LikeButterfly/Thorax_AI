"""
ML Service - Сервис для предсказания патологий с использованием Swin Transformer
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Any, Dict, List

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.config import settings
from app.ml_model import MLModelService

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Глобальная переменная для модели
ml_service = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом приложения"""
    global ml_service

    # Загрузка модели при старте
    logger.info("Загружаем ML модель...")
    ml_service = MLModelService()
    await ml_service.load_model()
    logger.info("ML модель загружена успешно")

    yield

    # Очистка при завершении
    logger.info("Очищаем ресурсы...")


app = FastAPI(
    title="ML Pathology Detection Service",
    description="Сервис для предсказания патологий с использованием Swin Transformer",
    version="1.0.0",
    lifespan=lifespan,
)


# Pydantic модели для API
class StudyPredictionRequest(BaseModel):
    study_id: int
    image_paths: List[str]


class ImagePrediction(BaseModel):
    image_path: str
    contrast_type: str
    pathology_probability: float
    has_pathology: bool


class StudyPredictionResponse(BaseModel):
    study_id: int
    total_images: int
    pathology_images: List[str]
    predictions: List[ImagePrediction]
    study_has_pathology: bool


@app.get("/health")
async def health_check():
    """Проверка здоровья сервиса"""
    return {"status": "healthy", "model_loaded": ml_service is not None}


@app.post("/predict/study/{study_id}")
async def predict_study(study_id: int, request: StudyPredictionRequest):
    """
    Предсказание патологий для исследования с новой логикой анализа

    Args:
        study_id: ID исследования
        request: Запрос с путями к изображениям

    Returns:
        Результаты предсказаний с агрегацией на уровне исследования
    """
    if ml_service is None:
        raise HTTPException(status_code=503, detail="ML модель не загружена")

    try:
        logger.info(
            f"Начинаем обработку исследования {study_id} с {len(request.image_paths)} изображениями"
        )

        # Используем новую логику анализа
        result = await ml_service.analyze_study_with_new_logic(request.image_paths)

        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])

        return {
            "study_id": study_id,
            "mean_prob": result["mean_prob"],
            "predicted_class": result["predicted_class"],
            "ci_95": result["ci_95"],
            "n_frames": result["n_frames"],
            "frac_positive": result["frac_positive"],
            "pathology_images": result["pathology_images"],
        }

    except Exception as e:
        logger.error(f"Ошибка при обработке исследования {study_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ошибка обработки: {str(e)}") from e


@app.get("/predict/image/{image_path:path}")
async def predict_single_image(image_path: str):
    """
    Предсказание для одного изображения (для тестирования)
    """
    if ml_service is None:
        raise HTTPException(status_code=503, detail="ML модель не загружена")

    if not os.path.exists(image_path):
        raise HTTPException(status_code=404, detail="Файл не найден")

    try:
        prediction = await ml_service.predict_image(image_path)
        return prediction
    except Exception as e:
        logger.error(f"Ошибка при обработке изображения {image_path}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ошибка обработки: {str(e)}") from e


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8001, reload=True)
