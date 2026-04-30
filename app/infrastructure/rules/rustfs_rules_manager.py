import json
import logging
from typing import Any
from app.domain.ports.excel_cr_rule_port import IExcelCrRulePort
from app.domain.ports.storage_port import IStoragePort

logger = logging.getLogger(__name__)

_DEFAULT_RULES: dict[str, Any] = {
    "llm_confirmed": [],
    "keyword": [],
    "direct": [],
}
_RULES_KEY = "config/rules.json"


class RustfsRulesManager(IExcelCrRulePort):
    def __init__(self, storage: IStoragePort, bucket: str):
        self._storage = storage
        self._bucket = bucket

    async def load(self) -> dict[str, Any]:
        try:
            data = await self._storage.download_file(self._bucket, _RULES_KEY)
            return json.loads(data)
        except Exception:
            logger.info("rules.json not found in RustFS — returning defaults")
            return dict(_DEFAULT_RULES)

    async def save(self, rules: dict[str, Any]) -> None:
        data = json.dumps(rules, ensure_ascii=False, indent=2).encode("utf-8")
        await self._storage.upload_file(self._bucket, _RULES_KEY, data, "application/json")