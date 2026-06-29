"""Tests for Phase 7+ deliverables: evaluation dataset, desensitizer, agent trace, experiments."""


import pytest

from app.domain.incident import AlertType
from app.evaluation.dataset import generate_dataset, dataset_summary
from app.evaluation.runner import score_report, compute_metrics, run_evaluation
from app.evaluation.experiments import run_all_experiments
from app.infrastructure.log_desensitizer import (
    desensitize, desensitize_log_entry, desensitize_logs,
)
from app.infrastructure.agent_trace import (
    TraceRecorder,
)
from app.domain.incident import (
    ConfidenceLevel, DiagnosisReport, Hypothesis,
)


# === Evaluation Dataset Tests ===


def test_generate_dataset_returns_48_cases():
    """12 faults × 4 variants = 48 cases."""
    cases = generate_dataset()
    assert len(cases) == 48


def test_dataset_covers_all_12_faults():
    """All 12 fault templates are represented."""
    cases = generate_dataset()
    fault_ids = set(c.fault_id for c in cases)
    assert len(fault_ids) == 12


def test_dataset_each_fault_has_4_variants():
    """Each fault has exactly 4 parameter variants."""
    cases = generate_dataset()
    from collections import Counter
    counts = Counter(c.fault_id for c in cases)
    for fault_id, count in counts.items():
        assert count == 4, f"{fault_id} has {count} variants, expected 4"


def test_dataset_has_variants():
    """Dataset includes noise, tool_unavailable, wrong_runbook, and unrelated_deploy variants."""
    cases = generate_dataset()
    summary = dataset_summary(cases)
    variants = summary["by_variant"]
    assert variants["clean"] > 0
    assert variants["noisy"] > 0 or variants["tool_unavailable"] > 0


def test_dataset_summary_structure():
    """Summary has expected keys."""
    cases = generate_dataset()
    summary = dataset_summary(cases)
    assert "total_cases" in summary
    assert "by_category" in summary
    assert "by_variant" in summary
    assert "faults_covered" in summary
    assert summary["total_cases"] == 48


def test_eval_case_has_required_fields():
    """Each case has all required fields for evaluation."""
    cases = generate_dataset()
    for case in cases[:5]:
        assert case.case_id
        assert case.fault_id
        assert case.root_cause
        assert case.expected_cause_code
        assert case.affected_service
        assert case.alert_type in AlertType


# === Scoring Tests ===


def test_score_report_top1_hit():
    """Top-1 hit when first cause matches expected."""
    report = DiagnosisReport(
        incident_id="INC-001",
        status="DIAGNOSED",
        top_causes=[
            Hypothesis(cause_code="DATABASE_SLOW_QUERY", confidence=ConfidenceLevel.HIGH, rank=1),
        ],
    )
    result = score_report(report, "DATABASE_SLOW_QUERY", [])
    assert result["top1"] is True
    assert result["top3"] is True


def test_score_report_top3_not_top1():
    """Top-3 hit when expected cause is in top 3 but not first."""
    report = DiagnosisReport(
        incident_id="INC-001",
        status="DIAGNOSED",
        top_causes=[
            Hypothesis(cause_code="REDIS_TIMEOUT", confidence=ConfidenceLevel.HIGH, rank=1),
            Hypothesis(cause_code="DATABASE_SLOW_QUERY", confidence=ConfidenceLevel.MEDIUM, rank=2),
        ],
    )
    result = score_report(report, "DATABASE_SLOW_QUERY", [])
    assert result["top1"] is False
    assert result["top3"] is True


def test_score_report_miss():
    """No hit when expected cause is not in top 3."""
    report = DiagnosisReport(
        incident_id="INC-001",
        status="DIAGNOSED",
        top_causes=[
            Hypothesis(cause_code="REDIS_TIMEOUT", confidence=ConfidenceLevel.HIGH, rank=1),
        ],
    )
    result = score_report(report, "DATABASE_SLOW_QUERY", [])
    assert result["top1"] is False
    assert result["top3"] is False


def test_score_report_forbidden_violation():
    """Detects forbidden conclusion."""
    report = DiagnosisReport(
        incident_id="INC-001",
        status="DIAGNOSED",
        top_causes=[
            Hypothesis(cause_code="REDIS_TIMEOUT", confidence=ConfidenceLevel.HIGH, rank=1),
        ],
    )
    result = score_report(report, "DATABASE_SLOW_QUERY", ["REDIS_TIMEOUT"])
    assert result["forbidden_violation"] is True


def test_score_report_no_violation():
    """No forbidden violation when causes don't overlap."""
    report = DiagnosisReport(
        incident_id="INC-001",
        status="DIAGNOSED",
        top_causes=[
            Hypothesis(cause_code="DATABASE_SLOW_QUERY", confidence=ConfidenceLevel.HIGH, rank=1),
        ],
    )
    result = score_report(report, "DATABASE_SLOW_QUERY", ["REDIS_TIMEOUT"])
    assert result["forbidden_violation"] is False


def test_score_report_none():
    """Score None report as FAILED."""
    result = score_report(None, "DATABASE_SLOW_QUERY", [])
    assert result["top1"] is False
    assert result["top3"] is False
    assert result["status"] == "FAILED"


def test_compute_metrics_structure():
    """Metrics have expected structure."""
    from app.evaluation.runner import ScoringResult
    scoring = ScoringResult(
        case_id="EVAL-001", fault_id="mysql-slow-query",
        root_cause="MISSING_INDEX", expected_cause_code="DATABASE_SLOW_QUERY",
        rb_top1_hit=True, rb_top3_hit=True, rb_status="DIAGNOSED",
        rb_cause_codes=["DATABASE_SLOW_QUERY"], rb_evidence_count=1,
        rb_latency_ms=50.0,
    )
    metrics = compute_metrics([scoring])
    assert metrics["total_cases"] == 1
    assert "rule_based" in metrics
    assert metrics["rule_based"]["top1_accuracy"] == 1.0


@pytest.mark.asyncio
async def test_evaluation_runner_uses_case_specific_evidence():
    """Evaluation must not score every fault against the same fake MySQL evidence."""
    results = await run_evaluation()
    metrics = compute_metrics(results)["rule_based"]

    assert metrics["top1_accuracy"] >= 0.9
    assert metrics["forbidden_violation_rate"] == 0.0

    by_case = {result.fault_id: result for result in results}
    assert by_case["redis-timeout"].rb_cause_codes[0] == "REDIS_TIMEOUT"
    assert by_case["downstream-payment-timeout"].rb_cause_codes[0] == "DOWNSTREAM_SERVICE_FAILURE"
    assert by_case["mq-consumer-lag"].rb_cause_codes[0] == "MQ_CONSUMER_ERROR"


# === Log Desensitization Tests ===


def test_desensitize_phone_number():
    """Phone numbers are redacted."""
    text = "User called from +1-555-123-4567 about issue"
    result = desensitize(text)
    assert "555" not in result
    assert "[PHONE_REDACTED]" in result


def test_desensitize_api_key():
    """API keys are redacted."""
    text = "Authorization: Bearer sk-abc123def456ghi789jkl012mno345"
    result = desensitize(text)
    assert "sk-abc123" not in result
    assert "[API_KEY_REDACTED]" in result


def test_desensitize_password():
    """Passwords are redacted."""
    text = "Connecting with password=SuperSecret123 to database"
    result = desensitize(text)
    assert "SuperSecret123" not in result
    assert "[REDACTED]" in result


def test_desensitize_email():
    """Emails are redacted."""
    text = "Notification sent to user@example.com"
    result = desensitize(text)
    assert "user@example.com" not in result
    assert "[EMAIL_REDACTED]" in result


def test_desensitize_jwt():
    """JWT tokens are redacted."""
    text = "Token: eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNrypg"
    result = desensitize(text)
    assert "eyJhbG" not in result
    assert "[JWT_REDACTED]" in result


def test_desensitize_internal_ip():
    """Internal IP addresses are redacted."""
    text = "Connected to 192.168.1.100:3306"
    result = desensitize(text)
    assert "192.168.1.100" not in result
    assert "[IP_REDACTED]" in result


def test_desensitize_empty_string():
    """Empty string returns empty."""
    assert desensitize("") == ""


def test_desensitize_no_sensitive_data():
    """Clean text passes through unchanged."""
    text = "Order processed successfully in 150ms"
    assert desensitize(text) == text


def test_desensitize_log_entry():
    """Log entry dict is desensitized."""
    entry = {
        "timestamp": "2026-01-01T00:00:00",
        "level": "ERROR",
        "message": "Password=secret123 failed for user@test.com from 192.168.1.5",
        "trace_id": "abc-123",
    }
    result = desensitize_log_entry(entry)
    assert "secret123" not in result["message"]
    assert "user@test.com" not in result["message"]
    assert result["timestamp"] == "2026-01-01T00:00:00"  # Non-string preserved
    assert result["level"] == "ERROR"


def test_desensitize_logs_batch():
    """Batch desensitization of log list."""
    logs = [
        {"message": "API key: sk-abcdef12345678901234567890"},
        {"message": "Clean log message"},
        {"message": "Contact: admin@company.com"},
    ]
    result = desensitize_logs(logs)
    assert len(result) == 3
    assert "sk-abcdef" not in result[0]["message"]
    assert result[1]["message"] == "Clean log message"
    assert "admin@company.com" not in result[2]["message"]


# === Agent Trace Tests ===


def test_trace_recorder_start_and_finish():
    """Trace can be started and finished."""
    rec = TraceRecorder()
    trace = rec.start_trace("INC-001", "TASK-001")
    assert trace.incident_id == "INC-001"
    assert trace.diagnosis_task_id == "TASK-001"
    assert trace.trace_id

    rec.finish_trace(trace, status="DIAGNOSED")
    assert trace.final_status == "DIAGNOSED"
    assert trace.total_duration_ms >= 0


def test_trace_add_span():
    """Spans can be added to a trace."""
    rec = TraceRecorder()
    trace = rec.start_trace("INC-002")

    span = trace.add_span("graph_node", "load_incident")
    assert span.operation == "graph_node"
    assert span.name == "load_incident"
    assert span.span_id

    trace.finish_span(span)
    assert span.finished_at
    assert span.duration_ms >= 0


def test_trace_to_dict():
    """Trace serializes to dict."""
    rec = TraceRecorder()
    trace = rec.start_trace("INC-003")
    trace.add_span("tool_call", "query_logs")
    rec.finish_trace(trace, status="DIAGNOSED")

    d = trace.to_dict()
    assert d["trace_id"]
    assert d["incident_id"] == "INC-003"
    assert d["final_status"] == "DIAGNOSED"
    assert len(d["spans"]) == 1


def test_trace_recorder_list_traces():
    """Recorder can list all traces."""
    rec = TraceRecorder()
    t1 = rec.start_trace("INC-A")
    rec.finish_trace(t1, "DIAGNOSED")
    t2 = rec.start_trace("INC-B")
    rec.finish_trace(t2, "INCONCLUSIVE")

    traces = rec.list_traces()
    assert len(traces) == 2


def test_trace_recorder_get_by_incident():
    """Get traces filtered by incident ID."""
    rec = TraceRecorder()
    rec.start_trace("INC-X")
    rec.start_trace("INC-X")
    rec.start_trace("INC-Y")

    x_traces = rec.get_traces_for_incident("INC-X")
    assert len(x_traces) == 2


# === Controlled Experiments Tests ===


@pytest.mark.asyncio
async def test_run_all_experiments_returns_4():
    """All 4 experiments run successfully."""
    results = await run_all_experiments()
    assert len(results) == 4


@pytest.mark.asyncio
async def test_experiment_has_conclusion():
    """Each experiment has a non-empty conclusion."""
    results = await run_all_experiments()
    for exp in results:
        assert exp.conclusion, f"Experiment {exp.experiment_name} has no conclusion"
        assert exp.total_cases > 0


@pytest.mark.asyncio
async def test_experiment_names():
    """Experiments have correct names."""
    results = await run_all_experiments()
    names = [e.experiment_name for e in results]
    assert "raw_llm_vs_agent" in names
    assert "with_vs_without_runbook" in names
    assert "with_vs_without_verification" in names
    assert "full_vs_dedup_logs" in names
