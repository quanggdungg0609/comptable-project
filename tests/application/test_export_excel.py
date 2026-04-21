import pytest
from unittest.mock import AsyncMock
from app.application.use_cases.export_excel import ExportExcelUseCase

async def test_export_returns_bytes_and_filename():
    storage = AsyncMock()
    storage.download_file.return_value = b"xlsx_bytes"
    uc = ExportExcelUseCase(storage=storage, bucket_exports="exports")
    data, filename = await uc.execute(year=2026, month=3)
    assert data == b"xlsx_bytes"
    assert filename == "Bang_ke_thue_2026_03.xlsx"

async def test_export_raises_when_not_found():
    storage = AsyncMock()
    storage.download_file.side_effect = Exception("NoSuchKey")
    uc = ExportExcelUseCase(storage=storage, bucket_exports="exports")
    with pytest.raises(FileNotFoundError):
        await uc.execute(year=2026, month=3)