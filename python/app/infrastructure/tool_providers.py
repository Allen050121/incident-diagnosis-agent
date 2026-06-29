"""Real tool providers that call Java incident-platform APIs"""

import httpx
from app.config import settings


class HttpLogProvider:
    """Calls POST /internal/v1/logs/query on incident-platform"""

    def __init__(self, base_url: str | None = None):
        self._base_url = base_url or settings.platform_url

    async def execute(self, parameters: dict) -> dict:
        payload = {
            "service": parameters.get("service", ""),
            "startTime": parameters.get("start_time", ""),
            "endTime": parameters.get("end_time", ""),
            "keywords": parameters.get("keywords", []),
            "maxResults": parameters.get("max_results", 50),
        }
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(f"{self._base_url}/internal/v1/logs/query", json=payload)
            resp.raise_for_status()
            return resp.json()


class HttpMetricsProvider:
    """Calls POST /internal/v1/metrics/query on incident-platform"""

    def __init__(self, base_url: str | None = None):
        self._base_url = base_url or settings.platform_url

    async def execute(self, parameters: dict) -> dict:
        payload = {
            "metric": parameters.get("metric", ""),
            "service": parameters.get("service", ""),
            "startTime": parameters.get("start_time", ""),
            "endTime": parameters.get("end_time", ""),
        }
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(f"{self._base_url}/internal/v1/metrics/query", json=payload)
            resp.raise_for_status()
            return resp.json()


class HttpDeploymentProvider:
    """Calls POST /internal/v1/deployments/query on incident-platform"""

    def __init__(self, base_url: str | None = None):
        self._base_url = base_url or settings.platform_url

    async def execute(self, parameters: dict) -> dict:
        payload = {
            "service": parameters.get("service", ""),
            "startTime": parameters.get("start_time", ""),
            "endTime": parameters.get("end_time", ""),
            "maxResults": parameters.get("max_results", 10),
        }
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(f"{self._base_url}/internal/v1/deployments/query", json=payload)
            resp.raise_for_status()
            return resp.json()


class HttpRunbookProvider:
    """Calls POST /internal/v1/runbooks/search on incident-platform (fallback to local if not available)"""

    def __init__(self, base_url: str | None = None):
        self._base_url = base_url or settings.platform_url

    async def execute(self, parameters: dict) -> dict:
        payload = {
            "query": parameters.get("query", ""),
            "service": parameters.get("service", ""),
            "maxResults": parameters.get("max_results", 5),
        }
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(f"{self._base_url}/internal/v1/runbooks/search", json=payload)
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError:
            # Fallback: return empty if endpoint not implemented yet
            return {"runbooks": [], "total_count": 0, "truncated": False}
