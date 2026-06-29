"""LLM-powered diagnosis agent

Uses DeepSeek V4 Flash for plan creation, hypothesis generation, and report
generation. Falls back to rule-based when LLM is unavailable.

Pipeline:
  load_incident -> llm_create_plan -> collect_evidence
  -> llm_build_hypotheses -> validate_evidence
  -> llm_generate_report -> complete / inconclusive / fail
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from app.agent.graph import DiagnosisAgent
from app.domain.incident import (
    AlertType,
    ConfidenceLevel,
    DiagnosisReport,
    Evidence,
    Hypothesis,
    Incident,
    IncidentStatus,
    InvestigationPlan,
    PlanStep,
)
from app.infrastructure.evidence_governance import (
    filter_hypotheses_without_evidence,
    validate_evidence_traceability,
    determine_diagnosis_status,
)
from app.infrastructure.llm.client import LLMClient
from app.infrastructure.llm.prompts import (
    SYSTEM_PROMPT,
    PLAN_PROMPT,
    HYPOTHESIS_PROMPT,
    REPORT_PROMPT,
    format_evidence_summary,
    format_hypotheses_summary,
)
from app.infrastructure.tool_definitions import ToolInput
from app.infrastructure.tool_executor import ToolExecutor


@dataclass
class LLMAgentState:
    """Full state of the LLM diagnosis workflow"""
    incident: Optional[Incident] = None
    service_topology: dict = field(default_factory=dict)
    investigation_plan: Optional[InvestigationPlan] = None
    evidence: list[Evidence] = field(default_factory=list)
    hypotheses: list[Hypothesis] = field(default_factory=list)
    tool_failures: list[str] = field(default_factory=list)
    final_report: Optional[DiagnosisReport] = None
    # Budget tracking
    tool_calls_used: int = 0
    max_tool_calls: int = 10
    # LLM reasoning log
    llm_reasoning_log: list[str] = field(default_factory=list)


_CONFIDENCE_MAP = {
    "HIGH": ConfidenceLevel.HIGH,
    "MEDIUM": ConfidenceLevel.MEDIUM,
    "LOW": ConfidenceLevel.LOW,
}


class LLMDiagnosisAgent:
    """LLM-powered diagnosis agent.

    Uses DeepSeek V4 Flash for key decisions (plan, hypotheses, report).
    Falls back to rule-based DiagnosisAgent when LLM is unavailable.
    """

    def __init__(self, tool_executor: ToolExecutor, llm_client: LLMClient,
                 max_tool_calls: int = 10, rule_based_fallback: DiagnosisAgent | None = None):
        self._executor = tool_executor
        self._llm = llm_client
        self._max_tool_calls = max_tool_calls
        self._fallback = rule_based_fallback

    async def diagnose(self, incident: Incident) -> DiagnosisReport:
        """Run the LLM-powered diagnosis pipeline.

        Falls back to rule-based agent when LLM is not available.
        """
        if not self._llm.is_available:
            if self._fallback:
                return await self._fallback.diagnose(incident)
            return DiagnosisReport(
                incident_id=incident.incident_id,
                status="FAILED",
                tool_failures=["LLM not available and no rule-based fallback configured"],
            )

        state = LLMAgentState(
            incident=incident,
            max_tool_calls=self._max_tool_calls,
        )

        state = await self._load_incident(state)
        state = await self._llm_create_plan(state)
        state = await self._collect_evidence(state)
        state = await self._llm_build_hypotheses(state)
        state = await self._validate_evidence(state)
        state = await self._llm_generate_report(state)

        return state.final_report or DiagnosisReport(
            incident_id=incident.incident_id,
            status="FAILED",
            tool_failures=state.tool_failures,
        )

    @property
    def accumulated_usage(self):
        return self._llm.accumulated_usage

    # --- Graph nodes ---

    async def _load_incident(self, state: LLMAgentState) -> LLMAgentState:
        if state.incident:
            state.incident.status = IncidentStatus.INVESTIGATING
        return state

    async def _llm_create_plan(self, state: LLMAgentState) -> LLMAgentState:
        """Use LLM to create an investigation plan."""
        if not state.incident:
            return state

        incident = state.incident
        prompt = PLAN_PROMPT.format(
            service=incident.service,
            alert_type=incident.alert_type.value,
            endpoint=incident.endpoint or "N/A",
            value=incident.value,
            threshold=incident.threshold,
            started_at=incident.started_at.isoformat(),
        )

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]

        result = self._llm.chat_json(messages, max_tokens=1024, temperature=0.3)
        state.llm_reasoning_log.append(f"plan: {result}")

        steps = []
        if isinstance(result, list):
            items = result
        elif isinstance(result, dict) and "steps" in result:
            items = result["steps"]
        else:
            items = []

        for item in items[:4]:  # Max 4 steps
            tool = item.get("tool", "")
            if tool in ("query_logs", "query_metrics", "query_deployments", "search_runbooks"):
                steps.append(PlanStep(
                    tool=tool,
                    purpose=item.get("purpose", ""),
                    parameters=item.get("parameters", {}),
                ))

        # Fallback to rule-based plan if LLM plan is empty
        if not steps:
            steps = _rule_based_plan(incident)
            state.llm_reasoning_log.append("plan: used rule-based fallback")

        state.investigation_plan = InvestigationPlan(steps=steps)
        return state

    async def _collect_evidence(self, state: LLMAgentState) -> LLMAgentState:
        """Execute the investigation plan to collect evidence."""
        if not state.investigation_plan:
            return state

        for step in state.investigation_plan.steps:
            if state.tool_calls_used >= state.max_tool_calls:
                state.tool_failures.append("Budget exhausted before plan completed")
                break

            result = await self._executor.execute(ToolInput(
                tool=step.tool,
                parameters=step.parameters,
            ))
            state.tool_calls_used += 1

            evidence = Evidence(
                evidence_id=result.evidence_id,
                source=step.tool,
                content=result.data,
                query_window=result.query_window,
                truncated=result.truncated,
            )

            if result.success:
                state.evidence.append(evidence)
            else:
                state.tool_failures.append(f"{step.tool}: {result.error}")

        return state

    async def _llm_build_hypotheses(self, state: LLMAgentState) -> LLMAgentState:
        """Use LLM to generate hypotheses from evidence."""
        if not state.incident:
            state.hypotheses = [
                Hypothesis(cause_code="UNKNOWN", confidence=ConfidenceLevel.LOW,
                           reasoning_summary="No incident provided", rank=1)
            ]
            return state

        if not state.evidence:
            state.hypotheses = [
                Hypothesis(cause_code="UNKNOWN", confidence=ConfidenceLevel.LOW,
                           reasoning_summary="No evidence collected", rank=1)
            ]
            return state

        evidence_summary = format_evidence_summary(
            [{"evidence_id": e.evidence_id, "source": e.source, "content": e.content}
             for e in state.evidence]
        )

        prompt = HYPOTHESIS_PROMPT.format(
            service=state.incident.service,
            alert_type=state.incident.alert_type.value,
            value=state.incident.value,
            threshold=state.incident.threshold,
            evidence_summary=evidence_summary,
        )

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]

        result = self._llm.chat_json(messages, max_tokens=2048, temperature=0.3)
        state.llm_reasoning_log.append(f"hypotheses: {result}")

        hypotheses = []
        items = result.get("hypotheses", []) if isinstance(result, dict) else []

        for item in items[:3]:  # Max 3
            cause_code = item.get("cause_code", "UNKNOWN")
            confidence_str = item.get("confidence", "LOW").upper()
            confidence = _CONFIDENCE_MAP.get(confidence_str, ConfidenceLevel.LOW)
            reasoning = item.get("reasoning_summary", "")
            supporting = item.get("supporting_evidence_ids", [])
            contradicting = item.get("contradicting_evidence_ids", [])

            if not isinstance(supporting, list):
                supporting = []
            if not isinstance(contradicting, list):
                contradicting = []

            hypotheses.append(Hypothesis(
                cause_code=cause_code,
                confidence=confidence,
                supporting_evidence=supporting,
                contradicting_evidence=contradicting,
                reasoning_summary=reasoning,
            ))

        # Fallback to rule-based if LLM returned no hypotheses
        if not hypotheses:
            hypotheses = _rule_based_hypotheses(state.incident, state.evidence)
            state.llm_reasoning_log.append("hypotheses: used rule-based fallback")

        # Rank
        for i, h in enumerate(hypotheses):
            h.rank = i + 1

        state.hypotheses = hypotheses
        return state

    async def _validate_evidence(self, state: LLMAgentState) -> LLMAgentState:
        """Validate evidence traceability (same as rule-based)."""
        all_evidence_ids = {e.evidence_id for e in state.evidence}

        for h in state.hypotheses:
            h.supporting_evidence = [
                eid for eid in h.supporting_evidence if eid in all_evidence_ids
            ]
            h.contradicting_evidence = [
                eid for eid in h.contradicting_evidence if eid in all_evidence_ids
            ]

        state.hypotheses = filter_hypotheses_without_evidence(state.hypotheses)
        return state

    async def _llm_generate_report(self, state: LLMAgentState) -> LLMAgentState:
        """Use LLM to generate the final diagnosis report."""
        if not state.incident:
            state.final_report = DiagnosisReport(
                incident_id="unknown", status="FAILED",
                tool_failures=["No incident provided"],
            )
            return state

        hypotheses_summary = format_hypotheses_summary(
            [{"cause_code": h.cause_code, "confidence": h.confidence.value,
              "reasoning_summary": h.reasoning_summary,
              "supporting_evidence": h.supporting_evidence,
              "contradicting_evidence": h.contradicting_evidence}
             for h in state.hypotheses]
        )

        prompt = REPORT_PROMPT.format(
            incident_id=state.incident.incident_id,
            service=state.incident.service,
            alert_type=state.incident.alert_type.value,
            hypotheses_summary=hypotheses_summary,
            evidence_ids=[e.evidence_id for e in state.evidence],
            tool_failures=state.tool_failures,
        )

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]

        result = self._llm.chat_json(messages, max_tokens=2048, temperature=0.3)
        state.llm_reasoning_log.append(f"report: {result}")

        # Parse LLM report
        evidence_ids = list({
            eid for h in state.hypotheses
            for eid in h.supporting_evidence + h.contradicting_evidence
        })

        traceability = validate_evidence_traceability(state.hypotheses, state.evidence)
        status = determine_diagnosis_status(state.hypotheses, traceability)

        # Override status with LLM suggestion if available
        if isinstance(result, dict):
            llm_status = result.get("status", "")
            if llm_status in ("DIAGNOSED", "INCONCLUSIVE", "FAILED"):
                status = llm_status

        actions = []
        missing = []
        summary = ""
        if isinstance(result, dict):
            actions = result.get("recommended_actions", [])
            missing = result.get("missing_evidence", [])
            summary = result.get("summary", "")

        # Fallback actions
        if not actions:
            actions = _rule_based_actions(state.hypotheses)

        state.final_report = DiagnosisReport(
            incident_id=state.incident.incident_id,
            status=status,
            top_causes=state.hypotheses,
            recommended_actions=actions,
            missing_evidence=missing,
            tool_failures=state.tool_failures,
            evidence_ids=evidence_ids,
            investigation_steps=len(state.investigation_plan.steps) if state.investigation_plan else 0,
            total_tool_calls=state.tool_calls_used,
        )

        state.incident.status = (
            IncidentStatus.DIAGNOSED if status == "DIAGNOSED"
            else IncidentStatus.INCONCLUSIVE
        )
        return state


# --- Rule-based fallback helpers ---

def _rule_based_plan(incident: Incident) -> list[PlanStep]:
    """Generate a rule-based plan when LLM fails."""
    service = incident.service
    if incident.alert_type == AlertType.P95_LATENCY_HIGH:
        return [
            PlanStep(tool="query_metrics", purpose="Check P95 latency",
                     parameters={"metric": "latency_p95", "service": service}),
            PlanStep(tool="query_metrics", purpose="Check DB pool",
                     parameters={"metric": "db_pool_active_ratio", "service": service}),
            PlanStep(tool="query_logs", purpose="Find slow queries",
                     parameters={"service": service, "keywords": ["slow", "timeout"]}),
            PlanStep(tool="query_deployments", purpose="Check recent deploys",
                     parameters={"service": service}),
        ]
    elif incident.alert_type == AlertType.ERROR_RATE_HIGH:
        return [
            PlanStep(tool="query_logs", purpose="Find errors",
                     parameters={"service": service, "keywords": ["error", "exception"]}),
            PlanStep(tool="query_metrics", purpose="Check error rate",
                     parameters={"metric": "error_rate", "service": service}),
            PlanStep(tool="query_deployments", purpose="Check deploys",
                     parameters={"service": service}),
        ]
    elif incident.alert_type == AlertType.THROUGHPUT_LOW:
        return [
            PlanStep(tool="query_metrics", purpose="Check request rate",
                     parameters={"metric": "request_rate", "service": service}),
            PlanStep(tool="query_logs", purpose="Find blocking",
                     parameters={"service": service, "keywords": ["timeout", "blocked"]}),
        ]
    else:  # MQ_LAG_HIGH
        return [
            PlanStep(tool="query_metrics", purpose="Check MQ lag",
                     parameters={"metric": "mq_lag", "service": service}),
            PlanStep(tool="query_logs", purpose="Find consumer errors",
                     parameters={"service": service, "keywords": ["consumer", "error"]}),
        ]


def _rule_based_hypotheses(incident: Incident, evidence: list[Evidence]) -> list[Hypothesis]:
    """Generate rule-based hypotheses when LLM fails."""
    hypotheses = []
    for ev in evidence:
        if ev.source == "query_logs":
            logs = ev.content.get("logs", [])
            if any("slow" in l.get("message", "").lower() for l in logs):
                hypotheses.append(Hypothesis(
                    cause_code="DATABASE_SLOW_QUERY", confidence=ConfidenceLevel.HIGH,
                    supporting_evidence=[ev.evidence_id],
                    reasoning_summary="Slow query patterns detected in logs",
                ))
            if any("pool" in l.get("message", "").lower() for l in logs):
                hypotheses.append(Hypothesis(
                    cause_code="DATABASE_CONNECTION_POOL_EXHAUSTED",
                    confidence=ConfidenceLevel.HIGH,
                    supporting_evidence=[ev.evidence_id],
                    reasoning_summary="Connection pool issues in logs",
                ))
        elif ev.source == "query_metrics":
            metric = ev.content.get("metric", "")
            current = ev.content.get("current", 0)
            baseline = ev.content.get("baseline", 0)
            if metric == "db_pool_active_ratio" and current > 0.9:
                hypotheses.append(Hypothesis(
                    cause_code="DATABASE_CONNECTION_POOL_EXHAUSTED",
                    confidence=ConfidenceLevel.HIGH,
                    supporting_evidence=[ev.evidence_id],
                    reasoning_summary=f"DB pool at {current:.0%}",
                ))
    if not hypotheses:
        hypotheses.append(Hypothesis(
            cause_code="UNKNOWN", confidence=ConfidenceLevel.LOW,
            reasoning_summary="No matching patterns found", rank=1,
        ))
    return hypotheses[:3]


def _rule_based_actions(hypotheses: list[Hypothesis]) -> list[str]:
    """Generate rule-based actions when LLM fails."""
    action_map = {
        "DATABASE_SLOW_QUERY": ["Check for missing indexes", "Optimize slow queries"],
        "DATABASE_CONNECTION_POOL_EXHAUSTED": ["Increase pool size", "Check for connection leaks"],
        "REDIS_TIMEOUT": ["Check Redis health", "Review slow commands"],
        "DOWNSTREAM_SERVICE_FAILURE": ["Check downstream health", "Verify circuit breaker"],
        "RECENT_DEPLOYMENT_REGRESSION": ["Review deployment changes", "Consider rollback"],
        "APPLICATION_ERROR_SPIKE": ["Review error logs", "Check resource usage"],
    }
    actions = []
    seen = set()
    for h in hypotheses:
        for a in action_map.get(h.cause_code, []):
            if a not in seen:
                actions.append(a)
                seen.add(a)
    if not actions:
        actions.append("Gather more evidence")
    return actions
