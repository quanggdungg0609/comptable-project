# app/application/use_cases/excel_cr/confirm_mappings.py
import logging
from typing import Any
from app.domain.ports.excel_cr_rule_port import IExcelCrRulePort
from app.infrastructure.repositories.sqlite_excel_cr_repo import SQLiteExcelCrRepository

logger = logging.getLogger(__name__)


class ConfirmMappingsUseCase:
    def __init__(self, repo: SQLiteExcelCrRepository, rules_manager: IExcelCrRulePort):
        self._repo = repo
        self._rules = rules_manager

    async def execute(self, session_id: str, confirmations: list[dict[str, Any]]) -> dict:
        """confirmations: [{"dien_giai": str, "khoan_muc": str, "chi_tieu": str}]"""
        session = await self._repo.get(session_id)
        if session is None:
            raise ValueError(f"Session {session_id} not found")

        confirm_map = {c["dien_giai"]: c for c in confirmations}

        # Apply confirmations to match_results
        for row in (session.match_results or []):
            conf = confirm_map.get(row["dien_giai"])
            if conf:
                row["chi_tieu"] = conf["chi_tieu"]
                row["match_tier"] = "llm_confirmed"

        # Persist new confirmed mappings to rules.json
        rules = await self._rules.load()
        existing_confirmed = {r["dien_giai"].lower() for r in rules["llm_confirmed"]}
        for conf in confirmations:
            if conf["dien_giai"].lower() not in existing_confirmed:
                rules["llm_confirmed"].append({
                    "dien_giai": conf["dien_giai"],
                    "chi_tieu": conf["chi_tieu"],
                })
        await self._rules.save(rules)

        session.status = "done"
        await self._repo.update(session)
        return {"session_id": session_id, "confirmed": len(confirmations)}
