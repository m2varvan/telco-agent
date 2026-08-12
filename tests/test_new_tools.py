"""
Unit tests for the 4 new diagnostic tools:
- query_neighbour_topology
- query_kpi_trend
- query_similar_incidents
- query_telecom_knowledge
"""
import asyncio
import pytest
from agent_tools.tools.query_neighbour_topology import query_neighbour_topology
from agent_tools.tools.query_kpi_trend import query_kpi_trend
from agent_tools.tools.query_similar_incidents import query_similar_incidents
from agent_tools.tools.query_telecom_knowledge import query_telecom_knowledge



def test_query_neighbour_topology():
    async def _run():
        async with query_neighbour_topology(None, None) as info:
            inp = info.input_schema(cell_id="INC3_CELL_C1", oss_id="eniq_oss_1", radius_km=3.0)
            return await info.single_fn(inp)

    result = asyncio.run(_run())
    assert "error" not in result
    assert result["target_cell"] == "INC3_CELL_C1"
    assert result["enodeb"] == "eNB_INC3"
    assert result["co_site_count"] >= 1
    assert any(c["cell_id"] == "INC3_CELL_C2" for c in result["co_site_cells"])


def test_query_kpi_trend():
    async def _run():
        async with query_kpi_trend(None, None) as info:
            inp = info.input_schema(cell_id="INC1_CELL_A", oss_id="eniq_oss_1", end_date="2026-06-29", days=14)
            return await info.single_fn(inp)

    result = asyncio.run(_run())
    assert "error" not in result
    assert result["cell_id"] == "INC1_CELL_A"
    assert len(result["daily_trend"]) > 0
    assert "summary" in result
    assert result["summary"]["pattern"] in ("step_drop", "gradual_decline", "stable")


def test_query_similar_incidents():
    async def _run():
        async with query_similar_incidents(None, None) as info:
            inp = info.input_schema(cell_id="INC1_CELL_A", limit=5)
            return await info.single_fn(inp)

    result = asyncio.run(_run())
    assert "error" not in result
    assert result["cell_id"] == "INC1_CELL_A"
    assert result["match_count"] >= 1
    assert "historical_tickets" in result
    assert result["historical_tickets"][0]["root_cause_code"] in ("CELL_BARRED_CHANGE", "ADMIN_STATE_CHANGE")


def test_query_telecom_knowledge():
    async def _run():
        async with query_telecom_knowledge(None, None) as info:
            inp = info.input_schema(query="Accessibility formula", max_sections=3)
            return await info.single_fn(inp)

    result = asyncio.run(_run())
    assert "error" not in result
    assert result["match_count"] >= 1
    assert "retrieved_knowledge" in result
    titles = [k["title"] for k in result["retrieved_knowledge"]]
    assert any("Accessibility" in t or "Ericsson" in t for t in titles)



