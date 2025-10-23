"""
API endpoints для предсказаний ML модели
"""

import logging
import os
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter()
logger = logging.getLogger(__name__)


# Pydantic модели для API
class StudyPredictionRequest(BaseModel):
    study_id: int
    image_paths: List[str]


@router.post("/predict/study/{study_id}")
async def predict_study(
    study_id: int,
    request: StudyPredictionRequest,
    app_request: Request,
) -> Dict[str, Any]:
    """
    Предсказание патологий для исследования с новой логикой анализа

    Args:
        study_id: ID исследования
        request: Запрос с путями к изображениям
        app_request: FastAPI Request для доступа к состоянию приложения

    Returns:
        Результаты предсказаний с агрегацией на уровне исследования
    """
    # Получаем ML сервис из состояния приложения
    ml_service = getattr(app_request.app.state, "ml_service", None)

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
