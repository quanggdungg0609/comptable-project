from abc import ABC, abstractmethod
from typing import Any

class IExcelCrRulePort(ABC):
    @abstractmethod
    async def load(self) -> dict[str, Any]: ...

    @abstractmethod
    async def save(self, rules: dict[str, Any]) -> None: ...