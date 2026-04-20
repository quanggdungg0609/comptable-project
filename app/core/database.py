import aiosqlite
from pathlib import Path
from app.core.config import get_settings

CREATE_JOBS_TABLE = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    file_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING',
    created_at TEXT NOT NULL,
    error TEXT,
    source_paths TEXT DEFAULT '[]',
    pending_file_path TEXT
)
"""

CREATE_INVOICE_ITEMS_TABLE = """
CREATE TABLE IF NOT EXISTS invoice_items (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES jobs(id),
    invoice_symbol TEXT DEFAULT '',
    invoice_number TEXT DEFAULT '',
    invoice_date TEXT DEFAULT '',
    seller_name TEXT DEFAULT '',
    seller_tax_code TEXT DEFAULT '',
    description TEXT DEFAULT '',
    price_before_tax TEXT DEFAULT '0',
    tax_rate TEXT DEFAULT '0',
    price_after_tax TEXT DEFAULT '0'
)
"""

async def get_db() -> aiosqlite.Connection:
    settings = get_settings()
    Path(settings.database_path).parent.mkdir(parents=True, exist_ok=True)
    db = await aiosqlite.connect(settings.database_path)
    db.row_factory = aiosqlite.Row
    return db

async def init_db() -> None:
    db = await get_db()
    try:
        await db.execute(CREATE_JOBS_TABLE)
        await db.execute(CREATE_INVOICE_ITEMS_TABLE)
        await db.commit()
    finally:
        await db.close()
