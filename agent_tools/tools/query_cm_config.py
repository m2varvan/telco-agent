"""
NAT Tool: query_cm_config
Query CM configuration parameters for a cell within a date window.
"""
import os
import time
from datetime import datetime, timedelta
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


class QueryCmConfigConfig(FunctionBaseConfig, name="query_cm_config"):
    """
    Query cm_config_sample.csv for configuration parameters/changes on a cell within a date window.
    """
    pass


@register_function(config_type=QueryCmConfigConfig, framework_wrappers=[LLMFrameworkEnum.LANGCHAIN])
async def query_cm_config(tool_config: QueryCmConfigConfig, builder: Builder):
    csv_path = os.getenv("CM_CONFIG_CSV", "sample_data/cm_config_sample.csv")

    async def _query_cm_config(cell_id: str, oss_id: str, before_date: str, days_back: int = 7) -> dict[str, Any]:
        """
        Query CM configuration for a cell within the [before_date - days_back, before_date] window.
        Use when Accessibility, DL Throughput, or DL PDCP DRB Latency is degraded.
        Join keys: EUTRANCELLFDD, OSS_ID, DATETIME_ID.

        Args:
            cell_id: EUTRANCELLFDD identifier (e.g. "INC1_CELL_A")
            oss_id: OSS instance identifier (e.g. "eniq_oss_1")
            before_date: ISO-8601 date string (e.g. "2026-06-29")
            days_back: Number of days back to search (default 7)

        Returns:
            dict with cell_id, window (from/to), and changes list with CM parameters
        """
        log = _log()
        args = {"cell_id": cell_id, "oss_id": oss_id, "before_date": before_date, "days_back": days_back}
        if log:
            log.tool_called("query_cm_config", args)
        t0 = time.monotonic()

        dt_to = datetime.fromisoformat(before_date)
        dt_from = dt_to - timedelta(days=days_back)
        dt_from_str = dt_from.strftime("%Y-%m-%d")
        dt_to_str = dt_to.strftime("%Y-%m-%d")

        con = duckdb.connect()
        try:
            rows = con.execute(
                """
                SELECT EUTRANCELLFDD, OSS_ID, DATETIME_ID,
                       ADMINISTRATIVESTATE, CELLBARRED, FREQBAND,
                       EARFCNDL, EARFCNUL, DLCHANNELBANDWIDTH,
                       LATITUDE, LONGITUDE
                FROM read_csv_auto(?, all_varchar=true)
                WHERE EUTRANCELLFDD = ?
                  AND OSS_ID = ?
                  AND SUBSTRING(DATETIME_ID, 1, 10) >= ?
                  AND SUBSTRING(DATETIME_ID, 1, 10) <= ?
                ORDER BY DATETIME_ID
                """,
                [csv_path, cell_id, oss_id, dt_from_str, dt_to_str],
            ).fetchall()

            col_names = [
                "EUTRANCELLFDD", "OSS_ID", "DATETIME_ID",
                "ADMINISTRATIVESTATE", "CELLBARRED", "FREQBAND",
                "EARFCNDL", "EARFCNUL", "DLCHANNELBANDWIDTH",
                "LATITUDE", "LONGITUDE",
            ]

            out = {
                "cell_id": cell_id,
                "window": {"from": dt_from.isoformat(), "to": dt_to.isoformat()},
                "changes": [dict(zip(col_names, r)) for r in rows],
                "num_records": len(rows),
            }
        finally:
            con.close()

        if log:
            log.tool_returned("query_cm_config", out, int((time.monotonic() - t0) * 1000))
        return out

    yield FunctionInfo.from_fn(
        _query_cm_config,
        description=(
            "Query cm_config_sample.csv for configuration parameters on a cell in a date window. "
            "Returns ADMINISTRATIVESTATE, CELLBARRED, FREQBAND, DLCHANNELBANDWIDTH, LATITUDE, LONGITUDE. "
            "Join keys: EUTRANCELLFDD, OSS_ID, DATETIME_ID. "
            "Args: cell_id (str), oss_id (str), before_date (str ISO-8601), days_back (int, default 7)."
        ),
    )
