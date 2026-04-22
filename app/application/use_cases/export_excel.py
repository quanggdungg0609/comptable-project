from app.domain.ports.storage_port import IStoragePort

class ExportExcelUseCase:
    def __init__(self, storage: IStoragePort, bucket_exports: str):
        self._storage = storage
        self._bucket_exports = bucket_exports

    async def execute(self, year: int, month: int) -> tuple[bytes, str]:
        filename_only = f"Bang_ke_thue_{year}_{month:02d}.xlsx"
        storage_key = f"{year}/{month:02d}/{filename_only}"
        try:
            data = await self._storage.download_file(self._bucket_exports, storage_key)
        except Exception as exc:
            raise FileNotFoundError(f"No export file found for {year}/{month:02d}") from exc
        return data, filename_only