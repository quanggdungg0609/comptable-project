import asyncio
import logging
from typing import Dict, Any, List
from app.domain.ports.task_queue_port import ITaskQueue
from app.application.use_cases.process_invoice import ProcessInvoiceUseCase

logger = logging.getLogger(__name__)

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
            "paired_pdf": paired_pdf
        })
        logger.info(f"Enqueued task for: {filename}")
        return "queued"

    async def start_workers(self, process_use_case: ProcessInvoiceUseCase, num_workers: int = 2):
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
        # Put sentinel values to stop workers
        for _ in range(len(self._workers)):
            await self._queue.put(None)
        
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers = []
        logger.info("Stopped background workers.")

    async def _worker_loop(self, worker_id: int):
        while self._running:
            task_data = await self._queue.get()
            if task_data is None: # Sentinel
                self._queue.task_done()
                break
            
            try:
                logger.info(f"Worker-{worker_id} processing: {task_data['filename']}")
                await self._use_case.execute(
                    filename=task_data["filename"],
                    file_data=task_data["file_data"],
                    paired_pdf=task_data["paired_pdf"]
                )
                logger.info(f"Worker-{worker_id} finished: {task_data['filename']}")
            except Exception as e:
                logger.error(f"Worker-{worker_id} error processing {task_data['filename']}: {e}", exc_info=True)
            finally:
                self._queue.task_done()
