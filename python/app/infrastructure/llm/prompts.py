"""System prompts and templates for LLM-driven diagnosis."""

SYSTEM_PROMPT = """\
You are an expert incident diagnosis assistant for Spring Boot microservices.

Your job:
1. Analyze the incident alert and available evidence
2. Generate hypotheses about the root cause
3. Rank hypotheses by confidence based on the evidence
4. Recommend actionable remediation steps

Rules:
- Always ground your reasoning in the provided evidence.
- Each hypothesis MUST reference specific evidence IDs.
- Use cause_code identifiers from this list when applicable:
  DATABASE_SLOW_QUERY, DATABASE_CONNECTION_POOL_EXHAUSTED, REDIS_TIMEOUT,
  DOWNSTREAM_SERVICE_FAILURE, RECENT_DEPLOYMENT_REGRESSION, APPLICATION_ERROR_SPIKE,
  MQ_CONSUMER_ERROR, RESOURCE_EXHAUSTION, NETWORK_ISSUE, UNKNOWN
- Confidence levels: HIGH, MEDIUM, LOW
- If evidence is insufficient, say INCONCLUSIVE rather than guessing.
"""

PLAN_PROMPT = """\
Given the following incident, create an investigation plan with 2-4 tool calls.

Incident:
- Service: {service}
- Alert Type: {alert_type}
- Endpoint: {endpoint}
- Value: {value} (threshold: {threshold})
- Started at: {started_at}

Available tools: query_logs, query_metrics, query_deployments, search_runbooks

Respond with a JSON array of investigation steps:
```json
[
  {{
    "tool": "query_metrics",
    "purpose": "Check error rate trend",
    "parameters": {{"metric": "error_rate", "service": "{service}"}}
  }}
]
```
"""

HYPOTHESIS_PROMPT = """\
Based on the incident and collected evidence, generate up to 3 hypotheses about the root cause.

Incident:
- Service: {service}
- Alert Type: {alert_type}
- Value: {value} (threshold: {threshold})

Evidence collected:
{evidence_summary}

Respond with a JSON object:
```json
{{
  "hypotheses": [
    {{
      "cause_code": "DATABASE_SLOW_QUERY",
      "confidence": "HIGH",
      "reasoning_summary": "Slow query logs show missing index on orders table",
      "supporting_evidence_ids": ["ev-001"],
      "contradicting_evidence_ids": []
    }}
  ]
}}
```
"""

REPORT_PROMPT = """\
Generate a final diagnosis report based on the hypotheses and evidence.

Incident: {incident_id} for service {service}
Alert: {alert_type}

Top hypotheses:
{hypotheses_summary}

All evidence IDs: {evidence_ids}
Tool failures: {tool_failures}

Respond with a JSON object:
```json
{{
  "status": "DIAGNOSED",
  "summary": "Brief diagnosis summary",
  "recommended_actions": ["Action 1", "Action 2"],
  "missing_evidence": ["What additional evidence would help"]
}}
```
Use status: "DIAGNOSED" if confident, "INCONCLUSIVE" if not enough evidence, "FAILED" if analysis failed.
"""


def format_evidence_summary(evidence_list: list[dict]) -> str:
    """Format evidence list into a readable summary for the LLM prompt."""
    if not evidence_list:
        return "(no evidence collected)"

    lines = []
    for ev in evidence_list:
        eid = ev.get("evidence_id", "?")
        source = ev.get("source", "?")
        content = ev.get("content", {})

        # Summarize content based on source type
        if source == "query_logs":
            logs = content.get("logs", [])
            error_stats = content.get("error_stats", {})
            lines.append(f"[{eid}] Logs ({len(logs)} entries):")
            if error_stats:
                lines.append(f"  Error stats: {error_stats}")
            for log in logs[:5]:  # Limit to first 5
                msg = log.get("message", "")[:120]
                level = log.get("level", "?")
                lines.append(f"  [{level}] {msg}")
            if len(logs) > 5:
                lines.append(f"  ... and {len(logs) - 5} more entries")

        elif source == "query_metrics":
            metric = content.get("metric", "?")
            current = content.get("current", 0)
            baseline = content.get("baseline", 0)
            lines.append(f"[{eid}] Metrics: {metric} = {current} (baseline: {baseline})")

        elif source == "query_deployments":
            deps = content.get("deployments", [])
            lines.append(f"[{eid}] Deployments ({len(deps)} total):")
            for dep in deps[:3]:
                lines.append(f"  {dep.get('version', '?')} at {dep.get('deployed_at', '?')} - {dep.get('changes', '')}")

        elif source == "search_runbooks":
            runbooks = content.get("runbooks", [])
            lines.append(f"[{eid}] Runbooks ({len(runbooks)} found):")
            for rb in runbooks[:3]:
                lines.append(f"  {rb.get('title', '?')}: {rb.get('summary', '')[:100]}")

        else:
            lines.append(f"[{eid}] {source}: {str(content)[:200]}")

    return "\n".join(lines)


def format_hypotheses_summary(hypotheses: list[dict]) -> str:
    """Format hypotheses into a readable summary for the LLM prompt."""
    if not hypotheses:
        return "(no hypotheses)"

    lines = []
    for h in hypotheses:
        lines.append(
            f"- [{h.get('confidence', '?')}] {h.get('cause_code', '?')}: "
            f"{h.get('reasoning_summary', '')}"
        )
        if h.get("supporting_evidence"):
            lines.append(f"  Supporting: {h['supporting_evidence']}")
        if h.get("contradicting_evidence"):
            lines.append(f"  Contradicting: {h['contradicting_evidence']}")
    return "\n".join(lines)
