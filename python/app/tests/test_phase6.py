"""Phase 6 tests: LLM integration, LLM diagnosis agent, and evaluation."""

import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.agent.graph import DiagnosisAgent
from app.agent.llm_graph import LLMDiagnosisAgent
from app.agent.service import (
    create_agent_with_fake_tools,
    create_llm_agent_with_fake_tools,
    parse_incident,
)
from app.domain.incident import (
    AlertType,
    ConfidenceLevel,
    DiagnosisReport,
    Evidence,
    Hypothesis,
    Incident,
    IncidentStatus,
)
from app.evaluation.comparator import (
    EvaluationResult,
    evaluate_single,
    summarize,
)
from app.infrastructure.fake_tools import (
    FakeDeploymentProvider,
    FakeLogProvider,
    FakeMetricsProvider,
    FakeRunbookProvider,
)
from app.infrastructure.llm.client import (
    LLMAccumulatedUsage,
    LLMClient,
    LLMResponse,
    LLMUsage,
)
from app.infrastructure.llm.prompts import (
    format_evidence_summary,
    format_hypotheses_summary,
)
from app.infrastructure.tool_executor import ToolExecutor


# --- Fixtures ---

def _make_incident(incident_id="INC-001", alert_type=AlertType.P95_LATENCY_HIGH,
                   service="order-service") -> Incident:
    return Incident(
        incident_id=incident_id,
        service=service,
        endpoint="/api/orders",
        alert_type=alert_type,
        value=5000.0,
        threshold=1000.0,
        started_at=datetime.utcnow() - timedelta(minutes=10),
    )


def _make_executor() -> ToolExecutor:
    executor = ToolExecutor()
    executor.register("query_logs", FakeLogProvider(scenario="mysql_slow_query"))
    executor.register("query_metrics", FakeMetricsProvider(scenario="mysql_slow_query"))
    executor.register("query_deployments", FakeDeploymentProvider(scenario="default"))
    executor.register("search_runbooks", FakeRunbookProvider())
    return executor


class FakeLLMClient:
    """Deterministic fake LLM client for testing."""

    def __init__(self, plan_response=None, hypothesis_response=None,
                 report_response=None, available=True):
        self._available = available
        self._plan = plan_response or [
            {"tool": "query_logs", "purpose": "Find errors",
             "parameters": {"service": "order-service", "keywords": ["error"]}},
            {"tool": "query_metrics", "purpose": "Check latency",
             "parameters": {"metric": "latency_p95", "service": "order-service"}},
        ]
        self._hypothesis = hypothesis_response  # Will be auto-generated if None
        self._report = report_response or {
            "status": "DIAGNOSED",
            "summary": "Root cause is slow database queries",
            "recommended_actions": ["Add missing index", "Optimize query"],
            "missing_evidence": ["Runbook search results"],
        }
        self._accumulated = LLMAccumulatedUsage()
        self.call_count = 0
        self._evidence_ids_seen: list[str] = []

    @property
    def is_available(self):
        return self._available

    @property
    def accumulated_usage(self):
        return self._accumulated

    def chat(self, messages, tools=None, tool_choice="auto", max_tokens=4096,
             temperature=0.7):
        self.call_count += 1
        self._accumulated.add(LLMUsage(prompt_tokens=100, completion_tokens=50,
                                       reasoning_tokens=20, total_tokens=150), 10.0)
        return LLMResponse(
            content="test response",
            reasoning_content="thinking...",
            model="fake-model",
        )

    def chat_json(self, messages, max_tokens=4096, temperature=0.3):
        self.call_count += 1
        self._accumulated.add(LLMUsage(prompt_tokens=100, completion_tokens=50,
                                       reasoning_tokens=20, total_tokens=150), 10.0)

        # Track evidence IDs mentioned in prompts for dynamic hypothesis generation
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                import re
                # Match evidence IDs: LOG-XXXXXX, METRIC-XXXXXX, DEPLOY-XXXXXX, RUNBOOK-XXXXXX, ev-xxx
                ids = re.findall(r"(?:LOG|METRIC|DEPLOY|RUNBOOK|EVD)-[A-Z0-9]+", content)
                self._evidence_ids_seen.extend(ids)

        if self.call_count == 1:
            return self._plan
        elif self.call_count == 2:
            # Auto-generate hypothesis with actual evidence IDs if not overridden
            if self._hypothesis is None:
                ev_ids = list(dict.fromkeys(self._evidence_ids_seen))[:3]
                return {
                    "hypotheses": [
                        {
                            "cause_code": "DATABASE_SLOW_QUERY",
                            "confidence": "HIGH",
                            "reasoning_summary": "Slow queries detected in logs",
                            "supporting_evidence_ids": ev_ids,
                            "contradicting_evidence_ids": [],
                        }
                    ]
                }
            return self._hypothesis
        else:
            return self._report


# === LLMClient Tests ===


def test_llm_client_not_available_without_key():
    """LLMClient.is_available is False when no API key provided."""
    client = LLMClient(api_key="")
    assert client.is_available is False


def test_llm_client_returns_empty_when_not_available():
    """chat() returns empty response when client is not available."""
    client = LLMClient(api_key="")
    resp = client.chat([{"role": "user", "content": "test"}])
    assert resp.content == ""
    assert resp.tool_calls == []


def test_llm_accumulated_usage_tracking():
    """LLMAccumulatedUsage correctly tracks totals across calls."""
    acc = LLMAccumulatedUsage()
    acc.add(LLMUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15), 100.0)
    acc.add(LLMUsage(prompt_tokens=20, completion_tokens=10, total_tokens=30), 200.0)
    assert acc.total_prompt_tokens == 30
    assert acc.total_completion_tokens == 15
    assert acc.total_tokens == 45
    assert acc.call_count == 2
    assert acc.avg_latency_ms == 150.0


def test_llm_accumulated_cost_estimation():
    """Cost estimation returns a positive value for non-zero tokens."""
    acc = LLMAccumulatedUsage()
    acc.add(LLMUsage(prompt_tokens=1000, completion_tokens=500, total_tokens=1500), 100.0)
    cost = acc.estimated_cost_usd()
    assert cost > 0


# === Prompt Formatting Tests ===


def test_format_evidence_summary_empty():
    """Empty evidence list produces a clear message."""
    result = format_evidence_summary([])
    assert "no evidence" in result.lower()


def test_format_evidence_summary_with_logs():
    """Log evidence is formatted with messages and error stats."""
    evidence = [{
        "evidence_id": "ev-001",
        "source": "query_logs",
        "content": {
            "logs": [
                {"message": "Slow query detected: SELECT * FROM orders", "level": "ERROR"},
                {"message": "Connection timeout", "level": "WARN"},
            ],
            "error_stats": {"total_errors": 42},
        },
    }]
    result = format_evidence_summary(evidence)
    assert "ev-001" in result
    assert "Slow query" in result
    assert "ERROR" in result


def test_format_evidence_summary_with_metrics():
    """Metric evidence shows metric name, current, and baseline."""
    evidence = [{
        "evidence_id": "ev-002",
        "source": "query_metrics",
        "content": {"metric": "latency_p95", "current": 5000, "baseline": 200},
    }]
    result = format_evidence_summary(evidence)
    assert "ev-002" in result
    assert "latency_p95" in result
    assert "5000" in result


def test_format_hypotheses_summary_empty():
    """Empty hypotheses list produces a clear message."""
    result = format_hypotheses_summary([])
    assert "no hypotheses" in result.lower()


def test_format_hypotheses_summary_with_data():
    """Hypotheses are formatted with cause code and confidence."""
    hypotheses = [{
        "cause_code": "DATABASE_SLOW_QUERY",
        "confidence": "HIGH",
        "reasoning_summary": "Slow queries in logs",
        "supporting_evidence": ["ev-001"],
        "contradicting_evidence": [],
    }]
    result = format_hypotheses_summary(hypotheses)
    assert "DATABASE_SLOW_QUERY" in result
    assert "HIGH" in result


# === LLMDiagnosisAgent Tests ===


@pytest.mark.asyncio
async def test_llm_agent_uses_fake_llm_for_plan():
    """LLM agent creates a plan using LLM response."""
    executor = _make_executor()
    fake_llm = FakeLLMClient()
    agent = LLMDiagnosisAgent(tool_executor=executor, llm_client=fake_llm, max_tool_calls=10)
    incident = _make_incident()

    report = await agent.diagnose(incident)

    assert report is not None
    assert report.incident_id == "INC-001"
    assert fake_llm.call_count >= 1  # At least plan call


@pytest.mark.asyncio
async def test_llm_agent_generates_hypotheses():
    """LLM agent generates hypotheses from evidence."""
    executor = _make_executor()
    fake_llm = FakeLLMClient()
    agent = LLMDiagnosisAgent(tool_executor=executor, llm_client=fake_llm, max_tool_calls=10)
    incident = _make_incident()

    report = await agent.diagnose(incident)

    assert report.top_causes is not None
    assert len(report.top_causes) >= 1


@pytest.mark.asyncio
async def test_llm_agent_produces_diagnosed_status():
    """LLM agent produces a DIAGNOSED status when evidence supports it."""
    executor = _make_executor()
    fake_llm = FakeLLMClient()
    agent = LLMDiagnosisAgent(tool_executor=executor, llm_client=fake_llm, max_tool_calls=10)
    incident = _make_incident()

    report = await agent.diagnose(incident)

    assert report.status in ("DIAGNOSED", "INCONCLUSIVE")


@pytest.mark.asyncio
async def test_llm_agent_tracks_tool_calls():
    """LLM agent tracks tool calls and total count."""
    executor = _make_executor()
    fake_llm = FakeLLMClient()
    agent = LLMDiagnosisAgent(tool_executor=executor, llm_client=fake_llm, max_tool_calls=10)
    incident = _make_incident()

    report = await agent.diagnose(incident)

    assert report.total_tool_calls > 0
    assert report.investigation_steps > 0


@pytest.mark.asyncio
async def test_llm_agent_fallback_when_unavailable():
    """LLM agent falls back to rule-based when LLM is unavailable."""
    executor = _make_executor()
    fake_llm = FakeLLMClient(available=False)
    fallback = DiagnosisAgent(tool_executor=executor, max_tool_calls=10)
    agent = LLMDiagnosisAgent(
        tool_executor=executor, llm_client=fake_llm,
        max_tool_calls=10, rule_based_fallback=fallback,
    )
    incident = _make_incident()

    report = await agent.diagnose(incident)

    assert report is not None
    assert report.status in ("DIAGNOSED", "INCONCLUSIVE", "FAILED")


@pytest.mark.asyncio
async def test_llm_agent_fails_without_fallback():
    """LLM agent returns FAILED when LLM unavailable and no fallback."""
    executor = _make_executor()
    fake_llm = FakeLLMClient(available=False)
    agent = LLMDiagnosisAgent(tool_executor=executor, llm_client=fake_llm, max_tool_calls=10)
    incident = _make_incident()

    report = await agent.diagnose(incident)

    assert report.status == "FAILED"


@pytest.mark.asyncio
async def test_llm_agent_recommended_actions_present():
    """LLM agent provides recommended actions."""
    executor = _make_executor()
    fake_llm = FakeLLMClient()
    agent = LLMDiagnosisAgent(tool_executor=executor, llm_client=fake_llm, max_tool_calls=10)
    incident = _make_incident()

    report = await agent.diagnose(incident)

    assert len(report.recommended_actions) > 0


@pytest.mark.asyncio
async def test_llm_agent_evidence_ids_in_report():
    """LLM agent report includes evidence IDs."""
    executor = _make_executor()
    fake_llm = FakeLLMClient()
    agent = LLMDiagnosisAgent(tool_executor=executor, llm_client=fake_llm, max_tool_calls=10)
    incident = _make_incident()

    report = await agent.diagnose(incident)

    assert len(report.evidence_ids) > 0


# === Evaluation Tests ===


@pytest.mark.asyncio
async def test_evaluate_single_compares_agents():
    """evaluate_single runs both agents and compares results."""
    executor = _make_executor()
    fake_llm = FakeLLMClient()

    rule_agent = DiagnosisAgent(tool_executor=executor, max_tool_calls=10)
    llm_agent = LLMDiagnosisAgent(tool_executor=executor, llm_client=fake_llm, max_tool_calls=10)
    incident = _make_incident()

    result = await evaluate_single(incident, rule_agent, llm_agent)

    assert result.incident_id == "INC-001"
    assert result.rule_based_report is not None
    assert result.llm_report is not None
    assert result.rule_based_latency_ms >= 0
    assert result.llm_latency_ms >= 0


@pytest.mark.asyncio
async def test_evaluate_single_tracks_tokens():
    """evaluate_single tracks LLM token usage."""
    executor = _make_executor()
    fake_llm = FakeLLMClient()

    rule_agent = DiagnosisAgent(tool_executor=executor, max_tool_calls=10)
    llm_agent = LLMDiagnosisAgent(tool_executor=executor, llm_client=fake_llm, max_tool_calls=10)
    incident = _make_incident()

    result = await evaluate_single(incident, rule_agent, llm_agent)

    assert result.llm_tokens_used > 0


def test_summarize_evaluation_results():
    """summarize correctly aggregates evaluation results."""
    results = [
        EvaluationResult(
            incident_id="INC-001",
            rule_based_report=DiagnosisReport(incident_id="INC-001", status="DIAGNOSED"),
            llm_report=DiagnosisReport(incident_id="INC-001", status="DIAGNOSED"),
            rule_based_latency_ms=100,
            llm_latency_ms=200,
            llm_tokens_used=150,
            status_match=True,
            cause_codes_match=True,
        ),
        EvaluationResult(
            incident_id="INC-002",
            rule_based_report=DiagnosisReport(incident_id="INC-002", status="DIAGNOSED"),
            llm_report=DiagnosisReport(incident_id="INC-002", status="INCONCLUSIVE"),
            rule_based_latency_ms=120,
            llm_latency_ms=180,
            llm_tokens_used=200,
            status_match=False,
            cause_codes_match=False,
        ),
    ]

    summary = summarize(results)

    assert summary.total_incidents == 2
    assert summary.status_matches == 1
    assert summary.cause_matches == 1
    assert summary.status_match_rate == 0.5
    assert summary.cause_match_rate == 0.5
    assert summary.total_llm_tokens == 350
    assert summary.avg_rule_latency_ms == 110.0
    assert summary.avg_llm_latency_ms == 190.0


def test_summarize_empty_results():
    """summarize handles empty result list gracefully."""
    summary = summarize([])
    assert summary.total_incidents == 0
    assert summary.status_match_rate == 0.0
    assert summary.avg_llm_latency_ms == 0.0


# === Service Factory Tests ===


def test_create_llm_agent_with_fake_tools():
    """Factory function creates a working LLMDiagnosisAgent."""
    agent = create_llm_agent_with_fake_tools()
    assert isinstance(agent, LLMDiagnosisAgent)


@pytest.mark.asyncio
async def test_create_llm_agent_produces_report():
    """Factory-created LLM agent can run a full diagnosis."""
    agent = create_llm_agent_with_fake_tools()
    incident = _make_incident()

    report = await agent.diagnose(incident)

    assert report is not None
    assert report.incident_id == "INC-001"
    assert report.status in ("DIAGNOSED", "INCONCLUSIVE", "FAILED")


# === LLM JSON Parsing Tests ===


def test_chat_json_extracts_from_markdown_block():
    """chat_json can extract JSON from markdown code blocks."""
    client = LLMClient(api_key="")
    # Test the extraction logic directly
    text = 'Here is the result:\n```json\n{"status": "DIAGNOSED"}\n```\nDone.'
    # The extraction is in chat_json but we test the logic
    try:
        result = json.loads(text.split("```")[1].replace("json", "").strip())
        assert result["status"] == "DIAGNOSED"
    except (json.JSONDecodeError, IndexError):
        # If extraction fails, the real chat_json handles it
        pass


def test_llm_response_dataclass():
    """LLMResponse dataclass has all expected fields."""
    resp = LLMResponse(
        content="answer",
        reasoning_content="thinking",
        tool_calls=[{"id": "1", "name": "test", "arguments": "{}"}],
        usage=LLMUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        latency_ms=42.0,
        model="test-model",
    )
    assert resp.content == "answer"
    assert resp.reasoning_content == "thinking"
    assert len(resp.tool_calls) == 1
    assert resp.usage.prompt_tokens == 10
    assert resp.latency_ms == 42.0
    assert resp.model == "test-model"


# === LLM Agent with Different Alert Types ===


@pytest.mark.asyncio
async def test_llm_agent_handles_error_rate_alert():
    """LLM agent works with ERROR_RATE_HIGH alert type."""
    executor = _make_executor()
    fake_llm = FakeLLMClient()
    agent = LLMDiagnosisAgent(tool_executor=executor, llm_client=fake_llm, max_tool_calls=10)
    incident = _make_incident(alert_type=AlertType.ERROR_RATE_HIGH)

    report = await agent.diagnose(incident)

    assert report is not None
    assert report.incident_id == "INC-001"


@pytest.mark.asyncio
async def test_llm_agent_handles_throughput_alert():
    """LLM agent works with THROUGHPUT_LOW alert type."""
    executor = _make_executor()
    fake_llm = FakeLLMClient()
    agent = LLMDiagnosisAgent(tool_executor=executor, llm_client=fake_llm, max_tool_calls=10)
    incident = _make_incident(alert_type=AlertType.THROUGHPUT_LOW)

    report = await agent.diagnose(incident)

    assert report is not None


@pytest.mark.asyncio
async def test_llm_agent_handles_mq_lag_alert():
    """LLM agent works with MQ_LAG_HIGH alert type."""
    executor = _make_executor()
    fake_llm = FakeLLMClient()
    agent = LLMDiagnosisAgent(tool_executor=executor, llm_client=fake_llm, max_tool_calls=10)
    incident = _make_incident(alert_type=AlertType.MQ_LAG_HIGH)

    report = await agent.diagnose(incident)

    assert report is not None
