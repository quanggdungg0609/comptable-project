import asyncio
import logging
from typing import Optional
from app.domain.entities.processing_job import ProcessingJob
from app.domain.ports.job_repository import IJobRepository
from app.domain.ports.llm_port import ILLMPort
from app.domain.ports.notification_port import INotificationPort
from app.domain.value_objects.file_type import FileType
from app.domain.value_objects.invoice_status import InvoiceStatus
from app.infrastructure.parsers.xml_parser import extract_text_from_xml, extract_line_items_from_xml
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
            import os
            pending_dir = "data/pending"
            os.makedirs(pending_dir, exist_ok=True)
            ext = filename.rsplit(".", 1)[-1].lower()
            pending_path = f"{pending_dir}/{job.id}.{ext}"
            with open(pending_path, "wb") as f:
                f.write(file_data)
            await self._repo.update_pending_file_path(job.id, pending_path)
            job.pending_file_path = pending_path

            if paired_pdf:
                pending_pdf_path = f"{pending_dir}/{job.id}_paired.pdf"
                with open(pending_pdf_path, "wb") as f:
                    f.write(paired_pdf)
                await self._repo.update_pending_pdf_path(job.id, pending_pdf_path)
                job.pending_pdf_path = pending_pdf_path

            if file_type == FileType.XML:
                content = extract_text_from_xml(file_data)
                line_items = extract_line_items_from_xml(file_data)
            else:
                content = await asyncio.to_thread(extract_text_from_pdf, file_data)
                line_items = []

            items, llm_line_items = await self._llm.extract_invoice(content)

            if file_type != FileType.XML:
                line_items = llm_line_items

            job.extracted_items = items
            job.extracted_line_items = line_items
            await self._repo.save_items(job.id, items)

            # Duplicate check — soft fail: DB error must not block the job
            if items:
                try:
                    item = items[0]
                    dup = await self._repo.find_duplicate(
                        item.invoice_symbol, item.invoice_number, item.seller_tax_code,
                        exclude_job_id=job.id,
                    )
                    if dup:
                        await self._repo.update_duplicate_of(job.id, dup.id)
                        await self._repo.update_status(job.id, InvoiceStatus.DUPLICATE)
                        job.status = InvoiceStatus.DUPLICATE
                        job.duplicate_of = dup.id
                        return job
                except Exception as dup_exc:
                    logger.warning("Duplicate check failed for job %s: %s", job.id, dup_exc)

            await self._repo.save_line_items(job.id, line_items)
            await self._repo.update_status(job.id, InvoiceStatus.AWAITING_REVIEW)
            job.status = InvoiceStatus.AWAITING_REVIEW

            if self._notification:
                try:
                    await self._notification.notify_new_invoice(job.id, filename)
                except Exception as notify_exc:
                    logger.warning("Notification failed for job %s: %s", job.id, notify_exc)

        except Exception as exc:
            import traceback
            error_msg = str(exc) or repr(exc)
            logger.error("Job %s failed: %s\n%s", job.id, error_msg, traceback.format_exc())
            await self._repo.update_status(job.id, InvoiceStatus.FAILED, error=error_msg)
            job.status = InvoiceStatus.FAILED
            job.error = error_msg

        return job
