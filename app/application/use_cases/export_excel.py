import logging
from app.domain.ports.storage_port import IStoragePort

logger = logging.getLogger(__name__)


class ExportExcelUseCase:
    def __init__(self, storage: IStoragePort, bucket_exports: str):
        self._storage = storage
        self._bucket_exports = bucket_exports

    async def execute(self, year: int, month: int) -> tuple[bytes, str]:
        filename_only = f"Bang_ke_thue_{year}_{month:02d}.xlsx"
        storage_key = f"{year}/{month:02d}/{filename_only}"

        logger.info(f"[ExportExcel] Exporting aggregate Excel for {year}/{month:02d}")
        logger.debug(f"[ExportExcel] Storage key: {storage_key}")

        try:
            logger.debug(f"[ExportExcel] Downloading file from storage")
            data = await self._storage.download_file(self._bucket_exports, storage_key)
            logger.info(f"[ExportExcel] Successfully downloaded {filename_only} ({len(data)} bytes)")
            return data, filename_only
        except Exception as exc:
            logger.error(f"[ExportExcel] Failed to download export file for {year}/{month:02d}: {exc}")
            raise FileNotFoundError(f"No export file found for {year}/{month:02d}") from exc