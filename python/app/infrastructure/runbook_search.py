"""BM25-based runbook search with evaluation metrics

Implements:
  - BM25 text scoring for runbook retrieval
  - Recall@K, Precision@K, MRR evaluation metrics
  - Filtering by runbook status (only valid/active runbooks returned)
"""

import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

from app.infrastructure.runbook_store import Runbook, RunbookStore


@dataclass
class SearchResult:
    runbook: Runbook
    score: float
    rank: int = 0


@dataclass
class SearchResults:
    results: list[SearchResult] = field(default_factory=list)
    total: int = 0
    query: str = ""


class BM25Search:
    """BM25 text search over runbooks.

    Only returns runbooks that are usable as evidence (valid, non-expired).
    """

    def __init__(self, store: RunbookStore, k1: float = 1.5, b: float = 0.75):
        self._store = store
        self._k1 = k1
        self._b = b
        self._avg_dl: float = 0
        self._df: dict[str, int] = {}  # term -> document frequency
        self._doc_count: int = 0
        self._index: dict[str, dict[str, int]] = {}  # runbook_id -> {term: freq}
        self._rebuild_index()

    def _tokenize(self, text: str) -> list[str]:
        """Simple whitespace + punctuation tokenization with lowercasing"""
        import re
        text = text.lower()
        tokens = re.findall(r'[a-z0-9_\-]+', text)
        return [t for t in tokens if len(t) > 1]

    def _build_doc_text(self, runbook: Runbook) -> str:
        """Build searchable text from runbook fields"""
        parts = [
            runbook.title,
            " ".join(runbook.symptoms),
            runbook.root_cause,
            runbook.resolution,
            " ".join(runbook.tags),
            runbook.component,
        ]
        return " ".join(parts)

    def _rebuild_index(self):
        """Build BM25 index from active runbooks"""
        self._index.clear()
        self._df.clear()
        self._doc_count = 0

        active_runbooks = self._store.list_active()
        doc_lengths = []

        for rb in active_runbooks:
            text = self._build_doc_text(rb)
            tokens = self._tokenize(text)
            if not tokens:
                continue

            freq = Counter(tokens)
            self._index[rb.runbook_id] = dict(freq)
            doc_lengths.append(len(tokens))
            self._doc_count += 1

            # Update document frequency
            for term in set(tokens):
                self._df[term] = self._df.get(term, 0) + 1

        if doc_lengths:
            self._avg_dl = sum(doc_lengths) / len(doc_lengths)

    def search(self, query: str, top_k: int = 5) -> SearchResults:
        """Search runbooks using BM25 scoring"""
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return SearchResults(query=query)

        scores: list[tuple[str, float]] = []

        for rb_id, term_freqs in self._index.items():
            score = 0.0
            doc_len = sum(term_freqs.values())

            for token in query_tokens:
                if token not in term_freqs:
                    continue

                tf = term_freqs[token]
                df = self._df.get(token, 0)
                if df == 0:
                    continue

                # BM25 formula
                idf = math.log((self._doc_count - df + 0.5) / (df + 0.5) + 1)
                tf_norm = (tf * (self._k1 + 1)) / (tf + self._k1 * (1 - self._b + self._b * doc_len / self._avg_dl))
                score += idf * tf_norm

            if score > 0:
                rb = self._store.get_active(rb_id)
                if rb:
                    scores.append((rb_id, score))

        # Sort by score descending
        scores.sort(key=lambda x: x[1], reverse=True)

        results = []
        for rank, (rb_id, score) in enumerate(scores[:top_k], 1):
            rb = self._store.get_active(rb_id)
            if rb:
                results.append(SearchResult(runbook=rb, score=score, rank=rank))

        return SearchResults(results=results, total=len(scores), query=query)


def evaluate_recall_at_k(
    search_fn,
    queries: list[dict],
    k: int = 3,
) -> dict:
    """Evaluate Recall@K for a set of queries.

    queries: list of {"query": str, "relevant_ids": list[str]}
    Returns: {"recall@k": float, "details": list}
    """
    recalls = []
    details = []

    for q in queries:
        query = q["query"]
        relevant = set(q["relevant_ids"])
        if not relevant:
            continue

        results = search_fn(query, top_k=k)
        retrieved_ids = {r.runbook.runbook_id for r in results.results}

        hits = retrieved_ids & relevant
        recall = len(hits) / len(relevant) if relevant else 0.0
        recalls.append(recall)
        details.append({
            "query": query,
            "recall": recall,
            "hits": list(hits),
            "retrieved": list(retrieved_ids),
        })

    avg_recall = sum(recalls) / len(recalls) if recalls else 0.0
    return {"recall@k": avg_recall, "details": details}


def evaluate_mrr(
    search_fn,
    queries: list[dict],
) -> dict:
    """Evaluate Mean Reciprocal Rank (MRR).

    queries: list of {"query": str, "relevant_ids": list[str]}
    Returns: {"mrr": float, "details": list}
    """
    rrs = []
    details = []

    for q in queries:
        query = q["query"]
        relevant = set(q["relevant_ids"])
        if not relevant:
            continue

        results = search_fn(query, top_k=10)
        rr = 0.0
        for i, r in enumerate(results.results, 1):
            if r.runbook.runbook_id in relevant:
                rr = 1.0 / i
                break

        rrs.append(rr)
        details.append({"query": query, "rr": rr})

    mrr = sum(rrs) / len(rrs) if rrs else 0.0
    return {"mrr": mrr, "details": details}
