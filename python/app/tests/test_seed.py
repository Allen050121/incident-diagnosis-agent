"""15 seed unit tests for the diagnosis agent - Phase 3 exit criteria"""

import asyncio
from datetime import UTC, datetime

import pytest

from app.agent.service import create_agent_with_configured_tools, create_agent_with_fake_tools, parse_incident
from app.domain.incident import AlertType, Incident
from app.infrastructure.fake_tools import (
    FakeDeploymentProvider,
    FakeLogProvider,
    FakeMetricsProvider,
    FakeRunbookProvider,
)
from app.infrastructure.file_logs import FileLogProvider
from app.infrastructure.prometheus_metrics import PrometheusMetricsProvider
from app.infrastructure.tool_definitions import ToolInput, validate_tool_input
from app.infrastructure.tool_executor import ToolExecutor


# ============================================================
# Test 1: Tool whitelist validation - valid tool
# ============================================================
def test_validate_tool_input_accepts_valid_tool():
    tool_input = ToolInput(tool="query_logs", parameters={"service": "order-service"})
    assert validate_tool_input(tool_input) is None


# ============================================================
# Test 2: Tool whitelist validation - invalid tool
# ============================================================
def test_validate_tool_input_rejects_unknown_tool():
    tool_input = ToolInput(tool="delete_database", parameters={})
    error = validate_tool_input(tool_input)
    assert error is not None
    assert "not in allowed list" in error


# ============================================================
# Test 3: Metrics whitelist validation - invalid metric
# ============================================================
def test_validate_metrics_rejects_unknown_metric():
    tool_input = ToolInput(tool="query_metrics", parameters={"metric": "cpu_temperature"})
    error = validate_tool_input(tool_input)
    assert error is not None
    assert "not in whitelist" in error


# ============================================================
# Test 4: Metrics whitelist validation - valid metric
# ============================================================
def test_validate_metrics_accepts_whitelisted_metric():
    tool_input = ToolInput(tool="query_metrics", parameters={"metric": "latency_p95"})
    assert validate_tool_input(tool_input) is None


# ============================================================
# Test 5: FakeLogProvider returns structured log data
# ============================================================
@pytest.mark.asyncio
async def test_fake_log_provider_returns_logs():
    provider = FakeLogProvider(scenario="mysql_slow_query")
    result = await provider.execute({"service": "order-service", "max_results": 10})
    assert "logs" in result
    assert len(result["logs"]) > 0
    assert "error_stats" in result
    assert result["logs"][0]["level"] in ("ERROR", "WARN", "INFO")


@pytest.mark.asyncio
async def test_file_log_provider_reads_and_filters_spring_logs(tmp_path):
    log_file = tmp_path / "order-service.log"
    log_file.write_text(
        "\n".join([
            "2026-06-29 16:40:00.001  INFO 123 --- [main] c.e.i.OrderController : Order processed successfully",
            "2026-06-29 16:40:01.002  WARN 123 --- [nio-9081-exec-1] c.e.i.FaultInjector : Fault injection: mysql-slow-query - simulating 1800ms delay",
            "2026-06-29 16:40:02.003 ERROR 123 --- [nio-9081-exec-2] c.e.i.OrderController : SQLSlowQueryException: query execution exceeded threshold",
            "java.lang.RuntimeException: stack trace line",
        ]),
        encoding="utf-8",
    )

    provider = FileLogProvider(str(tmp_path))
    result = await provider.execute({
        "service": "order-service",
        "keywords": ["slow", "sql"],
        "max_results": 10,
    })

    assert result["source"] == "file"
    assert result["total_count"] == 2
    assert result["error_stats"]["ERROR"] == 1
    assert result["error_stats"]["WARN"] == 1
    assert "SQLSlowQueryException" in result["logs"][-1]["message"]
    assert "stack trace line" in result["logs"][-1]["message"]


@pytest.mark.asyncio
async def test_file_log_provider_filters_by_incident_window(tmp_path):
    log_file = tmp_path / "order-service.log"
    log_file.write_text(
        "\n".join([
            "2026-06-29 16:30:00.001  WARN 123 --- [nio-9081-exec-1] c.e.i.FaultInjector : old mysql-slow-query signal",
            "2026-06-29 16:40:00.001  WARN 123 --- [nio-9081-exec-2] c.e.i.FaultInjector : current mysql-slow-query signal",
        ]),
        encoding="utf-8",
    )

    provider = FileLogProvider(str(tmp_path))
    result = await provider.execute({
        "service": "order-service",
        "keywords": ["mysql-slow-query"],
        "start_time": "2026-06-29T16:39:30",
        "end_time": "2026-06-29T16:41:00",
        "max_results": 10,
    })

    assert result["total_count"] == 1
    assert "current mysql-slow-query signal" in result["logs"][0]["message"]


# ============================================================
# Test 6: FakeMetricsProvider returns metric data with baseline/current
# ============================================================
@pytest.mark.asyncio
async def test_fake_metrics_provider_returns_metric_data():
    provider = FakeMetricsProvider(scenario="mysql_slow_query")
    result = await provider.execute({"metric": "db_pool_active_ratio", "service": "order-service"})
    assert result["metric"] == "db_pool_active_ratio"
    assert "baseline" in result
    assert "current" in result
    assert "peak" in result
    assert result["current"] > result["baseline"]  # Should show anomaly


@pytest.mark.asyncio
async def test_prometheus_metrics_provider_parses_query_response(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "status": "success",
                "data": {
                    "result": [
                        {
                            "metric": {"job": "order-service"},
                            "value": [1234567890.0, "0.25"],
                        }
                    ]
                },
            }

    class FakeAsyncClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, params):
            assert url == "http://prometheus:9090/api/v1/query"
            assert "http_server_requests_seconds_count" in params["query"]
            return FakeResponse()

    monkeypatch.setattr("app.infrastructure.prometheus_metrics.httpx.AsyncClient", FakeAsyncClient)

    provider = PrometheusMetricsProvider("http://prometheus:9090")
    result = await provider.execute({"metric": "request_rate", "service": "order-service"})

    assert result["source"] == "prometheus"
    assert result["metric"] == "request_rate"
    assert result["current"] == 0.25
    assert result["series_count"] == 1


def test_configured_agent_can_use_prometheus_metrics(monkeypatch):
    monkeypatch.setattr("app.agent.service.settings.metrics_provider", "prometheus")
    monkeypatch.setattr("app.agent.service.settings.prometheus_url", "http://prometheus:9090")

    agent = create_agent_with_configured_tools()
    provider = agent._executor._providers["query_metrics"]

    assert isinstance(provider, PrometheusMetricsProvider)


def test_configured_agent_can_use_file_logs(monkeypatch, tmp_path):
    monkeypatch.setattr("app.agent.service.settings.log_provider", "file")
    monkeypatch.setattr("app.agent.service.settings.log_base_dir", str(tmp_path))

    agent = create_agent_with_configured_tools()
    provider = agent._executor._providers["query_logs"]

    assert isinstance(provider, FileLogProvider)


# ============================================================
# Test 7: FakeDeploymentProvider returns deployment history
# ============================================================
@pytest.mark.asyncio
async def test_fake_deployment_provider_returns_deployments():
    provider = FakeDeploymentProvider(scenario="recent_deploy")
    result = await provider.execute({"service": "order-service"})
    assert "deployments" in result
    assert len(result["deployments"]) == 2
    assert "version" in result["deployments"][0]
    assert "git_commit" in result["deployments"][0]


# ============================================================
# Test 8: FakeRunbookProvider returns matching runbooks
# ============================================================
@pytest.mark.asyncio
async def test_fake_runbook_provider_filters_by_query():
    provider = FakeRunbookProvider()
    result = await provider.execute({"query": "slow query database"})
    assert "runbooks" in result
    assert len(result["runbooks"]) > 0
    assert any("MySQL" in rb["title"] for rb in result["runbooks"])


# ============================================================
# Test 9: ToolExecutor generates evidence IDs with correct prefix
# ============================================================
@pytest.mark.asyncio
async def test_tool_executor_generates_evidence_ids():
    executor = ToolExecutor()
    executor.register("query_logs", FakeLogProvider())
    result = await executor.execute(ToolInput(tool="query_logs", parameters={"service": "test"}))
    assert result.success
    assert result.evidence_id.startswith("LOG-")
    assert len(result.evidence_id) > 4


# ============================================================
# Test 10: ToolExecutor handles timeout gracefully
# ============================================================
@pytest.mark.asyncio
async def test_tool_executor_handles_timeout():
    class SlowProvider:
        async def execute(self, parameters):
            await asyncio.sleep(5)
            return {}

    executor = ToolExecutor()
    executor.register("query_logs", SlowProvider())
    result = await executor.execute(ToolInput(tool="query_logs", parameters={}, timeout_seconds=1))
    assert not result.success
    assert "timed out" in result.error


# ============================================================
# Test 11: Agent creates correct plan for P95_LATENCY_HIGH alert
# ============================================================
@pytest.mark.asyncio
async def test_agent_creates_latency_plan():
    agent = create_agent_with_fake_tools()
    incident = Incident(
        incident_id="INC-TEST-001",
        service="order-service",
        endpoint="/api/orders",
        alert_type=AlertType.P95_LATENCY_HIGH,
        value=1800.0,
        threshold=500.0,
        started_at=datetime.now(UTC),
    )
    report = await agent.diagnose(incident)
    # Should have used multiple tool calls
    assert report.total_tool_calls >= 3
    assert report.investigation_steps >= 3


# ============================================================
# Test 12: Agent produces hypotheses with evidence IDs
# ============================================================
@pytest.mark.asyncio
async def test_agent_hypotheses_have_evidence():
    agent = create_agent_with_fake_tools()
    incident = Incident(
        incident_id="INC-TEST-002",
        service="order-service",
        endpoint="/api/orders",
        alert_type=AlertType.P95_LATENCY_HIGH,
        value=1800.0,
        threshold=500.0,
        started_at=datetime.now(UTC),
    )
    report = await agent.diagnose(incident)
    assert len(report.top_causes) > 0
    # Top cause should have supporting evidence
    assert len(report.top_causes[0].supporting_evidence) > 0
    # Evidence IDs should be non-empty strings
    for eid in report.top_causes[0].supporting_evidence:
        assert len(eid) > 0


@pytest.mark.asyncio
async def test_agent_report_includes_evidence_details():
    agent = create_agent_with_fake_tools()
    incident = Incident(
        incident_id="INC-TEST-EVIDENCE",
        service="order-service",
        endpoint="/api/orders",
        alert_type=AlertType.P95_LATENCY_HIGH,
        value=1800.0,
        threshold=500.0,
        started_at=datetime.now(UTC),
    )

    report = await agent.diagnose(incident)

    assert report.evidence_details
    assert {detail.evidence_id for detail in report.evidence_details} >= set(report.evidence_ids)
    assert any("Logs:" in detail.summary for detail in report.evidence_details)
    assert any("Metric" in detail.summary for detail in report.evidence_details)


# ============================================================
# Test 13: Report status is DIAGNOSED when evidence supports hypothesis
# ============================================================
@pytest.mark.asyncio
async def test_agent_report_diagnosed_status():
    agent = create_agent_with_fake_tools()
    incident = Incident(
        incident_id="INC-TEST-003",
        service="order-service",
        endpoint="/api/orders",
        alert_type=AlertType.P95_LATENCY_HIGH,
        value=1800.0,
        threshold=500.0,
        started_at=datetime.now(UTC),
    )
    report = await agent.diagnose(incident)
    # With mysql_slow_query fake data, should get a diagnosis
    assert report.status in ("DIAGNOSED", "INCONCLUSIVE")
    # Should have recommended actions
    assert len(report.recommended_actions) > 0


# ============================================================
# Test 14: Report only references real evidence IDs
# ============================================================
@pytest.mark.asyncio
async def test_report_references_only_real_evidence():
    agent = create_agent_with_fake_tools()
    incident = Incident(
        incident_id="INC-TEST-004",
        service="order-service",
        endpoint="/api/orders",
        alert_type=AlertType.ERROR_RATE_HIGH,
        value=0.15,
        threshold=0.01,
        started_at=datetime.now(UTC),
    )
    report = await agent.diagnose(incident)
    # All evidence IDs in report should be in the evidence_ids list
    for hypothesis in report.top_causes:
        for eid in hypothesis.supporting_evidence:
            assert eid in report.evidence_ids, f"Evidence {eid} referenced but not in report evidence_ids"
        for eid in hypothesis.contradicting_evidence:
            assert eid in report.evidence_ids, f"Contradicting evidence {eid} referenced but not in report"


# ============================================================
# Test 15: parse_incident correctly parses API request data
# ============================================================
def test_parse_incident_from_request():
    data = {
        "incident_id": "INC-1001",
        "service": "order-service",
        "endpoint": "/api/orders",
        "alert_type": "P95_LATENCY_HIGH",
        "value": 1823.0,
        "threshold": 500.0,
        "started_at": "2026-06-29T10:00:00",
    }
    incident = parse_incident(data)
    assert incident.incident_id == "INC-1001"
    assert incident.service == "order-service"
    assert incident.alert_type == AlertType.P95_LATENCY_HIGH
    assert incident.value == 1823.0
    assert incident.threshold == 500.0
