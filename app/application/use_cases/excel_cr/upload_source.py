# app/application/use_cases/excel_cr/upload_source.py
import logging
from app.domain.entities.excel_cr_session import ExcelCrSession
from app.domain.ports.storage_port import IStoragePort
from app.infrastructure.parsers.excel_cr_source_parser import parse_source_file
from app.infrastructure.repositories.sqlite_excel_cr_repo import SQLiteExcelCrRepository

logger = logging.getLogger(__name__)

BUCKET = "excel-cr"


class UploadSourceUseCase:
    def __init__(self, repo: SQLiteExcelCrRepository, storage: IStoragePort):
        self._repo = repo
        self._storage = storage

    async def execute(self, filename: str, file_data: bytes) -> ExcelCrSession:
        # Validate parseable before storing
        parse_source_file(file_data, filename)

        session = ExcelCrSession()
        key = f"uploads/{session.id}/source_{filename}"
        await self._storage.upload_file(BUCKET, key, file_data, "application/octet-stream")
        session.source_file_key = key
        await self._repo.save(session)
        logger.info("Excel-CR session %s created, source stored at %s", session.id, key)
        return session
