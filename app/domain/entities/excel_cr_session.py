from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
import uuid

@dataclass
class ExcelCrSession:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: str = "pending"          # pending|aggregated|reviewed|done
    source_file_key: str | None = None
    template_key: str | None = None
    aggregated_data: list[dict[str, Any]] | None = None
    match_results: list[dict[str, Any]] | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))