"""LLM-powered diagnosis agent

Uses DeepSeek V4 Flash for plan creation, hypothesis generation, and report
generation. Falls back to rule-based when LLM is unavailable.

Pipeline:
  load_incident -> llm_create_plan -> collect_evidence
  -> llm_build_hypotheses -> validate_evidence
  -> llm_generate_report -> complete / inconclusive / fail
"""

from dataclasses import dataclass, field
from typing import Optional

from app.agent.graph import DiagnosisAgent, _build_evidence_details
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

        for item in items[:4]:  # Keep the LLM plan compact, then add guardrail steps below.
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

        steps = _merge_required_steps(steps, _rule_based_plan(incident), state.max_tool_calls)
        state.llm_reasoning_log.append(f"plan: evidence guardrail kept {len(steps)} steps")

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

            parameters = _with_incident_window(step.parameters, state.incident)
            result = await self._executor.execute(ToolInput(
                tool=step.tool,
                parameters=parameters,
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

        guardrail_hypotheses = _rule_based_hypotheses(state.incident, state.evidence)

        # Fallback to rule-based if LLM returned no hypotheses. Otherwise merge the
        # LLM's judgement with deterministic evidence guardrails so an LLM cannot
        # miss obvious root-cause evidence collected by mandatory tool calls.
        if not hypotheses:
            hypotheses = _merge_hypotheses(guardrail_hypotheses)
            state.llm_reasoning_log.append("hypotheses: used rule-based fallback")
        else:
            hypotheses = _merge_hypotheses(guardrail_hypotheses + hypotheses)
            state.llm_reasoning_log.append("hypotheses: merged LLM output with evidence guardrails")

        hypotheses = _remove_metric_contradicted_hypotheses(hypotheses, state.evidence)

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

        # Override status with LLM suggestion if available, but never allow the LLM
        # to downgrade a high-confidence, evidence-backed diagnosis.
        if isinstance(result, dict):
            llm_status = result.get("status", "")
            if llm_status in ("DIAGNOSED", "INCONCLUSIVE", "FAILED"):
                has_high_confidence_evidence = any(
                    h.confidence == ConfidenceLevel.HIGH and h.supporting_evidence
                    for h in state.hypotheses
                )
                if not (status == "DIAGNOSED" and llm_status != "DIAGNOSED" and has_high_confidence_evidence):
                    status = llm_status

        actions = []
        missing = []
        if isinstance(result, dict):
            actions = result.get("recommended_actions", [])
            missing = result.get("missing_evidence", [])

        actions = _merge_actions(_rule_based_actions(state.hypotheses), actions, state.hypotheses)

        state.final_report = DiagnosisReport(
            incident_id=state.incident.incident_id,
            status=status,
            top_causes=state.hypotheses,
            recommended_actions=actions,
            missing_evidence=missing,
            tool_failures=state.tool_failures,
            evidence_ids=evidence_ids,
            evidence_details=_build_evidence_details(state.evidence),
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
            if any("slow" in log.get("message", "").lower() for log in logs):
                hypotheses.append(Hypothesis(
                    cause_code="DATABASE_SLOW_QUERY", confidence=ConfidenceLevel.HIGH,
                    supporting_evidence=[ev.evidence_id],
                    reasoning_summary="Slow query patterns detected in logs",
                ))
            if any(_is_db_pool_exhaustion_log(log.get("message", "")) for log in logs):
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
            elif (
                metric == "latency_p95"
                and baseline
                and current > max(baseline * 5, incident.threshold)
            ):
                hypotheses.append(Hypothesis(
                    cause_code="DATABASE_SLOW_QUERY",
                    confidence=ConfidenceLevel.HIGH,
                    supporting_evidence=[ev.evidence_id],
                    reasoning_summary=(
                        f"P95 latency {current}ms is {current / baseline:.1f}x "
                        f"above baseline {baseline}ms"
                    ),
                ))
    if not hypotheses:
        hypotheses.append(Hypothesis(
            cause_code="UNKNOWN", confidence=ConfidenceLevel.LOW,
            reasoning_summary="No matching patterns found", rank=1,
        ))
    return hypotheses[:3]


def _with_incident_window(parameters: dict, incident: Incident | None) -> dict:
    if not incident:
        return parameters
    enriched = dict(parameters)
    enriched.setdefault("start_time", incident.started_at.isoformat())
    return enriched


def _step_key(step: PlanStep) -> tuple:
    normalized_params = []
    for key, value in sorted(step.parameters.items()):
        if isinstance(value, list):
            normalized_params.append((key, tuple(sorted(str(item) for item in value))))
        else:
            normalized_params.append((key, str(value)))
    return step.tool, tuple(normalized_params)


def _merge_required_steps(
    llm_steps: list[PlanStep],
    required_steps: list[PlanStep],
    max_tool_calls: int,
) -> list[PlanStep]:
    """Merge LLM-selected steps with required evidence collection steps."""
    merged = []
    seen = set()
    for step in required_steps + llm_steps:
        key = _semantic_step_key(step)
        if key in seen:
            continue
        if len(merged) >= max_tool_calls:
            break
        merged.append(step)
        seen.add(key)
    return merged


def _semantic_step_key(step: PlanStep) -> tuple:
    service = step.parameters.get("service", "")
    if step.tool in ("query_logs", "query_deployments"):
        return step.tool, service
    if step.tool == "query_metrics":
        return step.tool, service, step.parameters.get("metric", "")
    return _step_key(step)


def _confidence_score(confidence: ConfidenceLevel) -> int:
    return {ConfidenceLevel.HIGH: 3, ConfidenceLevel.MEDIUM: 2, ConfidenceLevel.LOW: 1}.get(confidence, 0)


def _is_db_pool_exhaustion_log(message: str) -> bool:
    message = message.lower()
    if any(noise in message for noise in ("hikaripool-1 - start completed", "start completed")):
        return False
    if any(non_db in message for non_db in ("redis", "http", "thread", "request queued", "rejected")):
        return False
    exhaustion_terms = (
        "connection pool exhausted",
        "pool exhausted",
        "connection pool full",
        "pool full",
        "timeout waiting for connection",
        "connection is not available",
        "too many connections",
        "unable to acquire jdbc connection",
        "could not acquire jdbc connection",
    )
    return any(term in message for term in exhaustion_terms)


def _merge_hypotheses(hypotheses: list[Hypothesis]) -> list[Hypothesis]:
    """Merge duplicate cause codes and rank evidence-backed hypotheses first."""
    merged: dict[str, Hypothesis] = {}

    for hypothesis in hypotheses:
        existing = merged.get(hypothesis.cause_code)
        if existing is None:
            merged[hypothesis.cause_code] = Hypothesis(
                cause_code=hypothesis.cause_code,
                confidence=hypothesis.confidence,
                supporting_evidence=list(dict.fromkeys(hypothesis.supporting_evidence)),
                contradicting_evidence=list(dict.fromkeys(hypothesis.contradicting_evidence)),
                reasoning_summary=hypothesis.reasoning_summary,
            )
            continue

        if _confidence_score(hypothesis.confidence) > _confidence_score(existing.confidence):
            existing.confidence = hypothesis.confidence
            existing.reasoning_summary = hypothesis.reasoning_summary or existing.reasoning_summary
        elif hypothesis.reasoning_summary and hypothesis.reasoning_summary not in existing.reasoning_summary:
            existing.reasoning_summary = (
                f"{existing.reasoning_summary}; {hypothesis.reasoning_summary}"
                if existing.reasoning_summary else hypothesis.reasoning_summary
            )

        for evidence_id in hypothesis.supporting_evidence:
            if evidence_id not in existing.supporting_evidence:
                existing.supporting_evidence.append(evidence_id)
        for evidence_id in hypothesis.contradicting_evidence:
            if evidence_id not in existing.contradicting_evidence:
                existing.contradicting_evidence.append(evidence_id)

    ranked = sorted(
        merged.values(),
        key=lambda h: (
            -_confidence_score(h.confidence),
            0 if h.supporting_evidence else 1,
            h.cause_code == "UNKNOWN",
        ),
    )
    return ranked[:3]


def _remove_metric_contradicted_hypotheses(
    hypotheses: list[Hypothesis],
    evidence: list[Evidence],
) -> list[Hypothesis]:
    pool_metrics = [
        item for item in evidence
        if item.source == "query_metrics"
        and item.content.get("metric") == "db_pool_active_ratio"
        and item.content.get("current") is not None
    ]
    pool_is_low = any(float(item.content.get("current", 0)) < 0.7 for item in pool_metrics)
    if not pool_is_low:
        return hypotheses
    return [
        hypothesis for hypothesis in hypotheses
        if hypothesis.cause_code != "DATABASE_CONNECTION_POOL_EXHAUSTED"
    ]


def _merge_actions(primary: list[str], secondary: list[str], hypotheses: list[Hypothesis]) -> list[str]:
    actions = []
    seen = set()
    cause_codes = {hypothesis.cause_code for hypothesis in hypotheses}
    for action in primary + secondary:
        if not action or action in seen:
            continue
        action_text = action.lower()
        if (
            "DATABASE_CONNECTION_POOL_EXHAUSTED" not in cause_codes
            and ("connection pool" in action_text or "hikaricp" in action_text)
        ):
            continue
        category = _action_category(action_text)
        if category and category in seen:
            continue
        actions.append(action)
        seen.add(action)
        if category:
            seen.add(category)
        if len(actions) >= 3:
            break
    return actions or ["Gather more evidence"]


def _action_category(action_text: str) -> str:
    if "connection pool" in action_text or "hikaricp" in action_text:
        return "connection_pool"
    if "index" in action_text or "explain" in action_text:
        return "database_index"
    if "n+1" in action_text or "rewrite" in action_text:
        return "query_optimization"
    if "execution plan" in action_text or "optimize" in action_text or "slow-running sql" in action_text:
        return "database_plan"
    if "monitor" in action_text or "alert" in action_text:
        return "monitoring"
    return ""


def _rule_based_actions(hypotheses: list[Hypothesis]) -> list[str]:
    """Generate rule-based actions when LLM fails."""
    action_map = {
        "DATABASE_SLOW_QUERY": [
            "Check for missing database indexes (EXPLAIN ANALYZE on slow queries)",
            "Review query execution plans and optimize N+1 queries",
        ],
        "DATABASE_CONNECTION_POOL_EXHAUSTED": [
            "Increase HikariCP maximum pool size",
            "Check for connection leaks (long-running transactions)",
            "Review slow queries holding connections",
        ],
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
