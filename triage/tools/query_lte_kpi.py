"""
Plain Python tool: query_lte_kpi
Query raw LTE PM counters and compute KPIs for a given cell, OSS instance, and date.
This is the NAT-independent version for testing and direct use.
"""
import os
from typing import Any

import duckdb

from triage.kpi_calculator import KPICalculator


LTE_CSV = os.getenv("LTE_KPI_CSV", "sample_data/lte_kpi_sample.csv")


def query_lte_kpi(
    cell_id: str,
    oss_id: str,
    year: int,
    month: int,
    day: int,
) -> dict[str, Any]:
    """
    Query raw LTE PM counters for (cell_id, oss_id, year, month, day) and return
    computed KPIs with baselines and degradation flags.

    Join keys: EUTRANCELLFDD, OSS_ID, YEAR_ID, MONTH_ID, DAY_ID (Req 8.1, 8.6)

    Returns:
        dict with cell_id, date, kpis_evaluated (kpi, value, baseline, status), raw_counters
        or {"error": "..."} if cell not found
    """
    csv_path = os.getenv("LTE_KPI_CSV", LTE_CSV)
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
            return {"error": f"No LTE data found for cell {cell_id} on {year}-{month:02d}-{day:02d}"}

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
        return calc.evaluate_lte(counters, prior_rows, cols)
    finally:
        con.close()
