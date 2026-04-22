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

CREATE_INVOICE_LINE_ITEMS_TABLE = """
CREATE TABLE IF NOT EXISTS invoice_line_items (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES jobs(id),
    invoice_symbol TEXT DEFAULT '',
    invoice_number TEXT DEFAULT '',
    invoice_date TEXT DEFAULT '',
    seller_name TEXT DEFAULT '',
    seller_tax_code TEXT DEFAULT '',
    ten_hang_hoa TEXT DEFAULT '',
    don_vi_tinh TEXT DEFAULT '',
    so_luong TEXT DEFAULT '0',
    don_gia TEXT DEFAULT '0',
    thanh_tien TEXT DEFAULT '0',
    tax_rate TEXT DEFAULT '0',
    tax_amount TEXT DEFAULT '0'
)
"""

# Global singleton database connection
_db_connection: aiosqlite.Connection | None = None

async def get_db() -> aiosqlite.Connection:
    global _db_connection
    if _db_connection is None:
        settings = get_settings()
        Path(settings.database_path).parent.mkdir(parents=True, exist_ok=True)
        _db_connection = await aiosqlite.connect(settings.database_path)
        _db_connection.row_factory = aiosqlite.Row
    return _db_connection

async def close_db() -> None:
    global _db_connection
    if _db_connection is not None:
        await _db_connection.close()
        _db_connection = None

async def init_db() -> None:
    db = await get_db()
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA synchronous=NORMAL")
    await db.execute(CREATE_JOBS_TABLE)
    await db.execute(CREATE_INVOICE_ITEMS_TABLE)
    await db.execute(CREATE_INVOICE_LINE_ITEMS_TABLE)
    await db.commit()
