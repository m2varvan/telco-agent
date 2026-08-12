"""
NAT Tool: query_similar_incidents
Query historical ticket records in incident_history.csv for past resolved incidents on a cell
or root cause code, returning resolution notes and engineer actions.
"""
import os
import time
from typing import Any

import duckdb
from nat.builder.builder import Builder
from nat.builder.framework_enum import LLMFrameworkEnum
from nat.builder.function_info import FunctionInfo
from nat.cli.register_workflow import register_function
from nat.data_models.function import FunctionBaseConfig


def _log():
    try:
        import main as _m
        return _m.LOG
    except Exception:
        return None


class QuerySimilarIncidentsConfig(FunctionBaseConfig, name="query_similar_incidents"):
    """
    Query incident_history.csv for past tickets matching a cell_id or root_cause_code.
    """
    pass


@register_function(config_type=QuerySimilarIncidentsConfig, framework_wrappers=[LLMFrameworkEnum.LANGCHAIN])
async def query_similar_incidents(tool_config: QuerySimilarIncidentsConfig, builder: Builder):
    ticket_csv = os.getenv("INCIDENT_HISTORY_CSV", "sample_data/incident_history.csv")

    async def _query_similar_incidents(
        cell_id: str | None = None,
        root_cause_code: str | None = None,
        oss_id: str = "eniq_oss_1",
        limit: int = 5,
    ) -> dict[str, Any]:
        """
        Query past incident resolution tickets for a cell or root cause category.

        Args:
            cell_id: EUTRANCELLFDD identifier (e.g. "INC1_CELL_A", optional)
            root_cause_code: Root cause code filter (e.g. "CELL_BARRED_CHANGE", optional)
            oss_id: OSS instance identifier (default "eniq_oss_1")
            limit: Maximum tickets to return (default 5)

        Returns:
            dict with matched_tickets list containing ticket_id, cell_id, created_date,
            root_cause_code, summary, resolution_notes, engineer_id
        """
        log = _log()
        args = {"cell_id": cell_id, "root_cause_code": root_cause_code, "limit": limit}
        if log:
            log.tool_called("query_similar_incidents", args)
        t0 = time.monotonic()

        if not os.path.exists(ticket_csv):
            out = {"error": f"Incident history database not found at {ticket_csv}"}
            if log:
                log.tool_returned("query_similar_incidents", out, int((time.monotonic() - t0) * 1000))
            return out

        con = duckdb.connect()
        try:
            query = "SELECT * FROM read_csv_auto(?, all_varchar=true) WHERE OSS_ID = ?"
            params = [ticket_csv, oss_id]

            if cell_id:
                query += " AND EUTRANCELLFDD = ?"
                params.append(cell_id)

            if root_cause_code:
                query += " AND root_cause_code = ?"
                params.append(root_cause_code)

            query += " ORDER BY created_date DESC LIMIT ?"
            params.append(limit)

            rows = con.execute(query, params).fetchall()
            cols = ["ticket_id", "EUTRANCELLFDD", "OSS_ID", "created_date", "closed_date",
                    "root_cause_code", "summary", "resolution_notes", "engineer_id"]

            tickets = [dict(zip(cols, r)) for r in rows]

            out = {
                "cell_id": cell_id,
                "root_cause_code": root_cause_code,
                "match_count": len(tickets),
                "historical_tickets": tickets,
            }
        finally:
            con.close()

        if log:
            log.tool_returned("query_similar_incidents", out, int((time.monotonic() - t0) * 1000))
        return out

    yield FunctionInfo.from_fn(
        _query_similar_incidents,
        description=(
            "Search historical ticket records in incident_history.csv for past resolved incidents on a cell "
            "or root cause category. Provides past resolution notes and fix actions. "
            "Args: cell_id (str, optional), root_cause_code (str, optional), limit (int, default 5)."
        ),
    )
