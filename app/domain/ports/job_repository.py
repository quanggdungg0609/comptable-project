from abc import ABC, abstractmethod
from typing import Optional
from app.domain.entities.processing_job import ProcessingJob
from app.domain.entities.invoice_item import InvoiceItem
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