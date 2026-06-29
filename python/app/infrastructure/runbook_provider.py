"""Runbook search tool provider - integrates BM25 search with the tool executor"""

from app.infrastructure.runbook_search import BM25Search
from app.infrastructure.runbook_store import RunbookStore


class RunbookSearchProvider:
    """Tool provider that uses BM25 search over the runbook store"""

    def __init__(self, store: RunbookStore | None = None):
        from app.infrastructure.runbook_store import create_sample_runbooks
        self._store = store or create_sample_runbooks()
        self._search = BM25Search(self._store)

    async def execute(self, parameters: dict) -> dict:
        query = parameters.get("query", "")
        service = parameters.get("service", "")
        max_results = parameters.get("max_results", 5)

        results = self._search.search(query, top_k=max_results)

        # Filter by service if specified
        runbooks = []
        for r in results.results:
            if service and r.runbook.service != service:
                continue
            runbooks.append({
                "runbook_id": r.runbook.runbook_id,
                "title": r.runbook.title,
                "symptoms": r.runbook.symptoms,
                "root_cause": r.runbook.root_cause,
                "resolution": r.runbook.resolution,
                "confidence_note": r.runbook.confidence_note,
                "score": round(r.score, 3),
                "rank": r.rank,
                "status": r.runbook.status.value,
                "is_valid_evidence": r.runbook.is_usable_as_evidence(),
            })

        return {
            "runbooks": runbooks,
            "total_count": len(runbooks),
            "truncated": False,
        }
