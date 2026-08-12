"""
NAT Tool: query_telecom_knowledge
Retrieval-Augmented Generation (RAG) hybrid search over telecom operations manuals,
Ericsson KPI user guides (PDFs), and SOP playbooks in sample_data/.
"""
import os
import time
from typing import Any

from nat.builder.builder import Builder
from nat.builder.framework_enum import LLMFrameworkEnum
from nat.builder.function_info import FunctionInfo
from nat.cli.register_workflow import register_function
from nat.data_models.function import FunctionBaseConfig

from agent_tools.rag_pipeline import TelecomRAGPipeline

_RAG_PIPELINE: TelecomRAGPipeline | None = None


def _get_pipeline() -> TelecomRAGPipeline:
    global _RAG_PIPELINE
    if _RAG_PIPELINE is None:
        sample_dir = os.getenv("SAMPLE_DATA_DIR", "sample_data")
        _RAG_PIPELINE = TelecomRAGPipeline(sample_dir)
    return _RAG_PIPELINE


def _log():
    try:
        import main as _m
        return _m.LOG
    except Exception:
        return None


class QueryTelecomKnowledgeConfig(FunctionBaseConfig, name="query_telecom_knowledge"):
    """
    Query sample_data/*.pdf and sample_data/*.md for relevant Ericsson KPI definitions,
    counter formulas, and SOP playbooks using a 4-Stage Hybrid RAG Pipeline.
    """
    pass


@register_function(config_type=QueryTelecomKnowledgeConfig, framework_wrappers=[LLMFrameworkEnum.LANGCHAIN])
async def query_telecom_knowledge(tool_config: QueryTelecomKnowledgeConfig, builder: Builder):
    async def _query_telecom_knowledge(query: str, max_sections: int = 3) -> dict[str, Any]:
        """
        Search telecom operations guides, Key Performance Indicators PDF, and SOP playbooks using Hybrid RAG.

        Args:
            query: Natural language query or topic (e.g. "accessibility formula", "PMRRCCONNESTABSUCC", "backhaul link down SOP")
            max_sections: Maximum relevant document sections to return (default 3)

        Returns:
            dict with query, total_chunks_searched, matches list (doc_name, page_number, section_title, content, score)
        """
        log = _log()
        args = {"query": query, "max_sections": max_sections}
        if log:
            log.tool_called("query_telecom_knowledge", args)
        t0 = time.monotonic()

        pipeline = _get_pipeline()
        results = pipeline.search(query, max_sections=max_sections)

        # Standardize format for main.py logger & agent JSON synthesis
        formatted_matches = []
        for r in results:
            formatted_matches.append({
                "title": f"[{r['doc_name']}" + (f" p.{r['page_number']}" if r['page_number'] else "") + f"] {r['section_title']}",
                "doc_name": r["doc_name"],
                "page_number": r["page_number"],
                "section_title": r["section_title"],
                "content": r["content"],
                "relevance_score": r["relevance_score"],
            })

        out = {
            "query": query,
            "total_chunks_indexed": len(pipeline.chunks),
            "match_count": len(formatted_matches),
            "retrieved_knowledge": formatted_matches,
        }

        if log:
            log.tool_returned("query_telecom_knowledge", out, int((time.monotonic() - t0) * 1000))
        return out

    yield FunctionInfo.from_fn(
        _query_telecom_knowledge,
        description=(
            "Search telecom operations manuals, Ericsson KPI user guides (PDFs), and SOP playbooks in sample_data/. "
            "Uses a 4-Stage Hybrid RAG Pipeline (Multi-Query Expansion, BM25 Sparse + Dense Vector, RRF Fusion, Re-ranking). "
            "Use to look up counter formulas, KPI thresholds, or standard operating procedure playbooks. "
            "Args: query (str), max_sections (int, default 3)."
        ),
    )

