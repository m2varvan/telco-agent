"""
NAT Tool: query_alarm_history
Retrieve downtime counters and alarm records for a cell on a given date.
Reads downtime from lte_kpi_sample.csv and alarms from alarm_history.csv.
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

# In-memory alarms injected by eval/scenarios.py for scripted eval runs.
# In interactive mode all alarms come from alarm_history.csv.
SYNTHETIC_ALARMS: list[dict] = []


def _log():
    try:
        import main as _m
        return _m.LOG
    except Exception:
        return None


class QueryAlarmHistoryConfig(FunctionBaseConfig, name="query_alarm_history"):
    """
    Retrieve downtime counters and alarm records for a cell on a given date.
    Use when Cell Availability is degraded.
    """
    pass


@register_function(config_type=QueryAlarmHistoryConfig, framework_wrappers=[LLMFrameworkEnum.LANGCHAIN])
async def query_alarm_history(tool_config: QueryAlarmHistoryConfig, builder: Builder):
    lte_csv   = os.getenv("LTE_KPI_CSV",       "sample_data/lte_kpi_sample.csv")
    alarm_csv = os.getenv("ALARM_HISTORY_CSV", "sample_data/alarm_history.csv")

    async def _query_alarm_history(
        cell_id: str, oss_id: str, year: int, month: int, day: int
    ) -> dict[str, Any]:
        """
        Retrieve downtime counters and alarm records for a cell on a given date.

        Args:
            cell_id: EUTRANCELLFDD identifier (e.g. "INC2_CELL_B")
            oss_id:  OSS instance identifier   (e.g. "eniq_oss_1")
            year:    Incident year
            month:   Incident month
            day:     Incident day

        Returns:
            dict with PMCELLDOWNTIMEAUTO, PMCELLDOWNTIMEMAN, PERIOD_DURATION,
            availability_pct, alarms list, has_downtime, alarm_count
        """
        log      = _log()
        args     = {"cell_id": cell_id, "oss_id": oss_id,
                    "year": year, "month": month, "day": day}
        date_str = f"{year}-{month:02d}-{day:02d}"

        if log:
            log.tool_called("query_alarm_history", args)
        t0 = time.monotonic()

        # ── 1. Downtime counters from LTE KPI CSV ──────────────────────────
        con = duckdb.connect()
        try:
            row = con.execute(
                """
                SELECT PMCELLDOWNTIMEAUTO, PMCELLDOWNTIMEMAN, PERIOD_DURATION
                FROM read_csv_auto(?)
                WHERE EUTRANCELLFDD = ?
                  AND OSS_ID        = ?
                  AND YEAR_ID  = ? AND MONTH_ID = ? AND DAY_ID = ?
                """,
                [lte_csv, cell_id, oss_id, year, month, day],
            ).fetchone()
        finally:
            con.close()

        if row is None:
            out = {"error": f"No LTE data for cell {cell_id} on {date_str}"}
            if log:
                log.tool_returned("query_alarm_history", out,
                                  int((time.monotonic() - t0) * 1000))
            return out

        downtime_auto = int(row[0]) if row[0] is not None else None
        downtime_man  = int(row[1]) if row[1] is not None else None
        period        = int(row[2]) if row[2] is not None else None

        avail = None
        if None not in (downtime_auto, downtime_man, period) and period:
            avail = round(100.0 * (1 - (downtime_auto + downtime_man) / period), 4)

        # ── 2. Alarm records from alarm_history.csv ────────────────────────
        csv_alarms: list[dict] = []
        if os.path.exists(alarm_csv):
            try:
                con2 = duckdb.connect()
                try:
                    # Read everything as varchar so timestamps are plain strings
                    alarm_rows = con2.execute(
                        """
                        SELECT alarm_id, EUTRANCELLFDD, OSS_ID, alarm_name,
                               severity, start_time, end_time, status, description
                        FROM read_csv_auto(?, all_varchar=true)
                        WHERE EUTRANCELLFDD = ?
                          AND OSS_ID        = ?
                          AND SUBSTRING(CAST(start_time AS VARCHAR), 1, 10) <= ?
                          AND (end_time IS NULL
                               OR SUBSTRING(CAST(end_time AS VARCHAR), 1, 10) >= ?)
                        ORDER BY start_time
                        """,
                        [alarm_csv, cell_id, oss_id, date_str, date_str],
                    ).fetchall()
                    cols = ["alarm_id", "EUTRANCELLFDD", "OSS_ID", "alarm_name",
                            "severity", "start_time", "end_time", "status", "description"]
                    csv_alarms = [dict(zip(cols, r)) for r in alarm_rows]
                finally:
                    con2.close()
            except Exception:
                pass  # alarm CSV failure is non-fatal

        # ── 3. Injected synthetic alarms (eval / scripted scenarios) ───────
        injected = [
            a for a in SYNTHETIC_ALARMS
            if a.get("EUTRANCELLFDD") == cell_id
            and str(a.get("start_time", ""))[:10] <= date_str
            and (not a.get("end_time")
                 or str(a.get("end_time", ""))[:10] >= date_str)
        ]

        # Merge — prefer CSV alarms; add injected only if alarm_id not already present
        seen = {a["alarm_id"] for a in csv_alarms}
        all_alarms = csv_alarms + [a for a in injected
                                   if a.get("alarm_id") not in seen]

        out = {
            "cell_id":          cell_id,
            "date":             date_str,
            "PMCELLDOWNTIMEAUTO": downtime_auto,
            "PMCELLDOWNTIMEMAN":  downtime_man,
            "PERIOD_DURATION":    period,
            "availability_pct":   avail,
            "alarms":             all_alarms,
            "has_downtime":       (downtime_auto or 0) + (downtime_man or 0) > 0,
            "alarm_count":        len(all_alarms),
        }

        if log:
            log.tool_returned("query_alarm_history", out,
                              int((time.monotonic() - t0) * 1000))
        return out

    yield FunctionInfo.from_fn(
        _query_alarm_history,
        description=(
            "Retrieve PMCELLDOWNTIMEAUTO, PMCELLDOWNTIMEMAN, availability_pct, and alarm "
            "records (alarm_name, severity, start/end time, description) for a cell on a "
            "given date. Reads from alarm_history.csv. "
            "Use when Cell Availability is degraded. "
            "Args: cell_id (str), oss_id (str), year (int), month (int), day (int)."
        ),
    )
