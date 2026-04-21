from app.domain.entities.invoice_item import InvoiceItem
from app.domain.entities.processing_job import ProcessingJob
from app.domain.ports.job_repository import IJobRepository
from app.domain.ports.storage_port import IStoragePort
from app.domain.ports.excel_port import IExcelPort
from app.domain.value_objects.invoice_status import InvoiceStatus

class ReviewAndConfirmUseCase:
    def __init__(
        self,
        repo: IJobRepository,
        storage: IStoragePort,
        excel: IExcelPort,
        bucket_invoices: str,
        bucket_exports: str,
    ):
        self._repo = repo
        self._storage = storage
        self._excel = excel
        self._bucket_invoices = bucket_invoices
        self._bucket_exports = bucket_exports

    async def confirm(
        self,
        job_id: str,
        updated_items: list[InvoiceItem],
    ) -> ProcessingJob:
        import os
        job = await self._repo.get(job_id)
        await self._repo.update_items(job_id, updated_items)

        # Read raw file from pending temp storage
        pending_path = job.pending_file_path
        if pending_path and os.path.exists(pending_path):
            with open(pending_path, "rb") as f:
                file_data = f.read()
        else:
            file_data = b""

        # Upload original invoice file to RustFS
        first = updated_items[0]
        year, month = first.invoice_date.year, first.invoice_date.month
        customer = first.seller_name.replace("/", "-").replace(" ", "_")[:50]
        ext = job.filename.rsplit(".", 1)[-1]
        storage_key = f"{year}/{month:02d}/{customer}/{first.invoice_number}.{ext}"
        await self._storage.upload_file(
            self._bucket_invoices, storage_key, file_data,
            "application/pdf" if ext == "pdf" else "application/xml",
        )

        # Clean up pending temp file
        if pending_path and os.path.exists(pending_path):
            os.unlink(pending_path)
        await self._repo.add_source_path(job_id, storage_key)

        # Append to monthly XLS in RustFS
        xls_key = f"Bang_ke_thue_{year}_{month:02d}.xlsx"
        try:
            existing = await self._storage.download_file(self._bucket_exports, xls_key)
        except Exception:
            existing = b""
        updated_xls = await self._excel.append_rows(updated_items, year, month, existing)
        await self._storage.upload_file(
            self._bucket_exports, xls_key, updated_xls,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        await self._repo.update_status(job_id, InvoiceStatus.CONFIRMED)
        job.status = InvoiceStatus.CONFIRMED
        return job

    async def reject(self, job_id: str) -> ProcessingJob:
        job = await self._repo.get(job_id)
        await self._repo.update_status(job_id, InvoiceStatus.REJECTED)
        job.status = InvoiceStatus.REJECTED
        return job