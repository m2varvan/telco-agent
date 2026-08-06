"""
Plain Python tool: query_alarm_history
Retrieve downtime counters and synthetic alarm records for a cell on a given date.
This is the NAT-independent version for testing and direct use.
"""
import os
from typing import Any

import duckdb


LTE_CSV = os.getenv("LTE_KPI_CSV", "sample_data/lte_kpi_sample.csv")

# Synthetic alarm table — populated by eval/scenarios.py before each scripted run.
# Each record: {alarm_id, EUTRANCELLFDD, alarm_name, severity, start_time, end_time, status}
SYNTHETIC_ALARMS: list[dict] = []


def query_alarm_history(
    cell_id: str,
    oss_id: str,
    year: int,
    month: int,
    day: int,
) -> dict[str, Any]:
    """
    Retrieve downtime counters from lte_kpi_sample.csv AND synthetic alarm records
    matching the given cell and date. Use when Cell Availability is degraded.

    Join keys: EUTRANCELLFDD, OSS_ID, YEAR_ID, MONTH_ID, DAY_ID (Req 8.1)

    Returns:
        dict with cell_id, PMCELLDOWNTIMEAUTO, PMCELLDOWNTIMEMAN, PERIOD_DURATION,
        availability_pct, alarms list, has_downtime bool
        or {"error": "..."} if cell not found
    """
    csv_path = os.getenv("LTE_KPI_CSV", LTE_CSV)
    con = duckdb.connect()
    try:
        result = con.execute(
            """
            SELECT PMCELLDOWNTIMEAUTO, PMCELLDOWNTIMEMAN, PERIOD_DURATION
            FROM read_csv_auto(?)
            WHERE EUTRANCELLFDD = ?
              AND OSS_ID = ?
              AND YEAR_ID = ? AND MONTH_ID = ? AND DAY_ID = ?
            """,
            [csv_path, cell_id, oss_id, year, month, day],
        )
        row = result.fetchone()
    finally:
        con.close()

    if row is None:
        return {"error": f"No data found for cell {cell_id} on {year}-{month:02d}-{day:02d}"}

    try:
        downtime_auto = int(row[0]) if row[0] is not None else None
        downtime_man  = int(row[1]) if row[1] is not None else None
        period        = int(row[2]) if row[2] is not None else None
    except (ValueError, TypeError):
        downtime_auto = downtime_man = period = None

    avail = None
    if downtime_auto is not None and downtime_man is not None and period:
        avail = round(100.0 * (1 - (downtime_auto + downtime_man) / period), 4)

    date_str = f"{year}-{month:02d}-{day:02d}"
    alarms = [
        a for a in SYNTHETIC_ALARMS
        if a.get("EUTRANCELLFDD") == cell_id
        and a.get("start_time", "")[:10] == date_str
    ]

    return {
        "cell_id": cell_id,
        "PMCELLDOWNTIMEAUTO": downtime_auto,
        "PMCELLDOWNTIMEMAN": downtime_man,
        "PERIOD_DURATION": period,
        "availability_pct": avail,
        "alarms": alarms,
        "has_downtime": (downtime_auto or 0) + (downtime_man or 0) > 0,
    }
