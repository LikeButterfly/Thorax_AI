"""
Базовый сервис для общих операций
"""

import logging
from abc import abstractmethod
from typing import Any, Dict, Generic, List, Optional, Type, TypeVar
from uuid import uuid4

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Тип для модели
ModelType = TypeVar("ModelType")  # , bound=Base


class BaseService(Generic[ModelType]):
    """
    Базовый сервис для работы с моделями

    Предоставляет общие CRUD операции и методы для работы с базой данных.
    """

    def __init__(self, db: Session, model: Type[ModelType]):
        """
        Инициализация сервиса

        Args:
            db: Сессия базы данных
            model: Класс модели SQLAlchemy
        """
        self.db = db
        self.model = model

    def create(self, **kwargs) -> ModelType:
        """
        Создает новую запись в базе данных

        Args:
            **kwargs: Поля для создания записи

        Returns:
            ModelType: Созданная запись

        Raises:
            SQLAlchemyError: Ошибка при создании записи
        """
        try:
            # Генерируем UUID если нужно
            if hasattr(self.model, "internal_id") and "internal_id" not in kwargs:
                kwargs["internal_id"] = str(uuid4())

            instance = self.model(**kwargs)
            self.db.add(instance)
            self.db.flush()  # Получаем ID без commit
            return instance
        except SQLAlchemyError as e:
            logger.error(f"Ошибка при создании записи {self.model.__name__}: {e}")
            self.db.rollback()
            raise

    def get_by_id(self, id: int) -> Optional[ModelType]:
        """
        Получает запись по ID

        Args:
            id: ID записи

        Returns:
            Optional[ModelType]: Запись или None
        """
        try:
            return self.db.query(self.model).filter(self.model.id == id).first()  # type: ignore
        except SQLAlchemyError as e:
            logger.error(f"Ошибка при получении записи {self.model.__name__} по ID {id}: {e}")
            return None

    def get_by_field(self, field_name: str, value: Any) -> Optional[ModelType]:
        """
        Получает запись по значению поля

        Args:
            field_name: Название поля
            value: Значение поля

        Returns:
            Optional[ModelType]: Запись или None
        """
        try:
            field = getattr(self.model, field_name)
            return self.db.query(self.model).filter(field == value).first()
        except (SQLAlchemyError, AttributeError) as e:
            logger.error(
                f"Ошибка при получении записи {self.model.__name__} по полю {field_name}: {e}"
            )
            return None

    def get_all(
        self, skip: int = 0, limit: int = 100, filters: Optional[Dict[str, Any]] = None
    ) -> List[ModelType]:
        """
        Получает список записей с фильтрацией и пагинацией

        Args:
            skip: Количество пропущенных записей
            limit: Максимальное количество записей
            filters: Словарь фильтров {поле: значение}

        Returns:
            List[ModelType]: Список записей
        """
        try:
            query = self.db.query(self.model)

            # Применяем фильтры
            if filters:
                for field_name, value in filters.items():
                    if hasattr(self.model, field_name):
                        field = getattr(self.model, field_name)
                        query = query.filter(field == value)

            return query.offset(skip).limit(limit).all()
        except SQLAlchemyError as e:
            logger.error(f"Ошибка при получении списка записей {self.model.__name__}: {e}")
            return []

    def update(self, id: int, **kwargs) -> Optional[ModelType]:
        """
        Обновляет запись по ID

        Args:
            id: ID записи
            **kwargs: Поля для обновления

        Returns:
            Optional[ModelType]: Обновленная запись или None
        """
        try:
            instance = self.get_by_id(id)
            if not instance:
                return None

            for field_name, value in kwargs.items():
                if hasattr(instance, field_name):
                    setattr(instance, field_name, value)

            self.db.flush()
            return instance
        except SQLAlchemyError as e:
            logger.error(f"Ошибка при обновлении записи {self.model.__name__} с ID {id}: {e}")
            self.db.rollback()
            return None

    def delete(self, id: int) -> bool:
        """
        Удаляет запись по ID (мягкое удаление)

        Args:
            id: ID записи

        Returns:
            bool: True если успешно
        """
        try:
            instance = self.get_by_id(id)
            if not instance:
                return False

            # Мягкое удаление
            if hasattr(instance, "is_active"):
                instance.is_active = False  # type: ignore
            else:
                self.db.delete(instance)

            self.db.flush()
            return True
        except SQLAlchemyError as e:
            logger.error(f"Ошибка при удалении записи {self.model.__name__} с ID {id}: {e}")
            self.db.rollback()
            return False

    def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        """
        Подсчитывает количество записей с фильтрацией

        Args:
            filters: Словарь фильтров {поле: значение}

        Returns:
            int: Количество записей
        """
        try:
            query = self.db.query(self.model)

            # Применяем фильтры
            if filters:
                for field_name, value in filters.items():
                    if hasattr(self.model, field_name):
                        field = getattr(self.model, field_name)
                        query = query.filter(field == value)

            return query.count()
        except SQLAlchemyError as e:
            logger.error(f"Ошибка при подсчете записей {self.model.__name__}: {e}")
            return 0

    def commit(self) -> bool:
        """
        Сохраняет изменения в базе данных

        Returns:
            bool: True если успешно
        """
        try:
            self.db.commit()
            return True
        except SQLAlchemyError as e:
            logger.error(f"Ошибка при сохранении изменений: {e}")
            self.db.rollback()
            return False

    def rollback(self) -> None:
        """Откатывает изменения в базе данных"""
        self.db.rollback()

    @abstractmethod
    def validate_data(self, data: Dict[str, Any]) -> bool:
        """
        Валидирует данные перед сохранением

        Args:
            data: Данные для валидации

        Returns:
            bool: True если данные валидны
        """
        pass
