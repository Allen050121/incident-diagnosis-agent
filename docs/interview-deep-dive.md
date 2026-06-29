# Interview Deep Dive: Incident Diagnosis Agent

This document summarizes the product and engineering depth behind the project.
It is written for interview explanation, not as a replacement for the setup guide.

## 1. Problem Framing

The project is not a generic chatbot for logs. It solves a narrower production
debugging problem:

- An alert has already fired.
- The affected service and alert type are known.
- The system must collect bounded evidence from controlled tools.
- The output is a Top-3 root cause list with evidence IDs and next actions.

The key product decision is to make the agent evidence-driven. The agent is not
allowed to invent facts or run arbitrary queries. It can only call whitelisted
tools such as logs, metrics, deployments, and runbooks.

## 2. Architecture

```text
Spring Boot fault lab
  order-service / inventory-service / payment-mock-service
        |
        | actuator metrics, log files, fault toggles
        v
Observability
  Prometheus + Grafana
        |
        v
Python Diagnosis Agent
  tool executor -> evidence -> hypotheses -> verification -> report
        |
        v
Evaluation
  48 cases, 12 fault types, variant scoring, controlled experiments
```

The architecture separates the agent's reasoning from evidence collection.
This makes each tool replaceable:

- `query_metrics`: fake provider for tests, Prometheus provider for live demos.
- `query_logs`: fake provider for tests, file-backed provider for live demos.
- `query_deployments`: deterministic provider today, can move to Git/MySQL later.
- `search_runbooks`: fake/BM25 path today, can move to Elasticsearch-backed RAG.

## 3. Evidence Governance

The agent keeps evidence IDs throughout the diagnosis pipeline.

Important rules:

- A hypothesis without supporting evidence cannot rank first.
- Tool failures are preserved in the final report.
- Missing evidence is reported instead of hidden.
- Runbooks are context, not final truth. Current incident logs, metrics, or
  deployment records must support the final cause.
- Sensitive log fields are desensitized before they are formatted for LLM use.
- The API returns `evidence_details` so demos and UIs can expand an evidence ID
  into a bounded log, metric, deployment, or runbook summary.

This is the main difference between the project and a prompt-only demo.

## 4. Why Controlled Tools Matter

The agent does not generate arbitrary PromQL or shell commands.

Prometheus access is hidden behind `PrometheusMetricsProvider`, which maps
whitelisted metric names to fixed PromQL templates:

- `request_rate`
- `error_rate`
- `latency_p95`
- `jvm_threads_active`
- `db_pool_active_ratio`
- `redis_latency_p95`
- `downstream_latency_p95`
- `mq_lag`

This reduces security risk and makes evaluation reproducible.

## 5. Evaluation Strategy

The evaluation dataset covers 12 fault templates with 4 variants each:

- clean case
- noisy case
- unrelated deployment
- tool unavailable
- wrong runbook

The important metrics are:

- Root Cause Top-1 Accuracy
- Root Cause Top-3 Recall
- Forbidden Conclusion Rate
- Inconclusive Rate
- Symptom-as-Cause Rate

The key lesson is that Runbook Recall@K and Root Cause Top-K are different
metrics. A retrieved runbook can help, but it is not itself the root-cause score.

## 6. Fault Coverage

The current evaluation covers:

- MySQL slow query / missing index
- MySQL connection pool exhaustion
- Redis timeout
- Redis hot key
- downstream payment timeout
- downstream payment 5xx
- HTTP connection pool exhaustion
- thread pool saturation
- configuration error
- deployment NPE regression
- rate limit / circuit breaker
- MQ consumer lag

This gives enough breadth to discuss classification, evidence ambiguity, and
tool failure behavior.

## 7. Live Demo Flow

Recommended demo path:

1. Start VM infrastructure and verify ports.
2. Start the three Java services.
3. Verify Prometheus targets are `up == 1`.
4. Open the Grafana dashboard.
5. Trigger a fault.
6. Send an incident to the Python diagnosis API.
7. Show the report:
   - Top causes
   - supporting evidence IDs
   - missing evidence
   - tool failures
   - recommended actions
8. Connect the diagnosis back to logs and metrics.

Useful checks:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-vm-connection.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-local-observability.ps1
```

One-command demo:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run-demo.ps1
```

The demo can run in two modes:

- `AGENT_MODE=rule`: deterministic RCA graph, best for stable evaluation.
- `AGENT_MODE=llm`: DeepSeek-powered planning/hypothesis/reporting with the
  same evidence tools and a rule-based fallback.

## 8. Design Tradeoffs

### MVP File Logs vs Loki

The live log provider currently reads Spring Boot log files from `logs/`.
This is simpler than deploying Promtail/Loki and is enough to prove the tool
contract. The agent does not care whether logs come from files, Loki, or
Elasticsearch as long as the provider returns bounded structured evidence.

Future upgrade:

```text
FileLogProvider -> LokiLogProvider
same query_logs contract, different backend
```

### Rule-Based Fallback vs LLM

The rule-based graph gives deterministic evaluation and regression protection.
The LLM path can improve natural-language reasoning, but it should not replace
evidence governance.

The product stance is:

- deterministic tools and scoring first
- LLM for synthesis and explanation
- fallback when LLM fails or budget is exceeded

### Fake Providers vs Real Providers

Fake providers are not a shortcut; they are test fixtures for reproducibility.
Real providers are used for live demos and integration tests.

This separation is why evaluation remains stable while Prometheus/file logs can
be enabled for realistic demonstrations.

## 9. What To Say In An Interview

Short version:

> I built an evidence-driven incident diagnosis agent for Spring Boot
> microservices. The agent does not directly guess root causes. It creates a
> bounded investigation plan, calls controlled tools for logs, metrics,
> deployments, and runbooks, then ranks Top-3 hypotheses only when evidence can
> be traced. I also built a 48-case evaluation set to measure Top-1, Top-3,
> forbidden conclusions, and inconclusive behavior.

Depth points:

- Tool whitelisting prevents arbitrary PromQL or unsafe operations.
- Evidence IDs create traceability from final report back to raw observations.
- Missing and contradictory evidence are first-class outputs.
- Prometheus and file logs make the demo realistic without coupling the agent
  to a specific observability backend.
- Rule-based evaluation protects against LLM hallucination and regression.
- The architecture can evolve provider by provider without rewriting the agent.

## 10. Next Extensions

High-value next steps:

- Replace file logs with Loki while keeping the same `query_logs` contract.
- Add a real deployment provider backed by Git commit metadata or a MySQL table.
- Add dedicated evidence detail endpoints if the UI needs lazy loading.
- Store completed reports in MySQL for audit history.
- Add a demo script that triggers faults and calls the diagnosis API end to end.
