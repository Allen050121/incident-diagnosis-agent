"""Evaluation runner - automated fault injection and scoring pipeline.

Runs the full evaluation dataset against both rule-based and LLM agents,
computes metrics, and outputs a structured report.
"""

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Optional

from app.agent.graph import DiagnosisAgent
from app.agent.service import parse_incident
from app.domain.incident import DiagnosisReport
from app.evaluation.dataset import EvalCase, generate_dataset
from app.infrastructure.fake_tools import (
    FakeDeploymentProvider,
    FakeLogProvider,
    FakeMetricsProvider,
    FakeRunbookProvider,
)
from app.infrastructure.tool_executor import ToolExecutor


class UnavailableProvider:
    """Tool provider that simulates a controlled tool outage."""

    def __init__(self, tool_name: str):
        self.tool_name = tool_name

    async def execute(self, parameters: dict) -> dict:
        raise RuntimeError(f"{self.tool_name} unavailable for evaluation case")


@dataclass
class ScoringResult:
    """Scoring result for a single evaluation case."""
    case_id: str
    fault_id: str
    root_cause: str
    expected_cause_code: str
    # Rule-based scoring
    rb_top1_hit: bool = False
    rb_top3_hit: bool = False
    rb_status: str = ""
    rb_cause_codes: list[str] = field(default_factory=list)
    rb_evidence_count: int = 0
    rb_latency_ms: float = 0.0
    rb_symptom_as_cause: bool = False
    # LLM scoring
    llm_top1_hit: bool = False
    llm_top3_hit: bool = False
    llm_status: str = ""
    llm_cause_codes: list[str] = field(default_factory=list)
    llm_evidence_count: int = 0
    llm_latency_ms: float = 0.0
    llm_tokens: int = 0
    llm_cost_usd: float = 0.0
    llm_symptom_as_cause: bool = False
    # Forbidden conclusion check
    rb_forbidden_violation: bool = False
    llm_forbidden_violation: bool = False


def score_report(report: Optional[DiagnosisReport], expected_cause_code: str,
                 forbidden: list[str]) -> dict:
    """Score a single diagnosis report against ground truth."""
    if not report:
        return {"top1": False, "top3": False, "status": "FAILED",
                "causes": [], "evidence": 0, "forbidden_violation": False,
                "symptom_as_cause": False}

    causes = [h.cause_code for h in report.top_causes]
    top1 = causes[0] == expected_cause_code if causes else False
    top3 = expected_cause_code in causes[:3]
    forbidden_violation = any(c in forbidden for c in causes)

    # Check if a symptom is used as cause (not a real root cause code)
    symptom_codes = {"APPLICATION_ERROR_SPIKE"}  # generic symptom-level codes
    symptom_as_cause = (
        causes and causes[0] in symptom_codes
        and expected_cause_code not in symptom_codes
    )

    return {
        "top1": top1,
        "top3": top3,
        "status": report.status,
        "causes": causes,
        "evidence": len(report.evidence_ids),
        "forbidden_violation": forbidden_violation,
        "symptom_as_cause": symptom_as_cause,
    }


def create_agent_for_case(case: EvalCase) -> DiagnosisAgent:
    """Create a deterministic evaluation agent whose tools reflect one fault case."""
    executor = ToolExecutor()
    scenario = case.fault_id

    providers = {
        "query_logs": FakeLogProvider(scenario=scenario),
        "query_metrics": FakeMetricsProvider(scenario=scenario),
        "query_deployments": FakeDeploymentProvider(
            scenario="deployment-npe" if case.fault_id == "deployment-npe" else "default"
        ),
        "search_runbooks": FakeRunbookProvider(scenario=scenario),
    }

    if case.has_unrelated_deploy and case.fault_id != "deployment-npe":
        providers["query_deployments"] = FakeDeploymentProvider(scenario="recent_deploy")

    if case.has_wrong_runbook:
        providers["search_runbooks"] = FakeRunbookProvider(scenario="default")

    if case.tool_unavailable:
        providers[case.tool_unavailable] = UnavailableProvider(case.tool_unavailable)

    for tool_name, provider in providers.items():
        executor.register(tool_name, provider)

    return DiagnosisAgent(tool_executor=executor, max_tool_calls=10)


async def run_evaluation(use_llm: bool = False) -> list[ScoringResult]:
    """Run the full evaluation pipeline."""
    cases = generate_dataset()
    results = []

    for case in cases:
        incident_data = {
            "incident_id": case.case_id,
            "service": case.affected_service,
            "alert_type": case.alert_type.value,
            "value": case.value,
            "threshold": case.threshold,
            "started_at": datetime.now(UTC).isoformat(),
        }
        incident = parse_incident(incident_data)

        # Score rule-based with case-specific deterministic tool evidence.
        rb_agent = create_agent_for_case(case)
        start = time.monotonic()
        rb_report = await rb_agent.diagnose(incident)
        rb_latency = (time.monotonic() - start) * 1000

        rb_score = score_report(rb_report, case.expected_cause_code,
                                case.forbidden_conclusions)

        result = ScoringResult(
            case_id=case.case_id,
            fault_id=case.fault_id,
            root_cause=case.root_cause,
            expected_cause_code=case.expected_cause_code,
            rb_top1_hit=rb_score["top1"],
            rb_top3_hit=rb_score["top3"],
            rb_status=rb_score["status"],
            rb_cause_codes=rb_score["causes"],
            rb_evidence_count=rb_score["evidence"],
            rb_latency_ms=round(rb_latency, 1),
            rb_symptom_as_cause=rb_score["symptom_as_cause"],
            rb_forbidden_violation=rb_score["forbidden_violation"],
        )

        # Score LLM if requested
        if use_llm:
            from app.agent.service import create_llm_agent_with_fake_tools
            llm_agent = create_llm_agent_with_fake_tools()
            incident2 = parse_incident(incident_data)
            start = time.monotonic()
            llm_report = await llm_agent.diagnose(incident2)
            llm_latency = (time.monotonic() - start) * 1000

            llm_score = score_report(llm_report, case.expected_cause_code,
                                     case.forbidden_conclusions)
            usage = llm_agent.accumulated_usage

            result.llm_top1_hit = llm_score["top1"]
            result.llm_top3_hit = llm_score["top3"]
            result.llm_status = llm_score["status"]
            result.llm_cause_codes = llm_score["causes"]
            result.llm_evidence_count = llm_score["evidence"]
            result.llm_latency_ms = round(llm_latency, 1)
            result.llm_tokens = usage.total_tokens
            result.llm_cost_usd = round(usage.estimated_cost_usd(), 6)
            result.llm_symptom_as_cause = llm_score["symptom_as_cause"]
            result.llm_forbidden_violation = llm_score["forbidden_violation"]

        results.append(result)

    return results


def compute_metrics(results: list[ScoringResult]) -> dict:
    """Compute all evaluation metrics from scoring results."""
    n = len(results)
    if n == 0:
        return {}

    # Rule-based metrics
    rb_top1_hits = sum(1 for r in results if r.rb_top1_hit)
    rb_top3_hits = sum(1 for r in results if r.rb_top3_hit)
    rb_forbidden = sum(1 for r in results if r.rb_forbidden_violation)
    rb_symptom_err = sum(1 for r in results if r.rb_symptom_as_cause)
    rb_inconclusive = sum(1 for r in results if r.rb_status == "INCONCLUSIVE")
    rb_diagnosed = sum(1 for r in results if r.rb_status == "DIAGNOSED")

    metrics = {
        "total_cases": n,
        "rule_based": {
            "top1_accuracy": round(rb_top1_hits / n, 3),
            "top3_recall": round(rb_top3_hits / n, 3),
            "forbidden_violation_rate": round(rb_forbidden / n, 3),
            "symptom_as_cause_rate": round(rb_symptom_err / n, 3),
            "inconclusive_rate": round(rb_inconclusive / n, 3),
            "diagnosed_rate": round(rb_diagnosed / n, 3),
            "avg_latency_ms": round(sum(r.rb_latency_ms for r in results) / n, 1),
            "avg_evidence_count": round(sum(r.rb_evidence_count for r in results) / n, 1),
            "top1_hits": rb_top1_hits,
            "top3_hits": rb_top3_hits,
        },
    }

    # LLM metrics (only if any LLM results exist)
    llm_results = [r for r in results if r.llm_status]
    if llm_results:
        ln = len(llm_results)
        llm_top1 = sum(1 for r in llm_results if r.llm_top1_hit)
        llm_top3 = sum(1 for r in llm_results if r.llm_top3_hit)
        llm_forbidden = sum(1 for r in llm_results if r.llm_forbidden_violation)
        llm_symptom_err = sum(1 for r in llm_results if r.llm_symptom_as_cause)
        llm_inconclusive = sum(1 for r in llm_results if r.llm_status == "INCONCLUSIVE")
        llm_diagnosed = sum(1 for r in llm_results if r.llm_status == "DIAGNOSED")

        metrics["llm"] = {
            "top1_accuracy": round(llm_top1 / ln, 3),
            "top3_recall": round(llm_top3 / ln, 3),
            "forbidden_violation_rate": round(llm_forbidden / ln, 3),
            "symptom_as_cause_rate": round(llm_symptom_err / ln, 3),
            "inconclusive_rate": round(llm_inconclusive / ln, 3),
            "diagnosed_rate": round(llm_diagnosed / ln, 3),
            "avg_latency_ms": round(sum(r.llm_latency_ms for r in llm_results) / ln, 1),
            "avg_evidence_count": round(sum(r.llm_evidence_count for r in llm_results) / ln, 1),
            "total_tokens": sum(r.llm_tokens for r in llm_results),
            "total_cost_usd": round(sum(r.llm_cost_usd for r in llm_results), 6),
            "avg_tokens_per_case": round(sum(r.llm_tokens for r in llm_results) / ln, 0),
            "top1_hits": llm_top1,
            "top3_hits": llm_top3,
        }

    # Per-category breakdown
    categories = {}
    for r in results:
        cat = r.root_cause.split("_")[0] if "_" in r.root_cause else r.root_cause
        if cat not in categories:
            categories[cat] = {"total": 0, "rb_top1": 0, "rb_top3": 0}
        categories[cat]["total"] += 1
        if r.rb_top1_hit:
            categories[cat]["rb_top1"] += 1
        if r.rb_top3_hit:
            categories[cat]["rb_top3"] += 1

    metrics["by_category"] = categories

    # Per-variant breakdown
    variants = {"clean": {"total": 0, "rb_top1": 0},
                "noisy": {"total": 0, "rb_top1": 0},
                "tool_missing": {"total": 0, "rb_top1": 0}}
    # Simplified variant tracking based on case_id patterns
    for r in results:
        variant = "clean"
        if "02" in r.case_id or "03" in r.case_id:
            variant = "noisy"
        elif "04" in r.case_id:
            variant = "tool_missing"
        if variant in variants:
            variants[variant]["total"] += 1
            if r.rb_top1_hit:
                variants[variant]["rb_top1"] += 1

    metrics["by_variant"] = variants

    return metrics


async def run_and_report(use_llm: bool = False, output_path: str = "eval_results.json") -> dict:
    """Run full evaluation and save results."""
    results = await run_evaluation(use_llm=use_llm)
    metrics = compute_metrics(results)

    report = {
        "timestamp": datetime.now(UTC).isoformat(),
        "metrics": metrics,
        "results": [asdict(r) for r in results],
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    return report
