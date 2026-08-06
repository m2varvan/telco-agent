"""
Plain Python tool: query_cm_config
Query CM configuration parameters for a cell within a date window.
This is the NAT-independent version for testing and direct use.
"""
import os
from datetime import datetime, timedelta
from typing import Any

import duckdb


CM_CSV = os.getenv("CM_CONFIG_CSV", "sample_data/cm_config_sample.csv")


def query_cm_config(
    cell_id: str,
    oss_id: str,
    before_date: str,
    days_back: int = 7,
) -> dict[str, Any]:
    """
    Query cm_config_sample.csv for configuration records on cell_id within
    [before_date - days_back, before_date] window (inclusive).
    
    Join keys: EUTRANCELLFDD, OSS_ID, DATETIME_ID (Req 8.3, 8.7)
    Uses exact UPPERCASE column names: ADMINISTRATIVESTATE, CELLBARRED, FREQBAND,
    EARFCNDL, EARFCNUL, DLCHANNELBANDWIDTH, LATITUDE, LONGITUDE
    
    Args:
        cell_id: EUTRANCELLFDD identifier
        oss_id: OSS instance identifier
        before_date: ISO-8601 date string (e.g. "2026-06-29")
        days_back: Number of days back to search (default 7)
    
    Returns:
        dict with cell_id, window (from/to), changes list, num_records
    """
    csv_path = os.getenv("CM_CONFIG_CSV", CM_CSV)
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

        return {
            "cell_id": cell_id,
            "window": {"from": dt_from.isoformat(), "to": dt_to.isoformat()},
            "changes": [dict(zip(col_names, r)) for r in rows],
            "num_records": len(rows),
        }
    finally:
        con.close()
