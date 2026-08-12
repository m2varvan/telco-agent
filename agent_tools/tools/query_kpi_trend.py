"""
NAT Tool: query_kpi_trend
Retrieve 14-day time-series KPI trends for a cell to analyze degradation patterns
(step-function drop vs gradual decline vs stable).
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

from agent_tools.kpi_calculator import KPICalculator


def _log():
    try:
        import main as _m
        return _m.LOG
    except Exception:
        return None


class QueryKpiTrendConfig(FunctionBaseConfig, name="query_kpi_trend"):
    """
    Retrieve 14-day time-series KPI trends for a cell up to end_date.
    Returns daily values, baseline median, min/max, and trend pattern classification.
    """
    pass


@register_function(config_type=QueryKpiTrendConfig, framework_wrappers=[LLMFrameworkEnum.LANGCHAIN])
async def query_kpi_trend(tool_config: QueryKpiTrendConfig, builder: Builder):
    lte_csv = os.getenv("LTE_KPI_CSV", "sample_data/lte_kpi_sample.csv")

    async def _query_kpi_trend(
        cell_id: str, oss_id: str, end_date: str, days: int = 14
    ) -> dict[str, Any]:
        """
        Query time-series KPI trend over a N-day lookback window up to end_date.

        Args:
            cell_id: EUTRANCELLFDD cell identifier (e.g. "INC1_CELL_A")
            oss_id: OSS instance identifier (e.g. "eniq_oss_1")
            end_date: ISO-8601 end date string (e.g. "2026-06-29")
            days: Lookback days window (default 14)

        Returns:
            dict with cell_id, kpi_trends list (date, accessibility, throughput, availability),
            baseline_accessibility, baseline_throughput, pattern classification.
        """
        log = _log()
        args = {"cell_id": cell_id, "oss_id": oss_id, "end_date": end_date, "days": days}
        if log:
            log.tool_called("query_kpi_trend", args)
        t0 = time.monotonic()

        dt_to = datetime.fromisoformat(end_date).date()
        dt_from = dt_to - timedelta(days=days - 1)

        con = duckdb.connect()
        try:
            rows = con.execute(
                """
                SELECT * FROM read_csv_auto(?)
                WHERE EUTRANCELLFDD = ?
                  AND OSS_ID = ?
                  AND (
                      (YEAR_ID * 10000 + MONTH_ID * 100 + DAY_ID) >= ?
                      AND (YEAR_ID * 10000 + MONTH_ID * 100 + DAY_ID) <= ?
                  )
                ORDER BY YEAR_ID, MONTH_ID, DAY_ID
                """,
                [
                    lte_csv, cell_id, oss_id,
                    dt_from.year * 10000 + dt_from.month * 100 + dt_from.day,
                    dt_to.year * 10000 + dt_to.month * 100 + dt_to.day,
                ],
            ).fetchall()

            if not rows:
                out = {"error": f"No KPI trend data found for cell {cell_id} between {dt_from} and {dt_to}"}
                if log:
                    log.tool_returned("query_kpi_trend", out, int((time.monotonic() - t0) * 1000))
                return out

            cols = [desc[0] for desc in con.description]
            calc = KPICalculator()

            daily_points = []
            acc_list = []
            thp_list = []
            avail_list = []

            for row in rows:
                counters = dict(zip(cols, row))
                y, m, d = counters["YEAR_ID"], counters["MONTH_ID"], counters["DAY_ID"]
                date_str = f"{y}-{m:02d}-{d:02d}"

                acc = calc.compute_accessibility(
                    counters.get("PMRRCCONNESTABSUCC"), counters.get("PMRRCCONNESTABATT"), counters.get("PMRRCCONNESTABATTREATT"),
                    counters.get("PMS1SIGCONNESTABSUCC"), counters.get("PMS1SIGCONNESTABATT"),
                    counters.get("PMERABESTABSUCCINIT"), counters.get("PMERABESTABATTINIT")
                )
                thp = calc.compute_dl_throughput(
                    counters.get("PMPDCPVOLDLDRB"), counters.get("PMPDCPVOLDLDRBLASTTTI"), counters.get("PMUETHPTIMEDL")
                )
                avail, _ = calc.compute_cell_availability(
                    counters.get("PMCELLDOWNTIMEAUTO"), counters.get("PMCELLDOWNTIMEMAN"), counters.get("PERIOD_DURATION")
                )

                if acc is not None:
                    acc_list.append(acc)
                if thp is not None:
                    thp_list.append(thp)
                if avail is not None:
                    avail_list.append(avail)

                daily_points.append({
                    "date": date_str,
                    "accessibility_pct": round(acc, 2) if acc is not None else None,
                    "dl_throughput_kbps": round(thp, 1) if thp is not None else None,
                    "availability_pct": round(avail, 2) if avail is not None else None,
                })

            # Trend pattern classification
            pattern = "stable"
            if len(acc_list) >= 3:
                recent_acc = acc_list[-1]
                prior_acc_median = calc.compute_baseline(acc_list[:-1]) or recent_acc
                if (prior_acc_median - recent_acc) > 10.0:
                    pattern = "step_drop"
                elif (prior_acc_median - recent_acc) > 3.0:
                    pattern = "gradual_decline"

            out = {
                "cell_id": cell_id,
                "window": {"from": str(dt_from), "to": str(dt_to), "days": len(daily_points)},
                "daily_trend": daily_points,
                "summary": {
                    "baseline_accessibility_pct": round(calc.compute_baseline(acc_list[:-1]) or 0, 2) if len(acc_list) > 1 else None,
                    "latest_accessibility_pct": round(acc_list[-1], 2) if acc_list else None,
                    "baseline_throughput_kbps": round(calc.compute_baseline(thp_list[:-1]) or 0, 1) if len(thp_list) > 1 else None,
                    "latest_throughput_kbps": round(thp_list[-1], 1) if thp_list else None,
                    "pattern": pattern,
                },
            }
        finally:
            con.close()

        if log:
            log.tool_returned("query_kpi_trend", out, int((time.monotonic() - t0) * 1000))
        return out

    yield FunctionInfo.from_fn(
        _query_kpi_trend,
        description=(
            "Retrieve 14-day time-series KPI trend and pattern classification (step_drop vs gradual_decline vs stable) "
            "for a cell leading up to an incident date. "
            "Args: cell_id (str), oss_id (str), end_date (str ISO-8601), days (int, default 14)."
        ),
    )
