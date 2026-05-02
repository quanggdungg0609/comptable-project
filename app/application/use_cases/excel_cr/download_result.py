# app/application/use_cases/excel_cr/download_result.py
import logging
from dataclasses import fields as dc_fields
from app.domain.ports.storage_port import IStoragePort
from app.domain.ports.excel_cr_rule_port import IExcelCrRulePort
from app.infrastructure.repositories.sqlite_excel_cr_repo import SQLiteExcelCrRepository
from app.infrastructure.excel.excel_cr_writer import ExcelCrWriter
from app.application.use_cases.excel_cr.aggregate_and_match import AggregatedRow

logger = logging.getLogger(__name__)

BUCKET = "excel-cr"


class DownloadResultUseCase:
    def __init__(self, repo: SQLiteExcelCrRepository, storage: IStoragePort):
        self._repo = repo
        self._storage = storage

    async def execute(self, session_id: str) -> bytes:
        session = await self._repo.get(session_id)
        if session is None:
            raise ValueError(f"Session {session_id} not found")
        if not session.template_key:
            raise ValueError("No template uploaded for this session")
        if not session.match_results:
            raise ValueError("No aggregated data — run aggregate first")

        template_bytes = await self._storage.download_file(BUCKET, session.template_key)

        rows = [
            AggregatedRow(
                thang=r["thang"],
                dien_giai=r["dien_giai"],
                khoan_muc=r["khoan_muc"],
                so_tien=r["so_tien"],
                chi_tieu=r.get("chi_tieu"),
                match_tier=r.get("match_tier"),
            )
            for r in session.match_results
            if r.get("chi_tieu")
        ]

        output_bytes = ExcelCrWriter.write(template_bytes, rows)

        result_key = f"results/{session_id}/output.xlsx"
        await self._storage.upload_file(BUCKET, result_key, output_bytes,
                                         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        logger.info("Excel-CR result stored at %s", result_key)
        return output_bytes
