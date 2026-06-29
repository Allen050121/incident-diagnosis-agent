"""Diagnosis service - wires together the agent, tools, and API"""

from datetime import UTC, datetime

from app.agent.graph import DiagnosisAgent
from app.agent.llm_graph import LLMDiagnosisAgent
from app.config import settings
from app.domain.incident import AlertType, Incident
from app.infrastructure.fake_tools import (
    FakeDeploymentProvider,
    FakeLogProvider,
    FakeMetricsProvider,
    FakeRunbookProvider,
)
from app.infrastructure.file_logs import FileLogProvider
from app.infrastructure.llm.client import LLMClient
from app.infrastructure.prometheus_metrics import PrometheusMetricsProvider
from app.infrastructure.tool_executor import ToolExecutor


def create_agent_with_fake_tools() -> DiagnosisAgent:
    """Create a diagnosis agent using fake tools for testing"""
    executor = ToolExecutor()
    executor.register("query_logs", FakeLogProvider(scenario="mysql_slow_query"))
    executor.register("query_metrics", FakeMetricsProvider(scenario="mysql_slow_query"))
    executor.register("query_deployments", FakeDeploymentProvider(scenario="default"))
    executor.register("search_runbooks", FakeRunbookProvider())
    return DiagnosisAgent(tool_executor=executor, max_tool_calls=10)


def create_agent_with_configured_tools() -> DiagnosisAgent:
    """Create a diagnosis agent using configured infrastructure providers."""
    executor = _create_configured_executor()
    return DiagnosisAgent(tool_executor=executor, max_tool_calls=settings.max_tool_calls)


def create_llm_agent_with_configured_tools() -> LLMDiagnosisAgent:
    """Create an LLM-powered diagnosis agent using configured providers."""
    executor = _create_configured_executor()
    llm = LLMClient(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        model=settings.llm_model,
    )
    fallback = DiagnosisAgent(tool_executor=executor, max_tool_calls=settings.max_tool_calls)
    return LLMDiagnosisAgent(
        tool_executor=executor,
        llm_client=llm,
        max_tool_calls=settings.max_tool_calls,
        rule_based_fallback=fallback,
    )


def create_agent_from_settings():
    """Create the configured rule or LLM agent based on AGENT_MODE."""
    if settings.agent_mode.lower() == "llm":
        return create_llm_agent_with_configured_tools()
    return create_agent_with_configured_tools()


def create_llm_agent_with_fake_tools() -> LLMDiagnosisAgent:
    """Create an LLM-powered diagnosis agent using fake tools for testing"""
    executor = ToolExecutor()
    executor.register("query_logs", FakeLogProvider(scenario="mysql_slow_query"))
    executor.register("query_metrics", FakeMetricsProvider(scenario="mysql_slow_query"))
    executor.register("query_deployments", FakeDeploymentProvider(scenario="default"))
    executor.register("search_runbooks", FakeRunbookProvider())
    llm = LLMClient(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        model=settings.llm_model,
    )
    fallback = DiagnosisAgent(tool_executor=executor, max_tool_calls=10)
    return LLMDiagnosisAgent(
        tool_executor=executor, llm_client=llm,
        max_tool_calls=10, rule_based_fallback=fallback,
    )


def _create_configured_executor() -> ToolExecutor:
    executor = ToolExecutor()
    if settings.log_provider.lower() == "file":
        executor.register("query_logs", FileLogProvider(settings.log_base_dir))
    else:
        executor.register("query_logs", FakeLogProvider(scenario="mysql_slow_query"))
    if settings.metrics_provider.lower() == "prometheus":
        executor.register("query_metrics", PrometheusMetricsProvider(settings.prometheus_url))
    else:
        executor.register("query_metrics", FakeMetricsProvider(scenario="mysql_slow_query"))
    executor.register("query_deployments", FakeDeploymentProvider(scenario="default"))
    executor.register("search_runbooks", FakeRunbookProvider())
    return executor


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
        started_at = datetime.now(UTC)

    return Incident(
        incident_id=data.get("incident_id", "INC-UNKNOWN"),
        service=data.get("service", "unknown"),
        endpoint=data.get("endpoint"),
        alert_type=alert_type,
        value=float(data.get("value", 0)),
        threshold=float(data.get("threshold", 0)),
        started_at=started_at,
    )
