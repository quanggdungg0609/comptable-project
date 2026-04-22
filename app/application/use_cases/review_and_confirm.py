from app.domain.entities.invoice_item import InvoiceItem
from app.domain.entities.invoice_line_item import InvoiceLineItem
from app.domain.entities.processing_job import ProcessingJob
from app.domain.ports.job_repository import IJobRepository
from app.domain.ports.storage_port import IStoragePort
from app.domain.ports.excel_port import IExcelPort
from app.domain.ports.excel_detail_port import IExcelDetailPort
from app.domain.value_objects.invoice_status import InvoiceStatus

class ReviewAndConfirmUseCase:
    def __init__(
        self,
        repo: IJobRepository,
        storage: IStoragePort,
        excel: IExcelPort,
        excel_detail: IExcelDetailPort,
        bucket_invoices: str,
        bucket_exports: str,
    ):
        self._repo = repo
        self._storage = storage
        self._excel = excel
        self._excel_detail = excel_detail
        self._bucket_invoices = bucket_invoices
        self._bucket_exports = bucket_exports

    async def prepare_confirm(
        self,
        job_id: str,
        updated_items: list[InvoiceItem],
        updated_line_items: list[InvoiceLineItem],
    ) -> ProcessingJob:
        """Saves review data and sets status to CONFIRMING. (Fast)"""
        await self._repo.update_items(job_id, updated_items)
        await self._repo.update_line_items(job_id, updated_line_items)
        await self._repo.update_status(job_id, InvoiceStatus.CONFIRMING)
        job = await self._repo.get(job_id)
        job.status = InvoiceStatus.CONFIRMING
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
        import logging
        logger = logging.getLogger(__name__)

        try:
            job = await self._repo.get(job_id)
            if not job: return

            # Save edited items to DB (moved here from prepare_confirm)
            await self._repo.update_items(job_id, updated_items)
            await self._repo.update_line_items(job_id, updated_line_items)

            first = updated_items[0]
            year, month = first.invoice_date.year, first.invoice_date.month
            customer = first.seller_name.replace("/", "-").replace(" ", "_")[:50]
            ext = job.filename.rsplit(".", 1)[-1]
            storage_key = f"{year}/{month:02d}/{customer}/{first.invoice_number}.{ext}"

            # Đọc dữ liệu file tạm
            pending_path = job.pending_file_path
            file_data = b""
            if pending_path and os.path.exists(pending_path):
                with open(pending_path, "rb") as f:
                    file_data = f.read()

            # Thực thi song song các tác vụ nặng
            await asyncio.gather(
                self._storage.upload_file(
                    self._bucket_invoices, storage_key, file_data,
                    "application/pdf" if ext == "pdf" else "application/xml",
                ),
                self._process_aggregate_excel(year, month, updated_items),
                self._process_detailed_excel(year, month, updated_line_items)
            )

            # Dọn dẹp
            if pending_path and os.path.exists(pending_path):
                os.unlink(pending_path)
            
            await self._repo.add_source_path(job_id, storage_key)
            await self._repo.update_status(job_id, InvoiceStatus.CONFIRMED)
            logger.info(f"Job {job_id} successfully confirmed in background.")

        except Exception as e:
            import traceback
            error_msg = f"Background confirmation failed: {str(e)}"
            logger.error(f"Job {job_id} error: {error_msg}\n{traceback.format_exc()}")
            await self._repo.update_status(job_id, InvoiceStatus.FAILED, error=error_msg)

    async def _process_aggregate_excel(self, year, month, items):
        xls_key = f"{year}/{month:02d}/Bang_ke_thue_{year}_{month:02d}.xlsx"
        try:
            existing_xls = await self._storage.download_file(self._bucket_exports, xls_key)
        except Exception:
            existing_xls = b""
        
        _, xls_bytes = await self._excel.append_rows(items, year, month, existing_xls)
        await self._storage.upload_file(
            self._bucket_exports, xls_key, xls_bytes,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    async def _process_detailed_excel(self, year, month, line_items):
        detail_key = f"{year}/{month:02d}/Chi_tiet_hoa_don_T{month}_{year}.xlsx"
        try:
            existing_detail = await self._storage.download_file(self._bucket_exports, detail_key)
        except Exception:
            existing_detail = b""
            
        _, detail_bytes = await self._excel_detail.append_rows(
            line_items, year, month, existing_detail
        )
        await self._storage.upload_file(
            self._bucket_exports, detail_key, detail_bytes,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    async def reject(self, job_id: str) -> ProcessingJob:
        job = await self._repo.get(job_id)
        await self._repo.update_status(job_id, InvoiceStatus.REJECTED)
        job.status = InvoiceStatus.REJECTED
        return job