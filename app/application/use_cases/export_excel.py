from app.domain.ports.storage_port import IStoragePort

class ExportExcelUseCase:
    def __init__(self, storage: IStoragePort, bucket_exports: str):
        self._storage = storage
        self._bucket_exports = bucket_exports

    async def execute(self, year: int, month: int) -> tuple[bytes, str]:
        filename = f"Bang_ke_thue_{year}_{month:02d}.xlsx"
        try:
            data = await self._storage.download_file(self._bucket_exports, filename)
        except Exception as exc:
            raise FileNotFoundError(f"No export file found for {year}/{month:02d}") from exc
        return data, filename