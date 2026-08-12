"""
Unit tests for the 2026 Advanced Hybrid RAG Pipeline:
- PDF text extraction & sliding window chunking
- Multi-query expansion
- Hybrid BM25 (sparse) + Dense vector similarity search
- Reciprocal Rank Fusion (RRF)
- PM counter re-ranking
"""
import asyncio
from pathlib import Path

from agent_tools.rag_pipeline import (
    DocumentIngestionEngine,
    SlidingWindowChunker,
    QueryExpander,
    TelecomRAGPipeline,
)
from agent_tools.tools.query_telecom_knowledge import query_telecom_knowledge


def test_pdf_extraction_and_chunking():
    pdf_path = Path("sample_data/Key Performance Indicators.pdf")
    assert pdf_path.exists(), "Key Performance Indicators.pdf missing from sample_data"

    pages = DocumentIngestionEngine.extract_pdf(pdf_path)
    assert len(pages) > 50, f"Expected 60+ pages, got {len(pages)}"

    chunker = SlidingWindowChunker()
    chunks = chunker.chunk_documents(pages)
    assert len(chunks) > len(pages)
    assert chunks[0].doc_name == "Key Performance Indicators.pdf"
    assert chunks[0].page_number is not None


def test_query_expansion():
    expander = QueryExpander()
    queries = expander.expand_query("accessibility drop")
    assert len(queries) > 1
    assert any("PMRRCCONNESTABSUCC" in q for q in queries)


def test_hybrid_rag_pipeline_search():
    pipeline = TelecomRAGPipeline("sample_data")
    assert len(pipeline.chunks) > 50

    # Search query for PM counter
    results = pipeline.search("PMRRCCONNESTABSUCC accessibility formula", max_sections=3)
    assert len(results) >= 1
    top = results[0]
    assert "doc_name" in top
    assert "relevance_score" in top
    assert top["relevance_score"] > 0.0
    assert "Key Performance Indicators.pdf" in top["doc_name"] or "telecom_knowledge.md" in top["doc_name"]


def test_query_telecom_knowledge_nat_tool():
    async def _run():
        async with query_telecom_knowledge(None, None) as info:
            inp = info.input_schema(query="Accessibility PMRRCCONNESTABSUCC", max_sections=3)
            return await info.single_fn(inp)

    result = asyncio.run(_run())
    assert "error" not in result
    assert result["match_count"] >= 1
    assert "retrieved_knowledge" in result
    first_match = result["retrieved_knowledge"][0]
    assert "Key Performance Indicators.pdf" in first_match["doc_name"] or "telecom_knowledge.md" in first_match["doc_name"]
