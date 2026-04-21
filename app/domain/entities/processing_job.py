from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
import uuid
from app.domain.entities.invoice_item import InvoiceItem
from app.domain.entities.invoice_line_item import InvoiceLineItem
from app.domain.value_objects.file_type import FileType
from app.domain.value_objects.invoice_status import InvoiceStatus


@dataclass
class ProcessingJob:
    id: str
    filename: str
    file_type: FileType
    status: InvoiceStatus
    created_at: datetime
    extracted_items: list[InvoiceItem] = field(default_factory=list)
    extracted_line_items: list[InvoiceLineItem] = field(default_factory=list)
    source_paths: list[str] = field(default_factory=list)
    error: Optional[str] = None
    pending_file_path: Optional[str] = None  # local temp path until confirmed

    @classmethod
    def create(cls, filename: str, file_type: FileType) -> "ProcessingJob":
        return cls(
            id=str(uuid.uuid4()),
            filename=filename,
            file_type=file_type,
            status=InvoiceStatus.PENDING,
            created_at=datetime.now(timezone.utc),
        )