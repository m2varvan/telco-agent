"""
NAT Tool: query_neighbour_topology
Find co-site sectors (same eNodeB) and spatial neighbour cells within a geographic radius.
Reads from cm_config_sample.csv.
"""
import math
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


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the Great-Circle distance between two points in km."""
    r = 6371.0  # Earth's radius in kilometers
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r * c


class QueryNeighbourTopologyConfig(FunctionBaseConfig, name="query_neighbour_topology"):
    """
    Query cm_config_sample.csv to find co-site sectors (same eNodeB) and geographic neighbours
    within radius_km of the target cell.
    """
    pass


@register_function(config_type=QueryNeighbourTopologyConfig, framework_wrappers=[LLMFrameworkEnum.LANGCHAIN])
async def query_neighbour_topology(tool_config: QueryNeighbourTopologyConfig, builder: Builder):
    cm_csv = os.getenv("CM_CONFIG_CSV", "sample_data/cm_config_sample.csv")

    async def _query_neighbour_topology(
        cell_id: str, oss_id: str = "eniq_oss_1", radius_km: float = 3.0
    ) -> dict[str, Any]:
        """
        Find co-site sectors (same eNodeB) and spatial neighbours within a given radius.

        Args:
            cell_id: EUTRANCELLFDD identifier (e.g. "INC3_CELL_C1")
            oss_id: OSS instance identifier (default "eniq_oss_1")
            radius_km: Distance threshold in kilometers (default 3.0 km)

        Returns:
            dict with target_cell, enodeb, coordinates, co_site_cells, spatial_neighbours
        """
        log = _log()
        args = {"cell_id": cell_id, "oss_id": oss_id, "radius_km": radius_km}
        if log:
            log.tool_called("query_neighbour_topology", args)
        t0 = time.monotonic()

        con = duckdb.connect()
        try:
            # Retrieve unique cell list with latest lat/lon/enb
            rows = con.execute(
                """
                SELECT EUTRANCELLFDD, ENODEBFUNCTION, FREQBAND,
                       CAST(LATITUDE AS DOUBLE) / CASE WHEN ABS(CAST(LATITUDE AS DOUBLE)) > 180 THEN 1e6 ELSE 1 END AS lat,
                       CAST(LONGITUDE AS DOUBLE) / CASE WHEN ABS(CAST(LONGITUDE AS DOUBLE)) > 180 THEN 1e6 ELSE 1 END AS lon
                FROM (
                    SELECT EUTRANCELLFDD, ENODEBFUNCTION, FREQBAND, LATITUDE, LONGITUDE,
                           ROW_NUMBER() OVER (PARTITION BY EUTRANCELLFDD ORDER BY DATETIME_ID DESC) as rn
                    FROM read_csv_auto(?, all_varchar=true)
                    WHERE OSS_ID = ?
                ) WHERE rn = 1
                """,
                [cm_csv, oss_id],
            ).fetchall()
        finally:
            con.close()

        target_row = next((r for r in rows if r[0] == cell_id), None)
        if not target_row:
            out = {"error": f"Cell {cell_id} not found in configuration topology."}
            if log:
                log.tool_returned("query_neighbour_topology", out, int((time.monotonic() - t0) * 1000))
            return out

        target_cell, target_enb, target_band, target_lat, target_lon = target_row

        co_site: list[dict] = []
        spatial_neighbours: list[dict] = []

        for r in rows:
            other_cell, other_enb, other_band, other_lat, other_lon = r
            if other_cell == cell_id:
                continue

            dist = round(haversine_km(target_lat, target_lon, other_lat, other_lon), 3)

            item = {
                "cell_id": other_cell,
                "enodeb": other_enb,
                "band": other_band,
                "distance_km": dist,
            }

            if other_enb == target_enb or (other_cell.startswith(target_cell[:4]) and not target_cell.startswith("GEN")):
                co_site.append(item)
            elif dist <= radius_km:
                spatial_neighbours.append(item)

        out = {
            "target_cell": cell_id,
            "enodeb": target_enb,
            "coordinates": {"latitude": target_lat, "longitude": target_lon},
            "co_site_cells": sorted(co_site, key=lambda x: x["cell_id"]),
            "spatial_neighbours": sorted(spatial_neighbours, key=lambda x: x["distance_km"]),
            "co_site_count": len(co_site),
            "neighbour_count": len(spatial_neighbours),
        }

        if log:
            log.tool_returned("query_neighbour_topology", out, int((time.monotonic() - t0) * 1000))
        return out

    yield FunctionInfo.from_fn(
        _query_neighbour_topology,
        description=(
            "Find co-site sectors (same eNodeB) and spatial neighbour cells within a geographic radius. "
            "Use when evaluating multi-cell degradation or neighbour interference. "
            "Args: cell_id (str), oss_id (str, default eniq_oss_1), radius_km (float, default 3.0)."
        ),
    )
