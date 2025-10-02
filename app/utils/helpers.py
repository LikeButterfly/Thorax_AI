"""
Вспомогательные функции
"""

import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path


def get_current_time() -> datetime:
    """
    Получает текущее время в UTC+3

    Returns:
        datetime: Текущее время в UTC+3
    """
    utc_plus_3 = timezone(timedelta(hours=3))
    return datetime.now(utc_plus_3)


def generate_unique_filename(original_filename: str) -> str:
    """
    Генерирует уникальное имя файла

    Args:
        original_filename: Оригинальное имя файла

    Returns:
        str: Уникальное имя файла
    """
    file_extension = Path(original_filename).suffix
    unique_name = f"{uuid.uuid4()}{file_extension}"
    return unique_name


def ensure_directory_exists(directory_path: str) -> None:
    """
    Создает директорию если она не существует

    Args:
        directory_path: Путь к директории
    """
    Path(directory_path).mkdir(parents=True, exist_ok=True)


def get_file_size_mb(file_path: str) -> float:
    """
    Получает размер файла в мегабайтах

    Args:
        file_path: Путь к файлу

    Returns:
        float: Размер файла в MB
    """
    if not os.path.exists(file_path):
        return 0.0

    size_bytes = os.path.getsize(file_path)
    return size_bytes / (1024 * 1024)


def is_valid_zip_file(file_path: str) -> bool:
    """
    Проверяет является ли файл валидным ZIP архивом

    Args:
        file_path: Путь к файлу

    Returns:
        bool: True если файл валидный ZIP
    """
    import zipfile

    try:
        with zipfile.ZipFile(file_path, "r") as zip_file:
            # Пытаемся прочитать список файлов
            zip_file.namelist()
            return True
    except (zipfile.BadZipFile, zipfile.LargeZipFile):
        return False
    except Exception:
        return False
