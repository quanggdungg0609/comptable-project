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
                return {"key": p_key, "data": p_data, "ctype": p_ctype, "local_path": p_path}

            # Primary file
            primary_ext = job.filename.rsplit(".", 1)[-1].lower()
            res = await _prepare_upload(job.pending_file_path, primary_ext)
            if res: files_to_upload.append(res)
            
            # Paired PDF (only if primary is XML)
            if job.pending_pdf_path:
                res_pdf = await _prepare_upload(job.pending_pdf_path, "pdf")
                if res_pdf: files_to_upload.append(res_pdf)

            # Thực thi song song các tác vụ nặng
            tasks = []
            for f in files_to_upload:
                tasks.append(self._storage.upload_file(self._bucket_invoices, f["key"], f["data"], f["ctype"]))
            
            tasks.append(self._process_aggregate_excel(year, month, updated_items))
            tasks.append(self._process_detailed_excel(year, month, updated_line_items))
            
            await asyncio.gather(*tasks)

            # Dọn dẹp & Cập nhật paths
            for f in files_to_upload:
                await self._repo.add_source_path(job_id, f["key"])
                def _del(lp):
                    if os.path.exists(lp): os.unlink(lp)
                await asyncio.to_thread(_del, f["local_path"])
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