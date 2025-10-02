"""
Сервис для генерации Excel отчетов
"""

import os
from pathlib import Path
from typing import Optional

import pandas as pd
from sqlalchemy.orm import Session

from app.models.study import Series, Study, UploadBatch
from app.services.mapping_service import MappingService


class ReportService:
    """Сервис для генерации отчетов"""

    def __init__(self, db: Session):
        self.db = db
        self.mapping_service = MappingService(db)

    async def generate_batch_report(self, batch_id: int) -> Optional[str]:
        """
        Генерирует Excel отчет для всех исследований в батче

        Args:
            batch_id: ID батча загрузки

        Returns:
            Optional[str]: Путь к созданному файлу или None при ошибке
        """
        try:
            # Получаем батч
            batch = self.db.query(UploadBatch).filter(UploadBatch.id == batch_id).first()
            if not batch:
                return None

            # Получаем все исследования батча
            studies = (
                self.db.query(Study)
                .filter(Study.upload_batch_id == batch_id)
                .filter(Study.is_active)
                .all()
            )

            if not studies:
                return None

            report_data = []

            for study in studies:
                # Получаем DICOM UID
                study_uid = self.mapping_service.get_study_dicom_uid(study.id)  # type: ignore

                # Получаем серии исследования
                series_list = (
                    self.db.query(Series)
                    .filter(Series.study_id == study.id)
                    .filter(Series.is_active)
                    .all()
                )

                if series_list:
                    # Для каждой серии создаем отдельную строку
                    for series in series_list:
                        series_uid = self.mapping_service.get_series_dicom_uid(series.id)  # type: ignore

                        report_data.append(
                            {
                                "path_to_study": str(study.study_path or study.path_to_study),
                                "study_uid": str(study_uid or ""),
                                "series_uid": str(series_uid or ""),
                                "probability_of_pathology": float(series.probability_of_pathology)  # type: ignore  # noqa: E501
                                if series.probability_of_pathology is not None
                                else 0.0,
                                "pathology": 1 if bool(series.pathology) else 0,
                                "processing_status": str(series.processing_status),
                                "time_of_processing": float(study.processing_time)  # type: ignore  # noqa: E501
                                if study.processing_time is not None
                                else 0.0,
                                "ci_95": study.ci_95 or "",  # ci_95 как последняя колонка
                            }
                        )
                else:
                    # Если нет серий, создаем строку только для исследования
                    report_data.append(
                        {
                            "path_to_study": str(study.study_path or study.path_to_study),
                            "study_uid": str(study_uid or ""),
                            "series_uid": "",
                            "probability_of_pathology": float(study.probability_of_pathology)  # type: ignore  # noqa: E501
                            if study.probability_of_pathology is not None
                            else 0.0,
                            "pathology": 1 if bool(study.pathology) else 0,
                            "processing_status": str(study.processing_status),
                            "time_of_processing": float(study.processing_time)  # type: ignore  # noqa: E501
                            if study.processing_time is not None
                            else 0.0,
                            "ci_95": study.ci_95 or "",
                        }
                    )

            # Создаем DataFrame
            df = pd.DataFrame(report_data)

            # Явно указываем типы колонок для Excel
            df["path_to_study"] = df["path_to_study"].astype(str)
            df["study_uid"] = df["study_uid"].astype(str)
            df["series_uid"] = df["series_uid"].astype(str)
            df["probability_of_pathology"] = df["probability_of_pathology"].astype(float)
            df["pathology"] = df["pathology"].astype(int)
            df["processing_status"] = df["processing_status"].astype(str)
            df["time_of_processing"] = df["time_of_processing"].astype(float)
            # ci_95 остается object

            # Создаем путь для отчета
            reports_dir = Path("reports")
            reports_dir.mkdir(exist_ok=True)

            filename = f"batch_report_{batch.upload_date.strftime('%Y%m%d_%H%M%S')}.xlsx"
            output_path = reports_dir / filename

            # Сохраняем в Excel с фиксированной шириной колонок
            with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
                df.to_excel(writer, index=False, sheet_name="Отчет")

                # Получаем лист для настройки ширины колонок
                worksheet = writer.sheets["Отчет"]

                # Устанавливаем фиксированную ширину для каждой колонки
                column_widths = {
                    "A": 30,  # path_to_study
                    "B": 40,  # study_uid
                    "C": 40,  # series_uid
                    "D": 20,  # probability_of_pathology
                    "E": 12,  # pathology
                    "F": 15,  # processing_status
                    "G": 15,  # time_of_processing
                    "H": 20,  # ci_95
                }

                for column_letter, width in column_widths.items():
                    worksheet.column_dimensions[column_letter].width = width

            return str(output_path)

        except Exception as e:
            print(f"Ошибка при генерации отчета по батчу: {str(e)}")
            return None
