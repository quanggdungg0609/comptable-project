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
        existing_job_id: str | None = None,
    ) -> ProcessingJob:
        file_type = FileType.from_filename(filename)

        if existing_job_id:
            job = await self._repo.get(existing_job_id)
            await self._repo.update_items(job.id, [])
            await self._repo.update_line_items(job.id, [])
            job.extracted_items = []
            job.extracted_line_items = []
            job.error = None
        else:
            job = ProcessingJob.create(filename=filename, file_type=file_type)
            await self._repo.save(job)

        logger.info(f"[ProcessInvoice] Starting processing for job {job.id}: {filename} ({file_type.value})")
        logger.debug(f"[ProcessInvoice] File size: {len(file_data)} bytes, Paired PDF: {paired_pdf is not None}")

        await self._repo.update_status(job.id, InvoiceStatus.PROCESSING)
        logger.info(f"[ProcessInvoice] Job {job.id} status set to PROCESSING")

        try:
            import os
            pending_dir = "data/pending"
            os.makedirs(pending_dir, exist_ok=True)
            ext = filename.rsplit(".", 1)[-1].lower()
            pending_path = f"{pending_dir}/{job.id}.{ext}"

            logger.debug(f"[ProcessInvoice] Saving file to {pending_path}")
            with open(pending_path, "wb") as f:
                f.write(file_data)
            await self._repo.update_pending_file_path(job.id, pending_path)
            job.pending_file_path = pending_path
            logger.info(f"[ProcessInvoice] File saved: {pending_path}")

            if paired_pdf:
                pending_pdf_path = f"{pending_dir}/{job.id}_paired.pdf"
                logger.debug(f"[ProcessInvoice] Saving paired PDF to {pending_pdf_path}")
                with open(pending_pdf_path, "wb") as f:
                    f.write(paired_pdf)
                await self._repo.update_pending_pdf_path(job.id, pending_pdf_path)
                job.pending_pdf_path = pending_pdf_path
                logger.info(f"[ProcessInvoice] Paired PDF saved: {pending_pdf_path}")

            logger.debug(f"[ProcessInvoice] Extracting content from {file_type.value} file")
            if file_type == FileType.XML:
                content = extract_text_from_xml(file_data)
                line_items = extract_line_items_from_xml(file_data)
                logger.info(f"[ProcessInvoice] Extracted {len(line_items)} line items from XML")
            else:
                content = await asyncio.to_thread(extract_text_from_pdf, file_data)
                line_items = []
                logger.info(f"[ProcessInvoice] Extracted text from PDF")

            logger.debug(f"[ProcessInvoice] Calling LLM to extract invoice data")
            items, llm_line_items = await self._llm.extract_invoice(content)
            logger.info(f"[ProcessInvoice] LLM extracted {len(items)} invoice items")

            if file_type != FileType.XML:
                line_items = llm_line_items
                logger.info(f"[ProcessInvoice] Using LLM-extracted line items ({len(line_items)} items)")

            job.extracted_items = items
            job.extracted_line_items = line_items
            await self._repo.save_items(job.id, items)
            logger.debug(f"[ProcessInvoice] Saved {len(items)} items to repository")

            # Duplicate check — soft fail: DB error must not block the job
            if items:
                try:
                    item = items[0]
                    logger.debug(f"[ProcessInvoice] Checking for duplicates: {item.invoice_symbol}/{item.invoice_number} from {item.seller_tax_code}")
                    dup = await self._repo.find_duplicate(
                        item.invoice_symbol, item.invoice_number, item.seller_tax_code,
                        exclude_job_id=job.id,
                    )
                    if dup:
                        logger.warning(f"[ProcessInvoice] Found duplicate! Job {job.id} is duplicate of {dup.id}")
                        await self._repo.update_duplicate_of(job.id, dup.id)
                        await self._repo.update_status(job.id, InvoiceStatus.DUPLICATE)
                        job.status = InvoiceStatus.DUPLICATE
                        job.duplicate_of = dup.id
                        logger.info(f"[ProcessInvoice] Job {job.id} marked as DUPLICATE")
                        return job
                    else:
                        logger.debug(f"[ProcessInvoice] No duplicate found")
                except Exception as dup_exc:
                    logger.warning(f"[ProcessInvoice] Duplicate check failed for job {job.id}: {dup_exc}")

            await self._repo.save_line_items(job.id, line_items)
            logger.debug(f"[ProcessInvoice] Saved {len(line_items)} line items to repository")

            await self._repo.update_status(job.id, InvoiceStatus.AWAITING_REVIEW)
            job.status = InvoiceStatus.AWAITING_REVIEW
            logger.info(f"[ProcessInvoice] Job {job.id} status set to AWAITING_REVIEW")

            if self._notification:
                try:
                    logger.debug(f"[ProcessInvoice] Sending notification for job {job.id}")
                    first = items[0] if items else None
                    seller_name = first.seller_name if first else ""
                    invoice_number = first.invoice_number if first else ""
                    await self._notification.notify_new_invoice(job.id, filename, seller_name, invoice_number)
                    logger.info(f"[ProcessInvoice] Notification sent for job {job.id}")
                except Exception as notify_exc:
                    logger.warning(f"[ProcessInvoice] Notification failed for job {job.id}: {notify_exc}")

            logger.info(f"[ProcessInvoice] Successfully completed job {job.id}")

        except Exception as exc:
            import traceback
            error_msg = str(exc) or repr(exc)
            logger.error(f"[ProcessInvoice] Job {job.id} failed: {error_msg}\n{traceback.format_exc()}")
            await self._repo.update_status(job.id, InvoiceStatus.FAILED, error=error_msg)
            job.status = InvoiceStatus.FAILED
            job.error = error_msg

        return job
