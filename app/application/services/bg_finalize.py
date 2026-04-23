"""Shared background finalizer for invoice confirmation.

Reuses cached singletons (storage + excel writers) and a persistent
background SQLite connection so each confirm does NOT re-parse XLSX
templates, re-build boto3 clients, or open a new DB connection on the
event loop.
"""
import asyncio
import logging
import traceback

from app.application.use_cases.review_and_confirm import ReviewAndConfirmUseCase
from app.core.config import get_settings
from app.core.database import get_bg_db
from app.core.dependencies import (
    get_excel_detail_singleton,
    get_excel_singleton,
    get_storage_singleton,
)
from app.infrastructure.repositories.sqlite_job_repo import SQLiteJobRepository

logger = logging.getLogger(__name__)

_bg_uc: ReviewAndConfirmUseCase | None = None
_bg_lock = asyncio.Lock()


async def _get_bg_uc() -> ReviewAndConfirmUseCase:
    global _bg_uc
    if _bg_uc is None:
        async with _bg_lock:
            if _bg_uc is None:
                settings = get_settings()
                db = await get_bg_db()
                _bg_uc = ReviewAndConfirmUseCase(
                    repo=SQLiteJobRepository(db),
                    storage=get_storage_singleton(),
                    excel=get_excel_singleton(),
                    excel_detail=get_excel_detail_singleton(),
                    bucket_invoices=settings.rustfs_bucket_invoices,
                    bucket_exports=settings.rustfs_bucket_exports,
                )
    return _bg_uc


def spawn_finalize(job_id: str, items, line_items) -> asyncio.Task:
    """Fire-and-forget background finalization.
    Returns the created Task (callers may ignore it)."""

    async def _run():
        try:
            uc = await _get_bg_uc()
            await uc.finalize_confirm(
                job_id=job_id,
                updated_items=items,
                updated_line_items=line_items,
            )
        except Exception as e:
            logger.error(f"[BgFinalize] Job {job_id} failed: {e}\n{traceback.format_exc()}")

    return asyncio.create_task(_run())


async def prewarm() -> None:
    """Call at startup so the first real confirm pays no init cost."""
    get_storage_singleton()
    get_excel_singleton()
    get_excel_detail_singleton()
    await get_bg_db()
    await _get_bg_uc()

    # Pre-spawn ProcessPoolExecutor workers so the first Excel append
    # doesn't pay the (slow, macOS 'spawn') cold-start cost.
    try:
        from app.infrastructure.excel import openpyxl_writer as _ow
        from app.infrastructure.excel import openpyxl_detail_writer as _od

        loop = asyncio.get_running_loop()
        await asyncio.gather(
            loop.run_in_executor(_ow._process_pool, int, 0),
            loop.run_in_executor(_od._process_pool, int, 0),
        )
    except Exception as e:
        logger.warning(f"[BgFinalize] Process pool prewarm failed (non-fatal): {e}")
