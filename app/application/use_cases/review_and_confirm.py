import logging
from typing import Optional
from app.domain.entities.invoice_item import InvoiceItem
from app.domain.entities.invoice_line_item import InvoiceLineItem
from app.domain.entities.processing_job import ProcessingJob
from app.domain.ports.job_repository import IJobRepository
from app.domain.ports.storage_port import IStoragePort
from app.domain.ports.excel_port import IExcelPort
from app.domain.ports.excel_detail_port import IExcelDetailPort
from app.domain.ports.notification_port import INotificationPort
from app.domain.value_objects.invoice_status import InvoiceStatus

logger = logging.getLogger(__name__)

class ReviewAndConfirmUseCase:
    def __init__(
        self,
        repo: IJobRepository,
        storage: IStoragePort,
        excel: IExcelPort,
        excel_detail: IExcelDetailPort,
        bucket_invoices: str,
        bucket_exports: str,
        notification: Optional[INotificationPort] = None,
    ):
        self._repo = repo
        self._storage = storage
        self._excel = excel
        self._excel_detail = excel_detail
        self._bucket_invoices = bucket_invoices
        self._bucket_exports = bucket_exports
        self._notification = notification

    async def prepare_confirm(
        self,
        job_id: str,
        updated_items: list[InvoiceItem],
        updated_line_items: list[InvoiceLineItem],
    ) -> ProcessingJob:
        """Saves review data and sets status to CONFIRMING. (Fast)"""
        logger.info(f"[ReviewAndConfirm] Preparing confirmation for job {job_id}")
        logger.debug(f"[ReviewAndConfirm] Updated {len(updated_items)} items and {len(updated_line_items)} line items")

        await self._repo.update_items(job_id, updated_items)
        logger.debug(f"[ReviewAndConfirm] Saved updated items to repository")

        await self._repo.update_line_items(job_id, updated_line_items)
        logger.debug(f"[ReviewAndConfirm] Saved updated line items to repository")

        await self._repo.update_status(job_id, InvoiceStatus.CONFIRMING)
        job = await self._repo.get(job_id)
        job.status = InvoiceStatus.CONFIRMING

        logger.info(f"[ReviewAndConfirm] Job {job_id} status set to CONFIRMING")
        return job

    async def finalize_confirm(
        self,
        job_id: str,
        updated_items: list[InvoiceItem],
        updated_line_items: list[InvoiceLineItem],
    ):
        """All heavy lifting runs in background: save items + Excel + Storage."""
        import asyncio
        import os
        import traceback

        logger.info(f"[ReviewAndConfirm] Starting background finalization for job {job_id}")
        logger.debug(f"[ReviewAndConfirm] Finalizing with {len(updated_items)} items and {len(updated_line_items)} line items")

        try:
            job = await self._repo.get(job_id)
            if not job:
                logger.error(f"[ReviewAndConfirm] Job {job_id} not found")
                return

            # Save edited items to DB (moved here from prepare_confirm)
            logger.debug(f"[ReviewAndConfirm] Updating items and line items in database")
            await self._repo.update_items(job_id, updated_items)
            await self._repo.update_line_items(job_id, updated_line_items)
            logger.debug(f"[ReviewAndConfirm] Items and line items updated")

            first = updated_items[0]
            year, month = first.invoice_date.year, first.invoice_date.month
            customer = first.seller_name.replace("/", "-").replace(" ", "_")[:50]
            logger.debug(f"[ReviewAndConfirm] Processing for {year}/{month} - Customer: {customer}")

            # Đọc dữ liệu các file tạm - Offload to thread to avoid blocking loop
            files_to_upload = []
            async def _prepare_upload(p_path, p_ext):
                if not p_path: return None
                def _read():
                    if os.path.exists(p_path):
                        with open(p_path, "rb") as f:
                            return f.read()
                    return None
                p_data = await asyncio.to_thread(_read)
                if not p_data: return None

                p_key = f"{year}/{month:02d}/{customer}/{first.invoice_number}.{p_ext}"
                p_ctype = "application/pdf" if p_ext == "pdf" else "application/xml"
                logger.debug(f"[ReviewAndConfirm] Prepared upload: {p_key} ({len(p_data)} bytes)")
                return {"key": p_key, "data": p_data, "ctype": p_ctype, "local_path": p_path}

            # Primary file
            logger.debug(f"[ReviewAndConfirm] Preparing primary file from {job.pending_file_path}")
            primary_ext = job.filename.rsplit(".", 1)[-1].lower()
            res = await _prepare_upload(job.pending_file_path, primary_ext)
            if res: files_to_upload.append(res)

            # Paired PDF (only if primary is XML)
            if job.pending_pdf_path:
                logger.debug(f"[ReviewAndConfirm] Preparing paired PDF from {job.pending_pdf_path}")
                res_pdf = await _prepare_upload(job.pending_pdf_path, "pdf")
                if res_pdf: files_to_upload.append(res_pdf)

            logger.info(f"[ReviewAndConfirm] Uploading {len(files_to_upload)} files and generating Excel reports")

            # Thực thi song song các tác vụ nặng
            tasks = []
            for f in files_to_upload:
                logger.debug(f"[ReviewAndConfirm] Queueing upload for {f['key']}")
                tasks.append(self._storage.upload_file(self._bucket_invoices, f["key"], f["data"], f["ctype"]))

            logger.debug(f"[ReviewAndConfirm] Queueing aggregate Excel generation")
            tasks.append(self._process_aggregate_excel(year, month, updated_items))

            logger.debug(f"[ReviewAndConfirm] Queueing detailed Excel generation")
            tasks.append(self._process_detailed_excel(year, month, updated_line_items))

            logger.debug(f"[ReviewAndConfirm] Running {len(tasks)} parallel tasks")
            await asyncio.gather(*tasks)
            logger.info(f"[ReviewAndConfirm] All parallel tasks completed")

            # Dọn dẹp & Cập nhật paths
            logger.debug(f"[ReviewAndConfirm] Cleaning up temporary files and updating repository")
            for f in files_to_upload:
                await self._repo.add_source_path(job_id, f["key"])
                def _del(lp):
                    if os.path.exists(lp): os.unlink(lp)
                await asyncio.to_thread(_del, f["local_path"])
                logger.debug(f"[ReviewAndConfirm] Deleted temporary file: {f['local_path']}")

            await self._repo.update_status(job_id, InvoiceStatus.CONFIRMED)
            logger.info(f"[ReviewAndConfirm] Job {job_id} successfully confirmed and finalized")
            if self._notification:
                try:
                    first = updated_items[0] if updated_items else None
                    seller_name = first.seller_name if first else ""
                    invoice_number = first.invoice_number if first else ""
                    await self._notification.notify_confirmed(job_id, job.filename, seller_name, invoice_number)
                except Exception as notify_exc:
                    logger.warning(f"[ReviewAndConfirm] Notification failed for job {job_id}: {notify_exc}")

        except Exception as e:
            error_msg = f"Background confirmation failed: {str(e)}"
            logger.error(f"[ReviewAndConfirm] Job {job_id} finalization failed: {error_msg}\n{traceback.format_exc()}")
            await self._repo.update_status(job_id, InvoiceStatus.FAILED, error=error_msg)

    async def _process_aggregate_excel(self, year, month, items):
        xls_key = f"{year}/{month:02d}/Bang_ke_thue_{year}_{month:02d}.xlsx"
        logger.debug(f"[ReviewAndConfirm] Processing aggregate Excel: {xls_key} with {len(items)} items")

        try:
            logger.debug(f"[ReviewAndConfirm] Downloading existing aggregate Excel")
            existing_xls = await self._storage.download_file(self._bucket_exports, xls_key)
            logger.debug(f"[ReviewAndConfirm] Downloaded existing aggregate Excel ({len(existing_xls)} bytes)")
        except Exception as e:
            logger.debug(f"[ReviewAndConfirm] No existing aggregate Excel found, creating new: {e}")
            existing_xls = b""

        logger.debug(f"[ReviewAndConfirm] Appending {len(items)} rows to aggregate Excel")
        _, xls_bytes = await self._excel.append_rows(items, year, month, existing_xls)
        logger.debug(f"[ReviewAndConfirm] Generated aggregate Excel ({len(xls_bytes)} bytes)")

        logger.debug(f"[ReviewAndConfirm] Uploading aggregate Excel to storage")
        await self._storage.upload_file(
            self._bucket_exports, xls_key, xls_bytes,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        logger.info(f"[ReviewAndConfirm] Aggregate Excel uploaded: {xls_key}")

    async def _process_detailed_excel(self, year, month, line_items):
        detail_key = f"{year}/{month:02d}/Chi_tiet_hoa_don_T{month}_{year}.xlsx"
        logger.debug(f"[ReviewAndConfirm] Processing detailed Excel: {detail_key} with {len(line_items)} line items")

        try:
            logger.debug(f"[ReviewAndConfirm] Downloading existing detailed Excel")
            existing_detail = await self._storage.download_file(self._bucket_exports, detail_key)
            logger.debug(f"[ReviewAndConfirm] Downloaded existing detailed Excel ({len(existing_detail)} bytes)")
        except Exception as e:
            logger.debug(f"[ReviewAndConfirm] No existing detailed Excel found, creating new: {e}")
            existing_detail = b""

        logger.debug(f"[ReviewAndConfirm] Appending {len(line_items)} rows to detailed Excel")
        _, detail_bytes = await self._excel_detail.append_rows(
            line_items, year, month, existing_detail
        )
        logger.debug(f"[ReviewAndConfirm] Generated detailed Excel ({len(detail_bytes)} bytes)")

        logger.debug(f"[ReviewAndConfirm] Uploading detailed Excel to storage")
        await self._storage.upload_file(
            self._bucket_exports, detail_key, detail_bytes,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        logger.info(f"[ReviewAndConfirm] Detailed Excel uploaded: {detail_key}")

    async def reject(self, job_id: str) -> ProcessingJob:
        logger.info(f"[ReviewAndConfirm] Rejecting job {job_id}")
        job = await self._repo.get(job_id)
        await self._repo.update_status(job_id, InvoiceStatus.REJECTED)
        job.status = InvoiceStatus.REJECTED
        logger.info(f"[ReviewAndConfirm] Job {job_id} marked as REJECTED")
        if self._notification:
            try:
                first = job.extracted_items[0] if job.extracted_items else None
                seller_name = first.seller_name if first else ""
                invoice_number = first.invoice_number if first else ""
                await self._notification.notify_rejected(job_id, job.filename, seller_name, invoice_number)
            except Exception as notify_exc:
                logger.warning(f"[ReviewAndConfirm] Notification failed for job {job_id}: {notify_exc}")
        return job