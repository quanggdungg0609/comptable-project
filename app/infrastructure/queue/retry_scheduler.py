import asyncio
import logging
import os
from app.domain.ports.job_repository import IJobRepository
from app.application.use_cases.process_invoice import ProcessInvoiceUseCase

logger = logging.getLogger(__name__)

_MAX_AUTO_RETRIES = 3
_RETRY_INTERVAL_SECONDS = 300  # 5 minutes


class RetryScheduler:
    def __init__(self, repo: IJobRepository, process_use_case: ProcessInvoiceUseCase):
        self._repo = repo
        self._process_use_case = process_use_case
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._loop())
        logger.info("[RetryScheduler] Started (interval: %ds, max retries: %d)", _RETRY_INTERVAL_SECONDS, _MAX_AUTO_RETRIES)

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("[RetryScheduler] Stopped")

    async def _loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(_RETRY_INTERVAL_SECONDS)
                await self._run_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("[RetryScheduler] Unexpected error: %s", exc, exc_info=True)

    async def _run_once(self) -> None:
        retryable = await self._repo.list_retryable(max_retry_count=_MAX_AUTO_RETRIES)
        if not retryable:
            return

        logger.info("[RetryScheduler] Found %d FAILED job(s) to retry", len(retryable))
        for job in retryable:
            await self._retry_job(job)

    async def _retry_job(self, job) -> None:
        # Re-check status to guard against race with manual retry
        current = await self._repo.get(job.id)
        if not current or current.status.value != "FAILED":
            logger.info("[RetryScheduler] Skipping job %s — status is now %s", job.id, current.status if current else "gone")
            return

        path = job.pending_file_path
        if not path or not os.path.exists(path):
            logger.warning("[RetryScheduler] Skipping job %s — pending file missing: %s", job.id, path)
            await self._repo.increment_retry_count(job.id)
            return

        try:
            file_data = open(path, "rb").read()
        except OSError as exc:
            logger.error("[RetryScheduler] Cannot read file for job %s: %s", job.id, exc)
            await self._repo.increment_retry_count(job.id)
            return

        paired_bytes: bytes | None = None
        if job.pending_pdf_path and os.path.exists(job.pending_pdf_path):
            try:
                paired_bytes = open(job.pending_pdf_path, "rb").read()
            except OSError:
                pass

        await self._repo.increment_retry_count(job.id)
        logger.info("[RetryScheduler] Retrying job %s (attempt %d/%d): %s", job.id, job.retry_count + 1, _MAX_AUTO_RETRIES, job.filename)

        try:
            result = await self._process_use_case.execute(
                filename=job.filename,
                file_data=file_data,
                paired_pdf=paired_bytes,
                existing_job_id=job.id,
            )
            logger.info("[RetryScheduler] Retry for job %s completed (status: %s)", job.id, result.status)
        except Exception as exc:
            logger.error("[RetryScheduler] Retry for job %s failed: %s", job.id, exc, exc_info=True)
