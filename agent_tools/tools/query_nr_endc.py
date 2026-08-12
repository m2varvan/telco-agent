"""
NAT Tool: query_nr_endc
Query NR EN-DC PM counters and compute EN-DC Setup Success Rate.
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
    try:
        import main as _m
        return _m.LOG
    except Exception:
        return None


class QueryNrEndcConfig(FunctionBaseConfig, name="query_nr_endc"):
    """
    Query NR EN-DC PM counters from nr_endc_sample.csv and compute EN-DC Setup Success Rate.
    """
    pass


@register_function(config_type=QueryNrEndcConfig, framework_wrappers=[LLMFrameworkEnum.LANGCHAIN])
async def query_nr_endc(tool_config: QueryNrEndcConfig, builder: Builder):
    csv_path = os.getenv("NR_ENDC_CSV", "sample_data/nr_endc_sample.csv")

    async def _query_nr_endc(nr_cell_id: str, oss_id: str, year: int, month: int, day: int) -> dict[str, Any]:
        """
        Query NR EN-DC counters and compute EN-DC Setup Success Rate.
        Use for 5G NSA cells when EN-DC performance is suspected degraded.

        Args:
            nr_cell_id: NRCellCU identifier (e.g. "INC4_NR_D")
            oss_id: OSS instance identifier (e.g. "eniq_oss_1")
            year: Incident year
            month: Incident month
            day: Incident day

        Returns:
            dict with kpis_evaluated (EN-DC Setup Success Rate) and raw_counters
        """
        log = _log()
        args = {"nr_cell_id": nr_cell_id, "oss_id": oss_id, "year": year, "month": month, "day": day}
        if log:
            log.tool_called("query_nr_endc", args)
        t0 = time.monotonic()

        con = duckdb.connect()
        try:
            result = con.execute(
                """
                SELECT * FROM read_csv_auto(?)
                WHERE NRCellCU = ?
                  AND OSS_ID = ?
                  AND YEAR_ID = ? AND MONTH_ID = ? AND DAY_ID = ?
                """,
                [csv_path, nr_cell_id, oss_id, year, month, day],
            )
            row = result.fetchone()

            if row is None:
                out = {"error": f"No NR data found for cell {nr_cell_id} on {year}-{month:02d}-{day:02d}"}
                if log:
                    log.tool_returned("query_nr_endc", out, int((time.monotonic() - t0) * 1000))
                return out

            cols = [desc[0] for desc in con.description]
            counters = dict(zip(cols, row))

            prior_result = con.execute(
                """
                SELECT * FROM read_csv_auto(?)
                WHERE NRCellCU = ?
                  AND OSS_ID = ?
                  AND (YEAR_ID < ? OR (YEAR_ID = ? AND MONTH_ID < ?)
                       OR (YEAR_ID = ? AND MONTH_ID = ? AND DAY_ID < ?))
                """,
                [csv_path, nr_cell_id, oss_id,
                 year, year, month,
                 year, month, day],
            )
            prior_rows = prior_result.fetchall()

            calc = KPICalculator()
            out = calc.evaluate_nr_endc(counters, prior_rows, cols)
        finally:
            con.close()

        if log:
            log.tool_returned("query_nr_endc", out, int((time.monotonic() - t0) * 1000))
        return out

    yield FunctionInfo.from_fn(
        _query_nr_endc,
        description=(
            "Query NR EN-DC PM counters from nr_endc_sample.csv and compute EN-DC Setup Success Rate. "
            "Join keys: NRCellCU, OSS_ID, YEAR_ID, MONTH_ID, DAY_ID. "
            "Args: nr_cell_id (str), oss_id (str), year (int), month (int), day (int)."
        ),
    )
