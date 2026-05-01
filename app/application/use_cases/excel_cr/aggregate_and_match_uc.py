# app/application/use_cases/excel_cr/aggregate_and_match_uc.py
import logging
from dataclasses import asdict
from app.domain.ports.storage_port import IStoragePort
from app.domain.ports.excel_cr_rule_port import IExcelCrRulePort
from app.domain.entities.excel_cr_session import ExcelCrSession
from app.infrastructure.repositories.sqlite_excel_cr_repo import SQLiteExcelCrRepository
from app.infrastructure.parsers.excel_cr_source_parser import parse_source_file
from app.application.use_cases.excel_cr.aggregate_and_match import aggregate_rows, match_rules

logger = logging.getLogger(__name__)

BUCKET = "excel-cr"


class AggregateAndMatchUseCase:
    def __init__(
        self,
        repo: SQLiteExcelCrRepository,
        storage: IStoragePort,
        rules_manager: IExcelCrRulePort,
    ):
        self._repo = repo
        self._storage = storage
        self._rules = rules_manager

    async def execute(self, session_id: str) -> dict:
        session = await self._repo.get(session_id)
        if session is None:
            raise ValueError(f"Session {session_id} not found")

        source_bytes = await self._storage.download_file(BUCKET, session.source_file_key)
        filename = session.source_file_key.rsplit("/", 1)[-1]
        df = parse_source_file(source_bytes, filename)

        raw_rows = df.to_dict(orient="records")
        agg_rows = aggregate_rows(raw_rows)

        rules = await self._rules.load()
        matched, unmatched = match_rules(agg_rows, rules)

        session.aggregated_data = [asdict(r) for r in agg_rows]
        session.match_results = [asdict(r) for r in matched] + [asdict(r) for r in unmatched]
        session.status = "aggregated"
        await self._repo.update(session)

        return {
            "session_id": session_id,
            "total": len(agg_rows),
            "matched": len(matched),
            "unmatched": len(unmatched),
            "rows": session.match_results,
        }
