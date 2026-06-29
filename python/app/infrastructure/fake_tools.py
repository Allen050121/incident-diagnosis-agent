"""Fake tool providers for unit testing - return deterministic mock data"""

from datetime import UTC, datetime, timedelta


def _scenario_matches(scenario: str, *names: str) -> bool:
    return scenario in names


class FakeLogProvider:
    """Returns mock log data for testing"""

    def __init__(self, scenario: str = "default"):
        self.scenario = scenario

    async def execute(self, parameters: dict) -> dict:
        service = parameters.get("service", "unknown")
        max_results = parameters.get("max_results", 10)

        if _scenario_matches(self.scenario, "mysql_slow_query", "mysql-slow-query"):
            logs = [
                {"timestamp": datetime.now(UTC).isoformat(), "level": "ERROR",
                 "message": "SQLSlowQueryException: query execution exceeded threshold (1823ms)",
                 "trace_id": "trace-abc-001", "service": service},
                {"timestamp": datetime.now(UTC).isoformat(), "level": "WARN",
                 "message": "Slow query detected: SELECT * FROM orders WHERE status='PENDING'",
                 "trace_id": "trace-abc-001", "service": service},
                {"timestamp": datetime.now(UTC).isoformat(), "level": "ERROR",
                 "message": "HikariPool - Connection is not available, request timed out",
                 "trace_id": "trace-abc-002", "service": service},
            ]
        elif _scenario_matches(self.scenario, "mysql_connection_pool", "mysql-connection-pool"):
            logs = [
                {"timestamp": datetime.now(UTC).isoformat(), "level": "ERROR",
                 "message": "HikariPool - Connection is not available, request timed out after 30000ms",
                 "trace_id": "trace-dbpool-001", "service": service},
                {"timestamp": datetime.now(UTC).isoformat(), "level": "ERROR",
                 "message": "SQLTransientConnectionException: database connection pool exhausted",
                 "trace_id": "trace-dbpool-002", "service": service},
            ]
        elif _scenario_matches(self.scenario, "redis_timeout", "redis-timeout"):
            logs = [
                {"timestamp": datetime.now(UTC).isoformat(), "level": "ERROR",
                 "message": "RedisCommandTimeoutException: Command timed out after 3000ms",
                 "trace_id": "trace-red-001", "service": service},
                {"timestamp": datetime.now(UTC).isoformat(), "level": "WARN",
                 "message": "Redis connection pool exhausted",
                 "trace_id": "trace-red-001", "service": service},
            ]
        elif _scenario_matches(self.scenario, "redis_hot_key", "redis-hot-key"):
            logs = [
                {"timestamp": datetime.now(UTC).isoformat(), "level": "WARN",
                 "message": "Redis hot key detected: product:PROD-001 caused single key latency spike",
                 "trace_id": "trace-hotkey-001", "service": service},
                {"timestamp": datetime.now(UTC).isoformat(), "level": "ERROR",
                 "message": "RedisCommandTimeoutException: hot key access timed out after 1200ms",
                 "trace_id": "trace-hotkey-002", "service": service},
            ]
        elif _scenario_matches(
            self.scenario,
            "downstream_failure",
            "downstream-payment-timeout",
            "downstream-payment-5xx",
        ):
            logs = [
                {"timestamp": datetime.now(UTC).isoformat(), "level": "ERROR",
                 "message": "HttpClientErrorException: 503 Service Unavailable from payment-mock-service",
                 "trace_id": "trace-ds-001", "service": service},
            ]
        elif _scenario_matches(self.scenario, "http-connection-pool"):
            logs = [
                {"timestamp": datetime.now(UTC).isoformat(), "level": "ERROR",
                 "message": "HTTP connection pool full; connection refused by downstream client",
                 "trace_id": "trace-http-pool-001", "service": service},
            ]
        elif _scenario_matches(self.scenario, "thread-pool-full"):
            logs = [
                {"timestamp": datetime.now(UTC).isoformat(), "level": "WARN",
                 "message": "Tomcat executor thread pool full; request queued and rejected",
                 "trace_id": "trace-thread-001", "service": service},
            ]
        elif _scenario_matches(self.scenario, "config-error"):
            logs = [
                {"timestamp": datetime.now(UTC).isoformat(), "level": "ERROR",
                 "message": "ConfigurationException: required property payment.timeout missing",
                 "trace_id": "trace-config-001", "service": service},
            ]
        elif _scenario_matches(self.scenario, "deployment-npe"):
            logs = [
                {"timestamp": datetime.now(UTC).isoformat(), "level": "ERROR",
                 "message": "NullPointerException after deploying v1.2.4 in order processing",
                 "trace_id": "trace-npe-001", "service": service},
            ]
        elif _scenario_matches(self.scenario, "rate-limit-triggered"):
            logs = [
                {"timestamp": datetime.now(UTC).isoformat(), "level": "WARN",
                 "message": "Circuit breaker open; requests rate limited by resilience policy",
                 "trace_id": "trace-circuit-001", "service": service},
            ]
        elif _scenario_matches(self.scenario, "mq-consumer-lag"):
            logs = [
                {"timestamp": datetime.now(UTC).isoformat(), "level": "ERROR",
                 "message": "RocketMQ consumer lag growing; consumer processing errors detected",
                 "trace_id": "trace-mq-001", "service": service},
            ]
        else:
            logs = [
                {"timestamp": datetime.now(UTC).isoformat(), "level": "INFO",
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
            "mysql-connection-pool": {
                "db_pool_active_ratio": {"baseline": 0.4, "peak": 1.0, "current": 0.98, "unit": "ratio"},
                "error_rate": {"baseline": 0.001, "peak": 0.2, "current": 0.18, "unit": "ratio"},
            },
            "redis_timeout": {
                "redis_latency_p95": {"baseline": 2.0, "peak": 3200.0, "current": 3100.0, "unit": "ms"},
                "error_rate": {"baseline": 0.001, "peak": 0.08, "current": 0.07, "unit": "ratio"},
            },
            "redis-timeout": {
                "redis_latency_p95": {"baseline": 2.0, "peak": 3200.0, "current": 3100.0, "unit": "ms"},
                "latency_p95": {"baseline": 80.0, "peak": 3000.0, "current": 2800.0, "unit": "ms"},
            },
            "redis-hot-key": {
                "redis_latency_p95": {"baseline": 2.0, "peak": 1200.0, "current": 1100.0, "unit": "ms"},
                "latency_p95": {"baseline": 80.0, "peak": 900.0, "current": 850.0, "unit": "ms"},
            },
            "downstream_failure": {
                "downstream_latency_p95": {"baseline": 50.0, "peak": 5000.0, "current": 0.0, "unit": "ms"},
                "error_rate": {"baseline": 0.002, "peak": 0.25, "current": 0.22, "unit": "ratio"},
            },
            "downstream-payment-timeout": {
                "downstream_latency_p95": {"baseline": 50.0, "peak": 5000.0, "current": 4800.0, "unit": "ms"},
                "latency_p95": {"baseline": 100.0, "peak": 5200.0, "current": 5000.0, "unit": "ms"},
            },
            "downstream-payment-5xx": {
                "downstream_latency_p95": {"baseline": 50.0, "peak": 1000.0, "current": 0.0, "unit": "ms"},
                "error_rate": {"baseline": 0.002, "peak": 0.4, "current": 0.35, "unit": "ratio"},
            },
            "http-connection-pool": {
                "request_rate": {"baseline": 1000.0, "peak": 200.0, "current": 180.0, "unit": "rpm"},
                "http_pool_active_ratio": {"baseline": 0.4, "peak": 1.0, "current": 0.97, "unit": "ratio"},
            },
            "thread-pool-full": {
                "request_rate": {"baseline": 1000.0, "peak": 150.0, "current": 160.0, "unit": "rpm"},
                "jvm_thread_pool_active_ratio": {"baseline": 0.5, "peak": 1.0, "current": 0.99, "unit": "ratio"},
            },
            "config-error": {
                "error_rate": {"baseline": 0.001, "peak": 0.5, "current": 0.45, "unit": "ratio"},
            },
            "deployment-npe": {
                "error_rate": {"baseline": 0.001, "peak": 0.6, "current": 0.5, "unit": "ratio"},
            },
            "rate-limit-triggered": {
                "request_rate": {"baseline": 1000.0, "peak": 300.0, "current": 280.0, "unit": "rpm"},
                "rate_limit_rejections": {"baseline": 0.0, "peak": 800.0, "current": 700.0, "unit": "count"},
            },
            "mq-consumer-lag": {
                "mq_lag": {"baseline": 50.0, "peak": 25000.0, "current": 22000.0, "unit": "messages"},
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

        if self.scenario in {"recent_deploy", "deployment-npe"}:
            changes = (
                "Introduced NullPointerException in order processing after config refactor"
                if self.scenario == "deployment-npe"
                else "Modified order processing logic, added new query"
            )
            deployments = [
                {
                    "version": "v1.2.4",
                    "deployed_at": datetime.now(UTC).isoformat(),
                    "git_commit": "f9a2c1b",
                    "deployer": "yangjw",
                    "changes": changes,
                },
                {
                    "version": "v1.2.3",
                    "deployed_at": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
                    "git_commit": "abc1234",
                    "deployer": "yangjw",
                    "changes": "Fixed inventory caching bug",
                },
            ]
        else:
            deployments = [
                {
                    "version": "v1.2.3",
                    "deployed_at": (datetime.now(UTC) - timedelta(days=3)).isoformat(),
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
            {
                "runbook_id": "RB-004",
                "title": "Resource Exhaustion Diagnosis",
                "symptoms": ["thread pool full", "connection pool full", "rate limited", "circuit breaker"],
                "root_cause": "Application resource exhaustion or resilience guardrail triggered",
                "resolution": "Check thread pools, HTTP client pools, and rate-limit/circuit-breaker settings",
                "confidence_note": "Used for traffic saturation incidents",
            },
            {
                "runbook_id": "RB-005",
                "title": "MQ Consumer Lag",
                "symptoms": ["consumer lag", "message backlog", "RocketMQ"],
                "root_cause": "Consumer processing errors or insufficient consumer capacity",
                "resolution": "Check consumer errors, scale consumers, and inspect poison messages",
                "confidence_note": "Message backlog standard procedure",
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
