"""
Celery tasks для асинхронной обработки
"""

from app.tasks.study_tasks import process_single_study_task

__all__ = ["process_single_study_task"]
