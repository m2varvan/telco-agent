"""
2026 Advanced Hybrid RAG Pipeline Module
Rogers AI for Networks | Multi-Stage RAG Architecture

Pipeline Stages:
  1. PDF & Document Structural Extraction + Sliding Window Chunking
  2. Multi-Query Expansion (Acronym & Counter Rewriting)
  3. Hybrid Sparse (BM25) + Dense (Vector Similarity) Retrieval
  4. Reciprocal Rank Fusion (RRF)
  5. Exact PM Counter & Heading Re-Ranking
"""
from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pypdf
from rank_bm25 import BM25Okapi


@dataclass
class TextChunk:
    chunk_id: str
    doc_name: str
    page_number: int | None
    section_title: str
    text: str


def _tokenize(text: str) -> list[str]:
    """Tokenize preserving underscore-connected counter names (e.g. PMRRCCONNESTABSUCC)."""
    return re.findall(r'[a-zA-Z0-9_]+', text.lower())


class DocumentIngestionEngine:
    """Extracts pages and sections from PDF and Markdown files in sample_data/."""

    @staticmethod
    def extract_pdf(pdf_path: Path) -> list[dict[str, Any]]:
        pages = []
        try:
            reader = pypdf.PdfReader(str(pdf_path))
            current_heading = pdf_path.stem
            for i, page in enumerate(reader.pages, start=1):
                text = page.extract_text() or ""
                # Attempt to extract heading if page starts with a section title
                lines = [line.strip() for line in text.split("\n") if line.strip()]
                if lines:
                    first_line = lines[0]
                    if len(first_line) < 80 and not first_line.isdigit():
                        current_heading = first_line

                pages.append({
                    "doc_name": pdf_path.name,
                    "page_number": i,
                    "section_title": current_heading,
                    "text": text,
                })
        except Exception as err:
            print(f"  ⚠  Warning: PDF extraction failed for {pdf_path.name}: {err}")
        return pages

    @staticmethod
    def extract_markdown(md_path: Path) -> list[dict[str, Any]]:
        sections = []
        try:
            full_text = md_path.read_text()
            raw_sections = re.split(r'\n(?=#{1,3}\s)', full_text)
            for sec in raw_sections:
                sec_str = sec.strip()
                if sec_str:
                    lines = sec_str.split("\n")
                    heading = lines[0].lstrip("#").strip()
                    sections.append({
                        "doc_name": md_path.name,
                        "page_number": None,
                        "section_title": heading,
                        "text": sec_str,
                    })
        except Exception as err:
            print(f"  ⚠  Warning: Markdown extraction failed for {md_path.name}: {err}")
        return sections


class SlidingWindowChunker:
    """Chunks text pages into sliding windows with overlap, preserving page & section metadata."""

    def __init__(self, chunk_size_chars: int = 1200, overlap_chars: int = 250):
        self.chunk_size = chunk_size_chars
        self.overlap = overlap_chars

    def chunk_documents(self, doc_pages: list[dict[str, Any]]) -> list[TextChunk]:
        chunks: list[TextChunk] = []
        chunk_idx = 0

        for page in doc_pages:
            text = page["text"].strip()
            if not text:
                continue

            if len(text) <= self.chunk_size:
                chunk_idx += 1
                chunks.append(TextChunk(
                    chunk_id=f"{page['doc_name']}_p{page['page_number'] or 0}_c{chunk_idx}",
                    doc_name=page["doc_name"],
                    page_number=page["page_number"],
                    section_title=page["section_title"],
                    text=text,
                ))
            else:
                start = 0
                while start < len(text):
                    end = min(start + self.chunk_size, len(text))
                    chunk_text = text[start:end].strip()
                    if chunk_text:
                        chunk_idx += 1
                        chunks.append(TextChunk(
                            chunk_id=f"{page['doc_name']}_p{page['page_number'] or 0}_c{chunk_idx}",
                            doc_name=page["doc_name"],
                            page_number=page["page_number"],
                            section_title=page["section_title"],
                            text=chunk_text,
                        ))
                    start += (self.chunk_size - self.overlap)

        return chunks


class QueryExpander:
    """Multi-query expansion for acronyms, counter names, and telecom concepts."""

    TELECOM_SYNONYMS = {
        "accessibility": ["PMRRCCONNESTABSUCC", "PMERABESTABSUCCINIT", "E-RAB initial setup success rate"],
        "retainability": ["PMERABRELABNORMALENB", "E-RAB percent lost abnormal release"],
        "throughput": ["PMPDCPVOLDLDRB", "PMUETHPTIMEDL", "DL throughput kbps"],
        "availability": ["PMCELLDOWNTIMEAUTO", "PMCELLDOWNTIMEMAN", "cell availability downtime"],
        "endc": ["pmEndcSetupUeSucc", "pmEndcSetupFailNrRa", "5G NSA EN-DC setup success"],
        "barring": ["CELLBARRED", "access barring"],
        "admin": ["ADMINISTRATIVESTATE", "cell operational lock state"],
        "backhaul": ["Backhaul Link Down", "transmission outage"],
        "interference": ["NEIGHBOUR_INTERFERENCE", "co-site sector interference"],
    }

    def expand_query(self, query: str) -> list[str]:
        queries = [query]
        q_lower = query.lower()

        expanded_terms = []
        for key, syns in self.TELECOM_SYNONYMS.items():
            if key in q_lower:
                expanded_terms.extend(syns)

        if expanded_terms:
            queries.append(f"{query} {' '.join(expanded_terms[:3])}")
            queries.append(" ".join(expanded_terms[:4]))

        return queries


class SimpleDenseVectorizer:
    """Sublinear TF-IDF n-gram vectorizer for dense semantic similarity without external heavyweight models."""

    def __init__(self):
        self.vocabulary: dict[str, int] = {}
        self.idf: dict[str, float] = {}
        self.doc_vectors: list[dict[int, float]] = []

    def fit_transform(self, texts: list[str]) -> None:
        doc_count = len(texts)
        term_doc_freq: dict[str, int] = {}

        # Build n-grams
        tokenized_docs = []
        for text in texts:
            tokens = _tokenize(text)
            # Combine 1-grams and 2-grams
            ngrams = tokens + [f"{tokens[i]}_{tokens[i+1]}" for i in range(len(tokens) - 1)]
            tokenized_docs.append(ngrams)

            unique_terms = set(ngrams)
            for term in unique_terms:
                term_doc_freq[term] = term_doc_freq.get(term, 0) + 1

        # Vocabulary assignment
        self.vocabulary = {term: idx for idx, term in enumerate(sorted(term_doc_freq.keys()))}

        # Calculate IDF
        for term, df in term_doc_freq.items():
            self.idf[term] = math.log((doc_count + 1) / (df + 1)) + 1.0

        # Build document vectors
        self.doc_vectors = []
        for ngrams in tokenized_docs:
            vec: dict[int, float] = {}
            term_counts: dict[str, int] = {}
            for t in ngrams:
                term_counts[t] = term_counts.get(t, 0) + 1

            norm_sq = 0.0
            for term, count in term_counts.items():
                if term in self.vocabulary:
                    term_idx = self.vocabulary[term]
                    tf = 1.0 + math.log(count)
                    weight = tf * self.idf[term]
                    vec[term_idx] = weight
                    norm_sq += weight * weight

            # Normalize L2
            norm = math.sqrt(norm_sq) or 1.0
            for k in vec:
                vec[k] /= norm

            self.doc_vectors.append(vec)

    def score_query(self, query: str) -> list[float]:
        tokens = _tokenize(query)
        ngrams = tokens + [f"{tokens[i]}_{tokens[i+1]}" for i in range(len(tokens) - 1)]

        term_counts: dict[str, int] = {}
        for t in ngrams:
            term_counts[t] = term_counts.get(t, 0) + 1

        q_vec: dict[int, float] = {}
        norm_sq = 0.0
        for term, count in term_counts.items():
            if term in self.vocabulary:
                term_idx = self.vocabulary[term]
                tf = 1.0 + math.log(count)
                weight = tf * self.idf[term]
                q_vec[term_idx] = weight
                norm_sq += weight * weight

        norm = math.sqrt(norm_sq) or 1.0
        for k in q_vec:
            q_vec[k] /= norm

        # Dot product cosine similarity
        scores = []
        for doc_vec in self.doc_vectors:
            score = 0.0
            for term_idx, weight in q_vec.items():
                if term_idx in doc_vec:
                    score += weight * doc_vec[term_idx]
            scores.append(score)

        return scores


class TelecomRAGPipeline:
    """
    Complete 4-Stage Hybrid RAG Engine:
      Stage 1: Multi-Query Expansion
      Stage 2: Hybrid BM25 (Sparse) + Dense Vector Similarity
      Stage 3: Reciprocal Rank Fusion (RRF)
      Stage 4: PM Counter & Heading Exact Re-Ranking
    """

    def __init__(self, data_dir: str = "sample_data"):
        self.data_dir = Path(data_dir)
        self.chunks: list[TextChunk] = []
        self.bm25_index: BM25Okapi | None = None
        self.dense_vectorizer: SimpleDenseVectorizer | None = None
        self.expander = QueryExpander()

        self._build_index()

    def _build_index(self) -> None:
        ingestion = DocumentIngestionEngine()
        doc_pages: list[dict[str, Any]] = []

        if self.data_dir.exists():
            # Process all PDFs in sample_data
            for pdf_file in sorted(self.data_dir.glob("*.pdf")):
                doc_pages.extend(ingestion.extract_pdf(pdf_file))

            # Process all Markdown files in sample_data
            for md_file in sorted(self.data_dir.glob("*.md")):
                doc_pages.extend(ingestion.extract_markdown(md_file))

        chunker = SlidingWindowChunker()
        self.chunks = chunker.chunk_documents(doc_pages)

        if not self.chunks:
            return

        # Build Sparse BM25 Index
        corpus_tokens = [_tokenize(c.text) for c in self.chunks]
        self.bm25_index = BM25Okapi(corpus_tokens)

        # Build Dense TF-IDF Vector Index
        self.dense_vectorizer = SimpleDenseVectorizer()
        self.dense_vectorizer.fit_transform([c.text for c in self.chunks])

    def search(self, query: str, max_sections: int = 3) -> list[dict[str, Any]]:
        if not self.chunks or not self.bm25_index or not self.dense_vectorizer:
            return []

        # Stage 1: Multi-Query Expansion
        expanded_queries = self.expander.expand_query(query)

        # Stage 2: Sparse & Dense Retrieval across expanded queries
        N = len(self.chunks)
        bm25_ranks = {i: float("inf") for i in range(N)}
        dense_ranks = {i: float("inf") for i in range(N)}

        for eq in expanded_queries:
            # Sparse BM25 scores
            q_tokens = _tokenize(eq)
            bm25_scores = self.bm25_index.get_scores(q_tokens)
            sorted_bm25_indices = sorted(range(N), key=lambda i: bm25_scores[i], reverse=True)
            for rank, idx in enumerate(sorted_bm25_indices):
                if bm25_scores[idx] > 0 and rank < bm25_ranks[idx]:
                    bm25_ranks[idx] = rank

            # Dense Vector Similarity scores
            dense_scores = self.dense_vectorizer.score_query(eq)
            sorted_dense_indices = sorted(range(N), key=lambda i: dense_scores[i], reverse=True)
            for rank, idx in enumerate(sorted_dense_indices):
                if dense_scores[idx] > 0 and rank < dense_ranks[idx]:
                    dense_ranks[idx] = rank

        # Stage 3: Reciprocal Rank Fusion (RRF)
        # Formula: RRF = 1/(60 + r_bm25) + 1/(60 + r_dense)
        rrf_scores: dict[int, float] = {}
        K = 60.0
        for i in range(N):
            r_bm = bm25_ranks[i]
            r_dn = dense_ranks[i]

            score_bm = 1.0 / (K + r_bm) if r_bm != float("inf") else 0.0
            score_dn = 1.0 / (K + r_dn) if r_dn != float("inf") else 0.0

            if score_bm > 0 or score_dn > 0:
                rrf_scores[i] = score_bm + score_dn

        # Stage 4: Re-Ranking Stage (Exact PM Counter & Heading Match Boost)
        q_tokens_set = set(_tokenize(query))
        counter_pattern = re.compile(r'\b(pm[A-Za-z0-9_]+|PMRRCCONNESTAB[A-Z]+|PMERAB[A-Z]+|PMPDCP[A-Z]+|PMCELLDOWNTIME[A-Z]+)\b')
        query_counters = set(counter_pattern.findall(query))

        reranked: list[tuple[int, float]] = []
        for idx, base_rrf in rrf_scores.items():
            chunk = self.chunks[idx]
            boost = 1.0

            # Boost exact PM counter name matches
            chunk_counters = set(counter_pattern.findall(chunk.text))
            if query_counters and (query_counters & chunk_counters):
                boost *= 1.5

            # Boost section title match
            title_tokens = set(_tokenize(chunk.section_title))
            if q_tokens_set & title_tokens:
                boost *= 1.25

            final_score = base_rrf * boost
            reranked.append((idx, final_score))

        reranked.sort(key=lambda x: x[1], reverse=True)

        # Output formatting
        results = []
        for idx, score in reranked[:max_sections]:
            chunk = self.chunks[idx]
            results.append({
                "doc_name": chunk.doc_name,
                "page_number": chunk.page_number,
                "section_title": chunk.section_title,
                "content": chunk.text,
                "relevance_score": round(score, 5),
            })

        return results
