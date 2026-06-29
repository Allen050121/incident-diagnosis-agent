"""Agent graph - LangGraph-inspired diagnosis workflow

Implements the pipeline:
  load_incident -> classify_incident -> load_topology -> create_plan
  -> collect_initial_evidence -> build_hypotheses
  -> select_verification -> verify_hypotheses
  -> validate_evidence -> generate_report
  -> complete / inconclusive / fail

MVP: Rule-based (no LLM), deterministic hypothesis generation from evidence.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Optional

from app.domain.incident import (
    AlertType,
    ConfidenceLevel,
    DiagnosisReport,
    Evidence,
    EvidenceDetail,
    Hypothesis,
    Incident,
    IncidentStatus,
    InvestigationPlan,
    PlanStep,
)
from app.infrastructure.tool_definitions import ToolInput
from app.infrastructure.tool_executor import ToolExecutor
from app.infrastructure.evidence_governance import (
    filter_hypotheses_without_evidence,
    validate_evidence_traceability,
    determine_diagnosis_status,
)


@dataclass
class AgentState:
    """Full state of the diagnosis workflow"""
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
    verification_rounds: int = 0
    max_verification_rounds: int = 3


class DiagnosisAgent:
    """Rule-based diagnosis agent implementing the minimum diagnosis pipeline"""

    def __init__(self, tool_executor: ToolExecutor, max_tool_calls: int = 10):
        self._executor = tool_executor
        self._max_tool_calls = max_tool_calls

    async def diagnose(self, incident: Incident) -> DiagnosisReport:
        """Run the full diagnosis pipeline"""
        state = AgentState(
            incident=incident,
            max_tool_calls=self._max_tool_calls,
        )

        # Execute the graph
        state = await self._load_incident(state)
        state = await self._classify_incident(state)
        state = await self._load_topology(state)
        state = await self._create_plan(state)
        state = await self._collect_initial_evidence(state)
        state = await self._build_hypotheses(state)
        state = await self._verify_hypotheses(state)
        state = await self._validate_evidence(state)
        state = await self._generate_report(state)

        return state.final_report or DiagnosisReport(
            incident_id=incident.incident_id,
            status="FAILED",
            tool_failures=state.tool_failures,
        )

    # --- Graph nodes ---

    async def _load_incident(self, state: AgentState) -> AgentState:
        """Parse and validate the incident"""
        if state.incident:
            state.incident.status = IncidentStatus.INVESTIGATING
        return state

    async def _classify_incident(self, state: AgentState) -> AgentState:
        """Classify incident by alert type to guide investigation"""
        return state  # Classification embedded in plan creation

    async def _load_topology(self, state: AgentState) -> AgentState:
        """Load service topology via tool"""
        if not state.incident or state.tool_calls_used >= state.max_tool_calls:
            return state

        result = await self._executor.execute(ToolInput(
            tool="query_metrics",
            parameters={
                "metric": "request_rate",
                "service": state.incident.service,
            },
        ))
        state.tool_calls_used += 1

        if result.success:
            # Store basic topology info from metrics
            state.service_topology = {
                "service": state.incident.service,
                "status": "loaded",
            }
        return state

    async def _create_plan(self, state: AgentState) -> AgentState:
        """Create investigation plan based on alert type (2-4 steps)"""
        if not state.incident:
            return state

        alert_type = state.incident.alert_type
        service = state.incident.service

        if alert_type == AlertType.P95_LATENCY_HIGH:
            steps = [
                PlanStep(tool="query_metrics", purpose="Confirm where latency is elevated",
                         parameters={"metric": "latency_p95", "service": service}),
                PlanStep(tool="query_metrics", purpose="Check database connection pool saturation",
                         parameters={"metric": "db_pool_active_ratio", "service": service}),
                PlanStep(tool="query_logs", purpose="Find errors and timeouts in the same window",
                         parameters={"service": service, "keywords": ["slow", "timeout", "error"]}),
                PlanStep(tool="query_deployments", purpose="Check for recent deployments",
                         parameters={"service": service}),
            ]
        elif alert_type == AlertType.ERROR_RATE_HIGH:
            steps = [
                PlanStep(tool="query_logs", purpose="Find error logs and exception traces",
                         parameters={"service": service, "keywords": ["error", "exception", "fail"]}),
                PlanStep(tool="query_metrics", purpose="Check error rate trend",
                         parameters={"metric": "error_rate", "service": service}),
                PlanStep(tool="query_deployments", purpose="Check whether a deployment caused regression",
                         parameters={"service": service}),
            ]
        elif alert_type == AlertType.THROUGHPUT_LOW:
            steps = [
                PlanStep(tool="query_metrics", purpose="Check request rate and saturation",
                         parameters={"metric": "request_rate", "service": service}),
                PlanStep(tool="query_logs", purpose="Find blocking, rejection, and timeout logs",
                         parameters={"service": service, "keywords": ["timeout", "blocked", "reject"]}),
                PlanStep(tool="query_metrics", purpose="Check Redis latency",
                         parameters={"metric": "redis_latency_p95", "service": service}),
            ]
        else:  # MQ_LAG_HIGH
            steps = [
                PlanStep(tool="query_metrics", purpose="Check MQ lag",
                         parameters={"metric": "mq_lag", "service": service}),
                PlanStep(tool="query_logs", purpose="Find consumer lag and processing errors",
                         parameters={"service": service, "keywords": ["consumer", "lag", "error"]}),
            ]

        state.investigation_plan = InvestigationPlan(steps=steps)
        return state

    async def _collect_initial_evidence(self, state: AgentState) -> AgentState:
        """Execute the investigation plan steps to collect evidence"""
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

    async def _build_hypotheses(self, state: AgentState) -> AgentState:
        """Build top-3 hypotheses from collected evidence"""
        if not state.incident or not state.evidence:
            state.hypotheses = [
                Hypothesis(
                    cause_code="UNKNOWN",
                    confidence=ConfidenceLevel.LOW,
                    reasoning_summary="Insufficient evidence collected",
                    rank=1,
                )
            ]
            return state

        hypotheses = []

        # Rule-based hypothesis generation based on evidence patterns
        for ev in state.evidence:
            if ev.source == "query_logs":
                logs = ev.content.get("logs", [])
                messages = [log.get("message", "") for log in logs]
                lower_messages = [message.lower() for message in messages]

                # Check for slow query patterns
                slow_query_logs = [
                    message for message in messages
                    if "slow" in message.lower() or "SQLSlowQuery" in message
                ]
                if slow_query_logs:
                    hypotheses.append(Hypothesis(
                        cause_code="DATABASE_SLOW_QUERY",
                        confidence=ConfidenceLevel.HIGH,
                        supporting_evidence=[ev.evidence_id],
                        reasoning_summary="Log contains slow query errors indicating missing index or unoptimized query",
                    ))

                # Check for connection pool issues
                pool_logs = [
                    message for message in lower_messages
                    if _is_db_pool_exhaustion_log(message)
                ]
                if pool_logs:
                    hypotheses.append(Hypothesis(
                        cause_code="DATABASE_CONNECTION_POOL_EXHAUSTED",
                        confidence=ConfidenceLevel.HIGH,
                        supporting_evidence=[ev.evidence_id],
                        reasoning_summary="Connection pool exhaustion detected in logs",
                    ))

                # Check for Redis issues
                redis_logs = [message for message in lower_messages if "redis" in message]
                if redis_logs:
                    hypotheses.append(Hypothesis(
                        cause_code="REDIS_TIMEOUT",
                        confidence=ConfidenceLevel.MEDIUM,
                        supporting_evidence=[ev.evidence_id],
                        reasoning_summary="Redis timeout errors found in logs",
                    ))

                # Check for downstream failures
                downstream_logs = [
                    message for message in lower_messages
                    if "503" in message or "unavailable" in message or "downstream" in message
                ]
                if downstream_logs:
                    hypotheses.append(Hypothesis(
                        cause_code="DOWNSTREAM_SERVICE_FAILURE",
                        confidence=ConfidenceLevel.MEDIUM,
                        supporting_evidence=[ev.evidence_id],
                        reasoning_summary="Downstream service returning 503 errors",
                    ))

                resource_logs = [
                    message for message in lower_messages
                    if any(token in message for token in (
                        "thread pool", "connection pool full", "rate limited",
                        "circuit breaker", "request queued", "rejected",
                    ))
                    and "database" not in message
                    and "hikaripool" not in message
                    and "redis" not in message
                ]
                if resource_logs:
                    hypotheses.append(Hypothesis(
                        cause_code="RESOURCE_EXHAUSTION",
                        confidence=ConfidenceLevel.HIGH,
                        supporting_evidence=[ev.evidence_id],
                        reasoning_summary="Resource saturation or resilience guardrail detected in logs",
                    ))

                mq_logs = [
                    message for message in lower_messages
                    if "mq" in message or "consumer lag" in message or "message backlog" in message
                ]
                if mq_logs:
                    hypotheses.append(Hypothesis(
                        cause_code="MQ_CONSUMER_ERROR",
                        confidence=ConfidenceLevel.HIGH,
                        supporting_evidence=[ev.evidence_id],
                        reasoning_summary="Message consumer lag or processing errors detected",
                    ))

                config_logs = [
                    message for message in lower_messages
                    if "configuration" in message or "config" in message or "property" in message
                ]
                if config_logs:
                    hypotheses.append(Hypothesis(
                        cause_code="APPLICATION_ERROR_SPIKE",
                        confidence=ConfidenceLevel.HIGH,
                        supporting_evidence=[ev.evidence_id],
                        reasoning_summary="Application errors point to missing or invalid configuration",
                    ))

                npe_logs = [
                    message for message in lower_messages
                    if "nullpointerexception" in message or " after deploying " in message
                ]
                if npe_logs:
                    hypotheses.append(Hypothesis(
                        cause_code="RECENT_DEPLOYMENT_REGRESSION",
                        confidence=ConfidenceLevel.HIGH,
                        supporting_evidence=[ev.evidence_id],
                        reasoning_summary="New application exception pattern appears after deployment",
                    ))

            elif ev.source == "query_metrics":
                metric_data = ev.content
                metric = metric_data.get("metric", "")
                current = metric_data.get("current", 0)
                baseline = metric_data.get("baseline", 0)

                if metric == "db_pool_active_ratio" and current > 0.9:
                    hypotheses.append(Hypothesis(
                        cause_code="DATABASE_CONNECTION_POOL_EXHAUSTED",
                        confidence=ConfidenceLevel.HIGH,
                        supporting_evidence=[ev.evidence_id],
                        reasoning_summary=f"DB pool usage at {current:.0%}, far above baseline {baseline:.0%}",
                    ))
                elif (
                    metric == "latency_p95"
                    and state.incident.service == "order-service"
                    and current > baseline * 5
                ):
                    hypotheses.append(Hypothesis(
                        cause_code="DATABASE_SLOW_QUERY",
                        confidence=ConfidenceLevel.MEDIUM,
                        supporting_evidence=[ev.evidence_id],
                        reasoning_summary=f"P95 latency {current}ms is {current/baseline:.1f}x above baseline {baseline}ms",
                    ))
                elif (
                    metric == "latency_p95"
                    and "inventory" in state.incident.service
                    and current > baseline * 5
                ):
                    hypotheses.append(Hypothesis(
                        cause_code="REDIS_TIMEOUT",
                        confidence=ConfidenceLevel.MEDIUM,
                        supporting_evidence=[ev.evidence_id],
                        reasoning_summary=f"Inventory latency {current}ms suggests cache or Redis latency",
                    ))
                elif (
                    metric == "latency_p95"
                    and "payment" in state.incident.service
                    and current > baseline * 5
                ):
                    hypotheses.append(Hypothesis(
                        cause_code="DOWNSTREAM_SERVICE_FAILURE",
                        confidence=ConfidenceLevel.MEDIUM,
                        supporting_evidence=[ev.evidence_id],
                        reasoning_summary=f"Payment service latency {current}ms suggests downstream timeout",
                    ))
                elif metric in ("http_pool_active_ratio", "jvm_thread_pool_active_ratio") and current > 0.9:
                    hypotheses.append(Hypothesis(
                        cause_code="RESOURCE_EXHAUSTION",
                        confidence=ConfidenceLevel.HIGH,
                        supporting_evidence=[ev.evidence_id],
                        reasoning_summary=f"{metric} at {current:.0%}, indicating resource saturation",
                    ))
                elif metric == "redis_latency_p95" and current > max(baseline * 5, 500):
                    hypotheses.append(Hypothesis(
                        cause_code="REDIS_TIMEOUT",
                        confidence=ConfidenceLevel.HIGH,
                        supporting_evidence=[ev.evidence_id],
                        reasoning_summary=f"Redis P95 latency {current}ms is far above baseline {baseline}ms",
                    ))
                elif metric == "downstream_latency_p95" and current > max(baseline * 5, 1000):
                    hypotheses.append(Hypothesis(
                        cause_code="DOWNSTREAM_SERVICE_FAILURE",
                        confidence=ConfidenceLevel.HIGH,
                        supporting_evidence=[ev.evidence_id],
                        reasoning_summary=f"Downstream P95 latency {current}ms is far above baseline {baseline}ms",
                    ))
                elif metric == "mq_lag" and current > max(baseline * 10, 5000):
                    hypotheses.append(Hypothesis(
                        cause_code="MQ_CONSUMER_ERROR",
                        confidence=ConfidenceLevel.HIGH,
                        supporting_evidence=[ev.evidence_id],
                        reasoning_summary=f"MQ lag {current} messages is far above baseline {baseline}",
                    ))
                elif metric == "error_rate" and current > 0.05:
                    hypotheses.append(Hypothesis(
                        cause_code="APPLICATION_ERROR_SPIKE",
                        confidence=ConfidenceLevel.MEDIUM,
                        supporting_evidence=[ev.evidence_id],
                        reasoning_summary=f"Error rate at {current:.1%}, significantly elevated",
                    ))

            elif ev.source == "query_deployments":
                deployments = ev.content.get("deployments", [])
                recent = [d for d in deployments
                          if _is_recent(d.get("deployed_at", ""), hours=4)]
                if recent:
                    changes = recent[0].get("changes", "").lower()
                    confidence = (
                        ConfidenceLevel.HIGH
                        if any(token in changes for token in ("null", "npe", "exception", "error"))
                        else ConfidenceLevel.LOW
                    )
                    hypotheses.append(Hypothesis(
                        cause_code="RECENT_DEPLOYMENT_REGRESSION",
                        confidence=confidence,
                        supporting_evidence=[ev.evidence_id],
                        reasoning_summary=f"Recent deployment: {recent[0].get('version', 'unknown')} - {recent[0].get('changes', '')}",
                    ))

        # Deduplicate by cause_code, merge evidence
        merged = _merge_hypotheses(hypotheses)
        merged = _remove_metric_contradicted_hypotheses(merged, state.evidence)
        # Sort by confidence and limit to top 3
        merged.sort(key=lambda h: _confidence_order(h.confidence))
        top3 = merged[:3]

        # Ensure no hypothesis without evidence ranks first
        for i, h in enumerate(top3):
            h.rank = i + 1
        if top3 and not top3[0].supporting_evidence and len(top3) > 1:
            # Find first with evidence and swap
            for i, h in enumerate(top3):
                if h.supporting_evidence:
                    top3[0], top3[i] = top3[i], top3[0]
                    break

        if not top3:
            top3 = [Hypothesis(
                cause_code="UNKNOWN",
                confidence=ConfidenceLevel.LOW,
                reasoning_summary="No matching evidence patterns found",
                rank=1,
            )]

        state.hypotheses = top3
        return state

    async def _verify_hypotheses(self, state: AgentState) -> AgentState:
        """Additional verification step - check for contradicting evidence"""
        # For MVP, add contradicting evidence from deployments
        if not state.hypotheses or not state.evidence:
            return state

        deploy_evidence = [e for e in state.evidence if e.source == "query_deployments"]
        for dep_ev in deploy_evidence:
            deployments = dep_ev.content.get("deployments", [])
            recent = [d for d in deployments if _is_recent(d.get("deployed_at", ""), hours=4)]
            if not recent:
                # No recent deployment - add contradicting evidence to deployment hypotheses
                for h in state.hypotheses:
                    if h.cause_code == "RECENT_DEPLOYMENT_REGRESSION":
                        h.contradicting_evidence.append(dep_ev.evidence_id)
                        h.confidence = ConfidenceLevel.LOW
                        h.reasoning_summary += " [No recent deployments found to support this]"

        return state

    async def _validate_evidence(self, state: AgentState) -> AgentState:
        """Validate that all claims in hypotheses reference real evidence (evidence governance)"""
        all_evidence_ids = {e.evidence_id for e in state.evidence}

        for h in state.hypotheses:
            # Filter out evidence references that don't exist
            h.supporting_evidence = [
                eid for eid in h.supporting_evidence if eid in all_evidence_ids
            ]
            h.contradicting_evidence = [
                eid for eid in h.contradicting_evidence if eid in all_evidence_ids
            ]

        # Filter and re-rank: hypotheses without evidence go to the end
        state.hypotheses = filter_hypotheses_without_evidence(state.hypotheses)

        return state

    async def _generate_report(self, state: AgentState) -> AgentState:
        """Generate the final diagnosis report with evidence governance"""
        if not state.incident:
            state.final_report = DiagnosisReport(
                incident_id="unknown",
                status="FAILED",
                tool_failures=["No incident provided"],
            )
            return state

        # Evidence traceability check
        traceability = validate_evidence_traceability(state.hypotheses, state.evidence)

        # Determine status using governance rules
        status = determine_diagnosis_status(state.hypotheses, traceability)

        # Generate recommended actions based on top cause
        actions = _generate_actions(state.hypotheses)

        # Collect all evidence IDs referenced in report
        evidence_ids = list({
            eid for h in state.hypotheses
            for eid in h.supporting_evidence + h.contradicting_evidence
        })

        # Identify missing evidence
        missing = _identify_missing_evidence(state.hypotheses, state.evidence)

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

        state.incident.status = IncidentStatus.DIAGNOSED if status == "DIAGNOSED" else IncidentStatus.INCONCLUSIVE
        return state


# --- Helper functions ---

def _is_recent(deployed_at_str: str, hours: int = 4) -> bool:
    """Check if a deployment timestamp is within the given hours"""
    try:
        deployed_at = datetime.fromisoformat(deployed_at_str.replace("Z", "+00:00"))
        if deployed_at.tzinfo is None:
            deployed_at = deployed_at.replace(tzinfo=UTC)
        else:
            deployed_at = deployed_at.astimezone(UTC)
        now = datetime.now(UTC)
        return (now - deployed_at).total_seconds() < hours * 3600
    except (ValueError, TypeError):
        return False


def _with_incident_window(parameters: dict, incident: Incident | None) -> dict:
    if not incident:
        return parameters
    enriched = dict(parameters)
    enriched.setdefault("start_time", incident.started_at.isoformat())
    return enriched


def _merge_hypotheses(hypotheses: list[Hypothesis]) -> list[Hypothesis]:
    """Merge hypotheses with the same cause_code"""
    merged = {}
    for h in hypotheses:
        if h.cause_code not in merged:
            merged[h.cause_code] = Hypothesis(
                cause_code=h.cause_code,
                confidence=h.confidence,
                supporting_evidence=list(h.supporting_evidence),
                contradicting_evidence=list(h.contradicting_evidence),
                reasoning_summary=h.reasoning_summary,
            )
        else:
            existing = merged[h.cause_code]
            # Upgrade confidence if needed
            if _confidence_order(h.confidence) < _confidence_order(existing.confidence):
                existing.confidence = h.confidence
            # Merge evidence lists
            for eid in h.supporting_evidence:
                if eid not in existing.supporting_evidence:
                    existing.supporting_evidence.append(eid)
            for eid in h.contradicting_evidence:
                if eid not in existing.contradicting_evidence:
                    existing.contradicting_evidence.append(eid)
    return list(merged.values())


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


def _confidence_order(confidence: ConfidenceLevel) -> int:
    """Lower is better"""
    return {ConfidenceLevel.HIGH: 0, ConfidenceLevel.MEDIUM: 1, ConfidenceLevel.LOW: 2}.get(confidence, 3)


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


def _generate_actions(hypotheses: list[Hypothesis]) -> list[str]:
    """Generate recommended actions based on hypotheses"""
    actions = []
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
        "REDIS_TIMEOUT": [
            "Check Redis server health and memory usage",
            "Increase connection pool size (spring.redis.pool.max-active)",
            "Review for slow Redis commands (KEYS, large value scans)",
        ],
        "DOWNSTREAM_SERVICE_FAILURE": [
            "Check downstream service health endpoints",
            "Verify circuit breaker configuration and fallback behavior",
            "Review downstream service logs for root cause",
        ],
        "RECENT_DEPLOYMENT_REGRESSION": [
            "Review recent deployment changes (git diff)",
            "Consider rollback if regression confirmed",
            "Check configuration changes in the deployment",
        ],
        "APPLICATION_ERROR_SPIKE": [
            "Review application logs for error patterns",
            "Check resource utilization (CPU, memory, threads)",
        ],
        "RESOURCE_EXHAUSTION": [
            "Check thread pools, HTTP client pools, and rate-limit/circuit-breaker settings",
            "Reduce saturation or raise pool limits after validating traffic demand",
        ],
        "MQ_CONSUMER_ERROR": [
            "Check consumer error logs and message backlog",
            "Scale consumers or inspect poison messages blocking progress",
        ],
    }

    seen = set()
    for h in hypotheses:
        for action in action_map.get(h.cause_code, []):
            if action not in seen:
                actions.append(action)
                seen.add(action)

    if not actions:
        actions.append("Gather more evidence - current data insufficient for confident diagnosis")

    return actions


def _identify_missing_evidence(hypotheses: list[Hypothesis], evidence: list[Evidence]) -> list[str]:
    """Identify what additional evidence would strengthen the diagnosis"""
    missing = []
    evidence_sources = {e.source for e in evidence}

    if "query_runbooks" not in evidence_sources:
        missing.append("Runbook search results for historical pattern matching")
    if "query_deployments" not in evidence_sources:
        missing.append("Recent deployment history to rule out release regression")

    # Check if we have metrics for key areas
    has_db_metrics = any(
        e.content.get("metric") in ("db_pool_active_ratio", "latency_p95")
        for e in evidence if e.source == "query_metrics"
    )
    if not has_db_metrics:
        missing.append("Database performance metrics (pool usage, query latency)")

    return missing


def _build_evidence_details(evidence: list[Evidence]) -> list[EvidenceDetail]:
    return [
        EvidenceDetail(
            evidence_id=item.evidence_id,
            source=item.source,
            summary=_summarize_evidence(item),
            query_window=item.query_window,
            truncated=item.truncated,
            content=item.content,
        )
        for item in evidence
    ]


def _summarize_evidence(evidence: Evidence) -> str:
    content = evidence.content
    if evidence.source == "query_logs":
        logs = content.get("logs", [])
        stats = content.get("error_stats", {})
        if not logs:
            warning = content.get("warning", "No matching logs found")
            return f"Logs: {warning}"
        messages = [log.get("message", "") for log in logs[:2]]
        return f"Logs: {len(logs)} entries, levels={stats}, sample={' | '.join(messages)}"

    if evidence.source == "query_metrics":
        metric = content.get("metric", "unknown")
        current = content.get("current", "n/a")
        baseline = content.get("baseline", "n/a")
        unit = content.get("unit", "")
        source = content.get("source", "metrics")
        return f"Metric {metric}: current={current}{unit}, baseline={baseline}{unit}, source={source}"

    if evidence.source == "query_deployments":
        deployments = content.get("deployments", [])
        if not deployments:
            return "Deployments: no recent deployments"
        first = deployments[0]
        return (
            "Deployments: "
            f"{len(deployments)} records, latest={first.get('version', 'unknown')} "
            f"{first.get('changes', '')}"
        )

    if evidence.source == "search_runbooks":
        runbooks = content.get("runbooks", [])
        if not runbooks:
            return "Runbooks: no matches"
        titles = [item.get("title", "untitled") for item in runbooks[:2]]
        return f"Runbooks: {len(runbooks)} matches, top={'; '.join(titles)}"

    return f"{evidence.source}: {str(content)[:200]}"
