# app/application/use_cases/excel_cr/llm_classify.py
import logging
from dataclasses import asdict
from app.infrastructure.repositories.sqlite_excel_cr_repo import SQLiteExcelCrRepository
from app.infrastructure.llm.excel_cr_classifier import ExcelCrClassifier

logger = logging.getLogger(__name__)


class LlmClassifyUseCase:
    def __init__(self, repo: SQLiteExcelCrRepository, classifier: ExcelCrClassifier):
        self._repo = repo
        self._classifier = classifier

    async def execute(self, session_id: str) -> dict:
        session = await self._repo.get(session_id)
        if session is None:
            raise ValueError(f"Session {session_id} not found")
        if not session.match_results:
            raise ValueError("Run aggregate first")

        unmatched = [r for r in session.match_results if r.get("chi_tieu") is None]
        if not unmatched:
            return {"session_id": session_id, "classified": 0}

        by_khoan_muc: dict[str, list] = {}
        for row in unmatched:
            km = row["khoan_muc"]
            by_khoan_muc.setdefault(km, []).append(row)

        # Collect all chi_tieu from session (from matched rows, as proxy for template list)
        known_chi_tieu = list({
            r["chi_tieu"] for r in session.match_results if r.get("chi_tieu")
        })

        auto_count = 0
        for khoan_muc, rows in by_khoan_muc.items():
            dien_giai_list = [r["dien_giai"] for r in rows]
            try:
                results = await self._classifier.classify(
                    khoan_muc=khoan_muc,
                    dien_giai_list=dien_giai_list,
                    chi_tieu_list=known_chi_tieu,
                )
            except Exception as e:
                logger.warning("LLM classify failed for %s: %s", khoan_muc, e)
                continue

            result_map = {r.dien_giai: r for r in results}
            for row in rows:
                res = result_map.get(row["dien_giai"])
                if res:
                    row["llm_suggested"] = res.suggested
                    row["llm_confidence"] = res.confidence
                    row["llm_reason"] = res.reason
                    row["llm_alternates"] = res.alternates
                    if res.auto_apply:
                        row["chi_tieu"] = res.suggested
                        row["match_tier"] = "llm_confirmed"
                        auto_count += 1

        session.status = "reviewed"
        await self._repo.update(session)
        return {"session_id": session_id, "classified": auto_count, "pending_review": len(unmatched) - auto_count}
