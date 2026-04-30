import asyncio
import pytest
import aiosqlite
from app.core.database import init_db, get_db, close_db

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