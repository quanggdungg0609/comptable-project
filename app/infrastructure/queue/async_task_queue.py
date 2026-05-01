import asyncio
import logging
from app.domain.ports.task_queue_port import ITaskQueue
from app.application.use_cases.process_invoice import ProcessInvoiceUseCase

logger = logging.getLogger(__name__)

_RATE_LIMIT_SIGNALS = ("429", "503", "quota", "rate limit", "resource_exhausted", "too many requests")
_MAX_REQUEUE = 5
_TASK_DELAY = 4        # seconds between tasks (stay under 15 RPM free tier)
_RATE_LIMIT_DELAY = 120  # seconds to wait after rate limit before requeue


class AsyncTaskQueue(ITaskQueue):
    def __init__(self):
        self._queue = asyncio.Queue()
        self._use_case = None
        self._workers = []
        self._running = False

    async def enqueue(self, filename: str, file_data: bytes, paired_pdf: bytes | None = None) -> str:
        await self._queue.put({
            "filename": filename,
            "file_data": file_data,
            "paired_pdf": paired_pdf,
            "_requeue_count": 0,
        })
        logger.info(f"Enqueued task for: {filename}")
        return "queued"

    async def start_workers(self, process_use_case: ProcessInvoiceUseCase, num_workers: int = 1):
        if self._running:
            return
        self._use_case = process_use_case
        self._running = True
        for i in range(num_workers):
            task = asyncio.create_task(self._worker_loop(i))
            self._workers.append(task)
        logger.info(f"Started {num_workers} background workers for invoice processing.")

    async def stop_workers(self):
        self._running = False
        for _ in range(len(self._workers)):
            await self._queue.put(None)
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers = []
        logger.info("Stopped background workers.")

    async def _worker_loop(self, worker_id: int):
        while self._running:
            task_data = await self._queue.get()
            if task_data is None:
                self._queue.task_done()
                break

            filename = task_data["filename"]
            requeue_count = task_data.get("_requeue_count", 0)

            try:
                logger.info(f"Worker-{worker_id} processing: {filename} (attempt {requeue_count + 1})")
                job = await self._use_case.execute(
                    filename=filename,
                    file_data=task_data["file_data"],
                    paired_pdf=task_data["paired_pdf"],
                )

                error_lower = (job.error or "").lower()
                is_rate_limited = job.status.value == "FAILED" and any(sig in error_lower for sig in _RATE_LIMIT_SIGNALS)

                if is_rate_limited and requeue_count < _MAX_REQUEUE:
                    logger.warning(
                        f"Worker-{worker_id} rate-limited on {filename} "
                        f"(attempt {requeue_count + 1}/{_MAX_REQUEUE}). "
                        f"Sleeping {_RATE_LIMIT_DELAY}s then requeuing."
                    )
                    await asyncio.sleep(_RATE_LIMIT_DELAY)
                    task_data["_requeue_count"] = requeue_count + 1
                    await self._queue.put(task_data)
                elif is_rate_limited:
                    logger.error(f"Worker-{worker_id} gave up on {filename} after {_MAX_REQUEUE} rate-limit retries.")
                else:
                    logger.info(f"Worker-{worker_id} finished: {filename} → {job.status.value}")
                    await asyncio.sleep(_TASK_DELAY)

            except Exception as e:
                logger.error(f"Worker-{worker_id} error processing {filename}: {e}", exc_info=True)
            finally:
                self._queue.task_done()
