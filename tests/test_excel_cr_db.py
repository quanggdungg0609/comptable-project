import json
import pytest
import asyncio
import aiosqlite
from datetime import datetime
from app.core.database import init_db, get_db, close_db
from app.domain.entities.excel_cr_session import ExcelCrSession
from app.infrastructure.repositories.sqlite_excel_cr_repo import SQLiteExcelCrRepository
@pytest.mark.asyncio
async def test_excel_cr_sessions_table_exists(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("DATABASE_PATH", db_path)

    # Reset singleton
    import app.core.database as db_module
    db_module._db_connection = None

    await init_db()
    db = await get_db()
    async with db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='excel_cr_sessions'"
    ) as cur:
        row = await cur.fetchone()
    assert row is not None, "excel_cr_sessions table must exist"
    await close_db()
    db_module._db_connection = None

@pytest.mark.asyncio
async def test_session_save_and_get(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test2.db")
    monkeypatch.setenv("DATABASE_PATH", db_path)
    import app.core.database as db_module
    db_module._db_connection = None

    await init_db()
    db = await get_db()
    repo = SQLiteExcelCrRepository(db)

    session = ExcelCrSession()
    session.source_file_key = "excel-cr/uploads/abc/source.csv"
    await repo.save(session)

    loaded = await repo.get(session.id)
    assert loaded is not None
    assert loaded.source_file_key == "excel-cr/uploads/abc/source.csv"
    assert loaded.status == "pending"

    await close_db()
    db_module._db_connection = None