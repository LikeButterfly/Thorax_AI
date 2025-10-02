"""
API endpoints для управления файлами и очистки
"""

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.services.active_analysis_service import ActiveAnalysisService
from app.services.mass_cleanup_service import MassCleanupService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cleanup", tags=["cleanup"])


@router.get("/analyses")
async def get_active_analyses(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    Проверяет активные загрузки
    """
    try:
        active_analysis_service = ActiveAnalysisService(db)
        has_active = active_analysis_service.has_active_analyses()

        return {"has_active_analyses": has_active}

    except Exception as e:
        logger.error(f"Ошибка при проверке активных загрузок: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ошибка при проверке: {str(e)}") from e


@router.post("/files")
async def cleanup_all_files(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    Удаляет все файлы всех исследований

    Массовое удаление файлов с проверкой активных анализов.
    """
    try:
        mass_cleanup_service = MassCleanupService(db)

        # Выполняем удаление
        success, message, statistics = mass_cleanup_service.cleanup_all_files()

        if not success:
            raise HTTPException(status_code=409, detail=message)

        return {"success": success, "message": message, "statistics": statistics}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при массовом удалении файлов: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ошибка при удалении файлов: {str(e)}") from e
