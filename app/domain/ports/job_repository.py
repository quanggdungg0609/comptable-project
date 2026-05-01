from abc import ABC, abstractmethod
from typing import Optional
from app.domain.entities.processing_job import ProcessingJob
from app.domain.entities.invoice_item import InvoiceItem
from app.domain.entities.invoice_line_item import InvoiceLineItem
from app.domain.value_objects.invoice_status import InvoiceStatus

class IJobRepository(ABC):
    @abstractmethod
    async def save(self, job: ProcessingJob) -> None: ...

    @abstractmethod
    async def get(self, job_id: str) -> Optional[ProcessingJob]: ...

    @abstractmethod
    async def list_all(self, status: Optional[InvoiceStatus] = None) -> list[ProcessingJob]: ...

    @abstractmethod
    async def update_status(self, job_id: str, status: InvoiceStatus, error: Optional[str] = None) -> None: ...

    @abstractmethod
    async def save_items(self, job_id: str, items: list[InvoiceItem]) -> None: ...

    @abstractmethod
    async def update_items(self, job_id: str, items: list[InvoiceItem]) -> None: ...

    @abstractmethod
    async def add_source_path(self, job_id: str, path: str) -> None: ...

    @abstractmethod
    async def update_pending_file_path(self, job_id: str, path: str) -> None: ...

    @abstractmethod
    async def update_pending_pdf_path(self, job_id: str, path: str) -> None: ...

    @abstractmethod
    async def save_line_items(self, job_id: str, items: list[InvoiceLineItem]) -> None: ...

    @abstractmethod
    async def update_line_items(self, job_id: str, items: list[InvoiceLineItem]) -> None: ...

    @abstractmethod
    async def get_items_by_month(self, year: int, month: int) -> list[InvoiceItem]: ...

    @abstractmethod
    async def get_line_items_by_month(self, year: int, month: int) -> list[InvoiceLineItem]: ...

    @abstractmethod
    async def find_duplicate(
        self,
        invoice_symbol: str,
        invoice_number: str,
        seller_tax_code: str,
        exclude_job_id: Optional[str] = None,
    ) -> Optional[ProcessingJob]: ...

    @abstractmethod
    async def update_duplicate_of(self, job_id: str, duplicate_of_id: str) -> None: ...

    @abstractmethod
    async def list_retryable(self, max_retry_count: int = 3) -> list[ProcessingJob]: ...

    @abstractmethod
    async def increment_retry_count(self, job_id: str) -> None: ...