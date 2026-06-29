"""LLM vs rule-based diagnosis comparison and evaluation."""

from dataclasses import dataclass, field
from typing import Optional

from app.agent.graph import DiagnosisAgent
from app.agent.llm_graph import LLMDiagnosisAgent
from app.domain.incident import DiagnosisReport, Incident


@dataclass
class EvaluationResult:
    """Result of comparing LLM vs rule-based diagnosis on one incident."""
    incident_id: str
    rule_based_report: Optional[DiagnosisReport] = None
    llm_report: Optional[DiagnosisReport] = None
    rule_based_latency_ms: float = 0.0
    llm_latency_ms: float = 0.0
    llm_tokens_used: int = 0
    llm_reasoning_tokens: int = 0
    llm_cost_usd: float = 0.0
    status_match: bool = False
    cause_codes_match: bool = False
    notes: list[str] = field(default_factory=list)


async def evaluate_single(
    incident: Incident,
    rule_agent: DiagnosisAgent,
    llm_agent: LLMDiagnosisAgent,
) -> EvaluationResult:
    """Run both agents on the same incident and compare results."""
    result = EvaluationResult(incident_id=incident.incident_id)

    # Run rule-based
    import time
    start = time.monotonic()
    result.rule_based_report = await rule_agent.diagnose(incident)
    result.rule_based_latency_ms = (time.monotonic() - start) * 1000

    # Run LLM-based
    start = time.monotonic()
    result.llm_report = await llm_agent.diagnose(incident)
    result.llm_latency_ms = (time.monotonic() - start) * 1000

    # LLM usage
    usage = llm_agent.accumulated_usage
    result.llm_tokens_used = usage.total_tokens
    result.llm_reasoning_tokens = usage.total_reasoning_tokens
    result.llm_cost_usd = usage.estimated_cost_usd()

    # Compare
    if result.rule_based_report and result.llm_report:
        result.status_match = (
            result.rule_based_report.status == result.llm_report.status
        )

        rb_causes = {h.cause_code for h in result.rule_based_report.top_causes}
        llm_causes = {h.cause_code for h in result.llm_report.top_causes}
        result.cause_codes_match = bool(rb_causes & llm_causes) if rb_causes and llm_causes else False

        if not result.status_match:
            result.notes.append(
                f"Status differs: rule={result.rule_based_report.status} vs llm={result.llm_report.status}"
            )

    return result


@dataclass
class EvaluationSummary:
    """Summary of evaluation across multiple incidents."""
    total_incidents: int = 0
    status_matches: int = 0
    cause_matches: int = 0
    total_llm_tokens: int = 0
    total_llm_cost_usd: float = 0.0
    avg_rule_latency_ms: float = 0.0
    avg_llm_latency_ms: float = 0.0
    results: list[EvaluationResult] = field(default_factory=list)

    @property
    def status_match_rate(self) -> float:
        return self.status_matches / self.total_incidents if self.total_incidents else 0.0

    @property
    def cause_match_rate(self) -> float:
        return self.cause_matches / self.total_incidents if self.total_incidents else 0.0


def summarize(results: list[EvaluationResult]) -> EvaluationSummary:
    """Summarize evaluation results across multiple incidents."""
    s = EvaluationSummary(
        total_incidents=len(results),
        results=results,
    )
    for r in results:
        if r.status_match:
            s.status_matches += 1
        if r.cause_codes_match:
            s.cause_matches += 1
        s.total_llm_tokens += r.llm_tokens_used
        s.total_llm_cost_usd += r.llm_cost_usd

    if results:
        s.avg_rule_latency_ms = sum(r.rule_based_latency_ms for r in results) / len(results)
        s.avg_llm_latency_ms = sum(r.llm_latency_ms for r in results) / len(results)

    return s
