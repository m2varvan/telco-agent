"""
NAT Tool: query_lte_kpi
Query raw LTE PM counters and compute KPIs for a given cell, OSS instance, and date.
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

from agent_tools.kpi_calculator import KPICalculator


def _log():
    """Lazy-import the TriageLogger from main.py if available."""
    try:
        import main as _m
        return _m.LOG
    except Exception:
        return None


class QueryLteKpiConfig(FunctionBaseConfig, name="query_lte_kpi"):
    """
    Query raw LTE PM counters from lte_kpi_sample.csv for a given cell, OSS instance,
    and date. Computes Accessibility, Retainability, DL Throughput, Cell Availability,
    and DL PDCP DRB Latency using Ericsson formulas.
    """
    pass


@register_function(config_type=QueryLteKpiConfig, framework_wrappers=[LLMFrameworkEnum.LANGCHAIN])
async def query_lte_kpi(tool_config: QueryLteKpiConfig, builder: Builder):
    csv_path = os.getenv("LTE_KPI_CSV", "sample_data/lte_kpi_sample.csv")

    async def _query_lte_kpi(cell_id: str, oss_id: str, year: int, month: int, day: int) -> dict[str, Any]:
        """
        Query raw LTE PM counters for a cell on a specific date.
        Computes Accessibility, Retainability, DL Throughput, Cell Availability, DL PDCP DRB Latency.

        Args:
            cell_id: EUTRANCELLFDD cell identifier (e.g. "INC1_CELL_A")
            oss_id: OSS instance identifier (e.g. "eniq_oss_1")
            year: Incident year (e.g. 2026)
            month: Incident month (e.g. 6)
            day: Incident day (e.g. 29)

        Returns:
            dict with kpis_evaluated list (kpi, value, baseline, status) and raw_counters
        """
        log = _log()
        args = {"cell_id": cell_id, "oss_id": oss_id, "year": year, "month": month, "day": day}
        if log:
            log.tool_called("query_lte_kpi", args)
        t0 = time.monotonic()

        con = duckdb.connect()
        try:
            result = con.execute(
                """
                SELECT * FROM read_csv_auto(?)
                WHERE EUTRANCELLFDD = ?
                  AND OSS_ID = ?
                  AND YEAR_ID = ? AND MONTH_ID = ? AND DAY_ID = ?
                """,
                [csv_path, cell_id, oss_id, year, month, day],
            )
            row = result.fetchone()

            if row is None:
                out = {"error": f"No LTE data found for cell {cell_id} on {year}-{month:02d}-{day:02d}"}
                if log:
                    log.tool_returned("query_lte_kpi", out, int((time.monotonic() - t0) * 1000))
                return out

            cols = [desc[0] for desc in con.description]
            counters = dict(zip(cols, row))

            prior_result = con.execute(
                """
                SELECT * FROM read_csv_auto(?)
                WHERE EUTRANCELLFDD = ?
                  AND OSS_ID = ?
                  AND (YEAR_ID < ? OR (YEAR_ID = ? AND MONTH_ID < ?)
                       OR (YEAR_ID = ? AND MONTH_ID = ? AND DAY_ID < ?))
                """,
                [csv_path, cell_id, oss_id,
                 year, year, month,
                 year, month, day],
            )
            prior_rows = prior_result.fetchall()

            calc = KPICalculator()
            out = calc.evaluate_lte(counters, prior_rows, cols)
        finally:
            con.close()

        if log:
            log.tool_returned("query_lte_kpi", out, int((time.monotonic() - t0) * 1000))
        return out

    yield FunctionInfo.from_fn(
        _query_lte_kpi,
        description=(
            "Query raw LTE PM counters from lte_kpi_sample.csv and compute KPIs "
            "(Accessibility, Retainability, DL Throughput, Cell Availability, DL Latency). "
            "Join keys: EUTRANCELLFDD, OSS_ID, YEAR_ID, MONTH_ID, DAY_ID. "
            "Args: cell_id (str), oss_id (str), year (int), month (int), day (int)."
        ),
    )
