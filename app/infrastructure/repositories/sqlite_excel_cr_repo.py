import json
from datetime import datetime, timezone
from typing import Optional
import aiosqlite

from app.domain.entities.excel_cr_session import ExcelCrSession

class SQLiteExcelCrRepository:
    def __init__(self, db: aiosqlite.Connection):
        self._db = db

    async def save(self, session: ExcelCrSession) -> None:
        await self._db.execute(
            """INSERT INTO excel_cr_sessions
               (id, status, source_file_key, template_key,
                aggregated_data, match_results, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                session.id,
                session.status,
                session.source_file_key,
                session.template_key,
                json.dumps(session.aggregated_data) if session.aggregated_data is not None else None,
                json.dumps(session.match_results) if session.match_results is not None else None,
                session.created_at.isoformat(),
                session.updated_at.isoformat(),
            ),
        )
        await self._db.commit()

    async def get(self, session_id: str) -> Optional[ExcelCrSession]:
        async with self._db.execute(
            "SELECT * FROM excel_cr_sessions WHERE id = ?", (session_id,)
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return None
        return ExcelCrSession(
            id=row["id"],
            status=row["status"],
            source_file_key=row["source_file_key"],
            template_key=row["template_key"],
            aggregated_data=json.loads(row["aggregated_data"]) if row["aggregated_data"] else None,
            match_results=json.loads(row["match_results"]) if row["match_results"] else None,
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    async def update(self, session: ExcelCrSession) -> None:
        session.updated_at = datetime.now(timezone.utc)
        await self._db.execute(
            """UPDATE excel_cr_sessions
               SET status=?, source_file_key=?, template_key=?,
                   aggregated_data=?, match_results=?, updated_at=?
               WHERE id=?""",
            (
                session.status,
                session.source_file_key,
                session.template_key,
                json.dumps(session.aggregated_data) if session.aggregated_data is not None else None,
                json.dumps(session.match_results) if session.match_results is not None else None,
                session.updated_at.isoformat(),
                session.id,
            ),
        )
        await self._db.commit()