"""Diagnosis service - wires together the agent, tools, and API"""

from datetime import datetime

from app.agent.graph import DiagnosisAgent
from app.domain.incident import AlertType, Incident
from app.infrastructure.fake_tools import (
    FakeDeploymentProvider,
    FakeLogProvider,
    FakeMetricsProvider,
    FakeRunbookProvider,
)
from app.infrastructure.tool_executor import ToolExecutor
from app.infrastructure.tool_providers import (
    HttpDeploymentProvider,
    HttpLogProvider,
    HttpMetricsProvider,
    HttpRunbookProvider,
)


def create_agent_with_fake_tools() -> DiagnosisAgent:
    """Create a diagnosis agent using fake tools for testing"""
    executor = ToolExecutor()
    executor.register("query_logs", FakeLogProvider(scenario="mysql_slow_query"))
    executor.register("query_metrics", FakeMetricsProvider(scenario="mysql_slow_query"))
    executor.register("query_deployments", FakeDeploymentProvider(scenario="default"))
    executor.register("search_runbooks", FakeRunbookProvider())
    return DiagnosisAgent(tool_executor=executor, max_tool_calls=10)


def create_agent_with_real_tools(platform_url: str | None = None) -> DiagnosisAgent:
    """Create a diagnosis agent using real Java platform APIs"""
    executor = ToolExecutor()
    executor.register("query_logs", HttpLogProvider(base_url=platform_url))
    executor.register("query_metrics", HttpMetricsProvider(base_url=platform_url))
    executor.register("query_deployments", HttpDeploymentProvider(base_url=platform_url))
    executor.register("search_runbooks", HttpRunbookProvider(base_url=platform_url))
    return DiagnosisAgent(tool_executor=executor, max_tool_calls=10)


def parse_incident(data: dict) -> Incident:
    """Parse an incident from API request data"""
    alert_type_str = data.get("alert_type", "P95_LATENCY_HIGH")
    try:
        alert_type = AlertType(alert_type_str)
    except ValueError:
        alert_type = AlertType.P95_LATENCY_HIGH

    started_at_str = data.get("started_at", "")
    try:
        started_at = datetime.fromisoformat(started_at_str)
    except (ValueError, TypeError):
        started_at = datetime.utcnow()

    return Incident(
        incident_id=data.get("incident_id", "INC-UNKNOWN"),
        service=data.get("service", "unknown"),
        endpoint=data.get("endpoint"),
        alert_type=alert_type,
        value=float(data.get("value", 0)),
        threshold=float(data.get("threshold", 0)),
        started_at=started_at,
    )
