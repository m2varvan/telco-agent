"""
Plain Python tool: query_nr_endc
Query NR EN-DC PM counters and compute EN-DC Setup Success Rate.
This is the NAT-independent version for testing and direct use.
"""
import os
from typing import Any

import duckdb

from triage.kpi_calculator import KPICalculator


NR_CSV = os.getenv("NR_ENDC_CSV", "sample_data/nr_endc_sample.csv")


def query_nr_endc(
    nr_cell_id: str,
    oss_id: str,
    year: int,
    month: int,
    day: int,
) -> dict[str, Any]:
    """
    Query NR EN-DC counters and compute EN-DC Setup Success Rate.
    
    Join keys: NRCellCU, OSS_ID, YEAR_ID, MONTH_ID, DAY_ID (Req 8.2, 8.7)
    Uses exact camelCase column names: pmEndcSetupUeSucc, pmEndcSetupUeAtt,
    pmEndcSetupScgUeSucc, pmEndcSetupScgUeAtt
    
    Returns:
        dict with nr_cell_id, date, kpis_evaluated, raw_counters
        or {"error": "..."} if cell not found
    """
    csv_path = os.getenv("NR_ENDC_CSV", NR_CSV)
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
            return {"error": f"No NR data found for cell {nr_cell_id} on {year}-{month:02d}-{day:02d}"}

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
        return calc.evaluate_nr_endc(counters, prior_rows, cols)
    finally:
        con.close()
