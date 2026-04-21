import asyncio
import logging
from typing import Optional
from app.domain.entities.processing_job import ProcessingJob
from app.domain.ports.job_repository import IJobRepository
from app.domain.ports.llm_port import ILLMPort
from app.domain.ports.notification_port import INotificationPort
from app.domain.value_objects.file_type import FileType
from app.domain.value_objects.invoice_status import InvoiceStatus
from app.infrastructure.parsers.xml_parser import extract_text_from_xml
from app.infrastructure.parsers.pdf_parser import extract_text_from_pdf

logger = logging.getLogger(__name__)

class ProcessInvoiceUseCase:
    def __init__(
        self,
        repo: IJobRepository,
        llm: ILLMPort,
        notification: Optional[INotificationPort] = None,
    ):
        self._repo = repo
        self._llm = llm
        self._notification = notification

    async def execute(
        self,
        filename: str,
        file_data: bytes,
        paired_pdf: bytes | None = None,
    ) -> ProcessingJob:
        file_type = FileType.from_filename(filename)
        job = ProcessingJob.create(filename=filename, file_type=file_type)
        await self._repo.save(job)
        await self._repo.update_status(job.id, InvoiceStatus.PROCESSING)

        try:
            # Save raw file to data/pending/ for later RustFS archiving on confirm
            import os
            pending_dir = "data/pending"
            os.makedirs(pending_dir, exist_ok=True)
            ext = filename.rsplit(".", 1)[-1].lower()
            pending_path = f"{pending_dir}/{job.id}.{ext}"
            with open(pending_path, "wb") as f:
                f.write(file_data)
            await self._repo.update_pending_file_path(job.id, pending_path)
            job.pending_file_path = pending_path

            if file_type == FileType.XML:
                content = extract_text_from_xml(file_data)
            else:
                content = await asyncio.to_thread(extract_text_from_pdf, file_data)

            items = await self._llm.extract_invoice(content)
            job.extracted_items = items
            await self._repo.save_items(job.id, items)
            await self._repo.update_status(job.id, InvoiceStatus.AWAITING_REVIEW)
            job.status = InvoiceStatus.AWAITING_REVIEW

            # Notify staff — failure here must not fail the job
            if self._notification:
                try:
                    await self._notification.notify_new_invoice(job.id, filename)
                except Exception as notify_exc:
                    logger.warning("Notification failed for job %s: %s", job.id, notify_exc)

        except Exception as exc:
            error_msg = str(exc)
            await self._repo.update_status(job.id, InvoiceStatus.FAILED, error=error_msg)
            job.status = InvoiceStatus.FAILED
            job.error = error_msg

        return job