"""Fake tool providers for unit testing - return deterministic mock data"""

from datetime import datetime, timedelta


class FakeLogProvider:
    """Returns mock log data for testing"""

    def __init__(self, scenario: str = "default"):
        self.scenario = scenario

    async def execute(self, parameters: dict) -> dict:
        service = parameters.get("service", "unknown")
        keywords = parameters.get("keywords", [])
        max_results = parameters.get("max_results", 10)

        if self.scenario == "mysql_slow_query":
            logs = [
                {"timestamp": datetime.utcnow().isoformat(), "level": "ERROR",
                 "message": "SQLSlowQueryException: query execution exceeded threshold (1823ms)",
                 "trace_id": "trace-abc-001", "service": service},
                {"timestamp": datetime.utcnow().isoformat(), "level": "WARN",
                 "message": "Slow query detected: SELECT * FROM orders WHERE status='PENDING'",
                 "trace_id": "trace-abc-001", "service": service},
                {"timestamp": datetime.utcnow().isoformat(), "level": "ERROR",
                 "message": "HikariPool - Connection is not available, request timed out",
                 "trace_id": "trace-abc-002", "service": service},
            ]
        elif self.scenario == "redis_timeout":
            logs = [
                {"timestamp": datetime.utcnow().isoformat(), "level": "ERROR",
                 "message": "RedisCommandTimeoutException: Command timed out after 3000ms",
                 "trace_id": "trace-red-001", "service": service},
                {"timestamp": datetime.utcnow().isoformat(), "level": "WARN",
                 "message": "Redis connection pool exhausted",
                 "trace_id": "trace-red-001", "service": service},
            ]
        elif self.scenario == "downstream_failure":
            logs = [
                {"timestamp": datetime.utcnow().isoformat(), "level": "ERROR",
                 "message": "HttpClientErrorException: 503 Service Unavailable from inventory-service",
                 "trace_id": "trace-ds-001", "service": service},
            ]
        else:
            logs = [
                {"timestamp": datetime.utcnow().isoformat(), "level": "INFO",
                 "message": "Order processed successfully",
                 "trace_id": "trace-ok-001", "service": service},
            ]

        truncated = len(logs) > max_results
        return {
            "logs": logs[:max_results],
            "total_count": len(logs),
            "error_stats": _count_by_level(logs),
            "truncated": truncated,
        }


class FakeMetricsProvider:
    """Returns mock metrics data for testing"""

    def __init__(self, scenario: str = "default"):
        self.scenario = scenario

    async def execute(self, parameters: dict) -> dict:
        metric = parameters.get("metric", "latency_p95")
        service = parameters.get("service", "unknown")

        scenarios = {
            "mysql_slow_query": {
                "db_pool_active_ratio": {"baseline": 0.4, "peak": 0.98, "current": 0.95, "unit": "ratio"},
                "latency_p95": {"baseline": 120.0, "peak": 1823.0, "current": 1750.0, "unit": "ms"},
                "error_rate": {"baseline": 0.001, "peak": 0.15, "current": 0.12, "unit": "ratio"},
            },
            "redis_timeout": {
                "redis_latency_p95": {"baseline": 2.0, "peak": 3200.0, "current": 3100.0, "unit": "ms"},
                "error_rate": {"baseline": 0.001, "peak": 0.08, "current": 0.07, "unit": "ratio"},
            },
            "downstream_failure": {
                "downstream_latency_p95": {"baseline": 50.0, "peak": 5000.0, "current": 0.0, "unit": "ms"},
                "error_rate": {"baseline": 0.002, "peak": 0.25, "current": 0.22, "unit": "ratio"},
            },
            "default": {
                metric: {"baseline": 0.5, "peak": 0.7, "current": 0.6, "unit": "unknown"},
            },
        }

        data = scenarios.get(self.scenario, scenarios["default"])
        metric_data = data.get(metric, {"baseline": 0.0, "peak": 0.0, "current": 0.0, "unit": "unknown"})

        return {
            "metric": metric,
            "service": service,
            **metric_data,
            "samples": 100,
        }


class FakeDeploymentProvider:
    """Returns mock deployment data for testing"""

    def __init__(self, scenario: str = "default"):
        self.scenario = scenario

    async def execute(self, parameters: dict) -> dict:
        service = parameters.get("service", "unknown")

        if self.scenario == "recent_deploy":
            deployments = [
                {
                    "version": "v1.2.4",
                    "deployed_at": datetime.utcnow().isoformat(),
                    "git_commit": "f9a2c1b",
                    "deployer": "yangjw",
                    "changes": "Modified order processing logic, added new query",
                },
                {
                    "version": "v1.2.3",
                    "deployed_at": (datetime.utcnow() - timedelta(days=1)).isoformat(),
                    "git_commit": "abc1234",
                    "deployer": "yangjw",
                    "changes": "Fixed inventory caching bug",
                },
            ]
        else:
            deployments = [
                {
                    "version": "v1.2.3",
                    "deployed_at": (datetime.utcnow() - timedelta(days=3)).isoformat(),
                    "git_commit": "abc1234",
                    "deployer": "yangjw",
                    "changes": "Fixed inventory caching bug",
                },
            ]

        return {
            "service": service,
            "deployments": deployments,
            "total_count": len(deployments),
        }


class FakeRunbookProvider:
    """Returns mock runbook data for testing"""

    def __init__(self, scenario: str = "default"):
        self.scenario = scenario

    async def execute(self, parameters: dict) -> dict:
        query = parameters.get("query", "")

        runbooks = [
            {
                "runbook_id": "RB-001",
                "title": "MySQL Slow Query Diagnosis",
                "symptoms": ["slow query", "db_pool", "connection timeout"],
                "root_cause": "Missing database index causing full table scan",
                "resolution": "Add index to orders.status column; optimize query plan",
                "confidence_note": "Verified in production incident INC-0892",
            },
            {
                "runbook_id": "RB-002",
                "title": "Redis Connection Timeout",
                "symptoms": ["redis timeout", "connection pool exhausted"],
                "root_cause": "Redis connection pool size too small for traffic spike",
                "resolution": "Increase spring.redis.pool.max-active; check for slow commands",
                "confidence_note": "Based on incident INC-0756",
            },
            {
                "runbook_id": "RB-003",
                "title": "Downstream Service 503",
                "symptoms": ["503", "service unavailable", "circuit breaker"],
                "root_cause": "Downstream service overloaded or crashed",
                "resolution": "Check downstream service health; verify circuit breaker configuration",
                "confidence_note": "Standard procedure",
            },
        ]

        # Filter by query keywords
        if query:
            keywords = query.lower().split()
            runbooks = [
                rb for rb in runbooks
                if any(kw in rb["title"].lower() or kw in " ".join(rb["symptoms"]).lower()
                       for kw in keywords)
            ]

        return {
            "runbooks": runbooks,
            "total_count": len(runbooks),
            "truncated": False,
        }


def _count_by_level(logs: list[dict]) -> dict:
    counts = {}
    for log in logs:
        level = log.get("level", "UNKNOWN")
        counts[level] = counts.get(level, 0) + 1
    return counts
