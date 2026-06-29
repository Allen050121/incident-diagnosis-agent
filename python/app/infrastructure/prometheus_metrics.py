"""Prometheus-backed metrics provider for query_metrics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


def _job_for_service(service: str) -> str:
    """Map incident service names to Prometheus job names."""
    return service or "order-service"


@dataclass(frozen=True)
class PromQuery:
    promql: str
    unit: str
    baseline: float
    scale: float = 1.0


class PrometheusMetricsProvider:
    """Query whitelisted metrics from Prometheus.

    The diagnosis graph expects normalized metric payloads:
    metric/current/baseline/unit. This provider keeps PromQL hidden behind
    the tool boundary so the agent cannot execute arbitrary queries.
    """

    def __init__(self, base_url: str, timeout_seconds: float = 5.0):
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    async def execute(self, parameters: dict) -> dict:
        metric = parameters.get("metric", "")
        service = parameters.get("service", "order-service")
        query = self._build_query(metric, service)

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.get(
                f"{self.base_url}/api/v1/query",
                params={"query": query.promql},
            )
            response.raise_for_status()
            payload = response.json()

        series = payload.get("data", {}).get("result", [])
        current = self._extract_value(series) * query.scale

        return {
            "metric": metric,
            "service": service,
            "current": current,
            "baseline": query.baseline,
            "unit": query.unit,
            "source": "prometheus",
            "promql": query.promql,
            "series_count": len(series),
            "raw_series": series[:5],
            "truncated": len(series) > 5,
        }

    def _build_query(self, metric: str, service: str) -> PromQuery:
        job = _job_for_service(service)
        escaped_job = job.replace("\\", "\\\\").replace('"', '\\"')

        queries = {
            "request_rate": PromQuery(
                promql=(
                    "sum(rate(http_server_requests_seconds_count"
                    f'{{job="{escaped_job}"}}[1m]))'
                ),
                unit="requests_per_second",
                baseline=20.0,
            ),
            "error_rate": PromQuery(
                promql=(
                    "sum(rate(http_server_requests_seconds_count"
                    f'{{job="{escaped_job}",status=~"5.."}}[1m])) '
                    "/ clamp_min(sum(rate(http_server_requests_seconds_count"
                    f'{{job="{escaped_job}"}}[1m])), 0.001)'
                ),
                unit="ratio",
                baseline=0.01,
            ),
            "latency_p50": PromQuery(
                promql=f'max(max_over_time(http_server_requests_seconds_max{{job="{escaped_job}"}}[10m]))',
                unit="ms",
                baseline=100.0,
                scale=1000.0,
            ),
            "latency_p95": PromQuery(
                promql=f'max(max_over_time(http_server_requests_seconds_max{{job="{escaped_job}"}}[10m]))',
                unit="ms",
                baseline=200.0,
                scale=1000.0,
            ),
            "jvm_threads_active": PromQuery(
                promql=f'max(jvm_threads_live_threads{{job="{escaped_job}"}})',
                unit="threads",
                baseline=50.0,
            ),
            "db_pool_active_ratio": PromQuery(
                promql=(
                    f'max(hikaricp_connections_active{{job="{escaped_job}"}}) '
                    f'/ clamp_min(max(hikaricp_connections_max{{job="{escaped_job}"}}), 1)'
                ),
                unit="ratio",
                baseline=0.5,
            ),
            "redis_latency_p95": PromQuery(
                promql=f'max(max_over_time(http_server_requests_seconds_max{{job="{escaped_job}"}}[10m]))',
                unit="ms",
                baseline=100.0,
                scale=1000.0,
            ),
            "downstream_latency_p95": PromQuery(
                promql='max(max_over_time(http_server_requests_seconds_max{job="payment-mock-service"}[10m]))',
                unit="ms",
                baseline=200.0,
                scale=1000.0,
            ),
            "mq_lag": PromQuery(
                promql=f'max(rocketmq_consumer_lag{{job="{escaped_job}"}}) or vector(0)',
                unit="messages",
                baseline=0.0,
            ),
        }

        if metric not in queries:
            raise ValueError(f"Unsupported metric for Prometheus provider: {metric}")
        return queries[metric]

    @staticmethod
    def _extract_value(series: list[dict[str, Any]]) -> float:
        values = []
        for item in series:
            value = item.get("value", [])
            if len(value) >= 2:
                try:
                    values.append(float(value[1]))
                except (TypeError, ValueError):
                    continue
        return max(values) if values else 0.0
