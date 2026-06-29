# Final Acceptance Notes

Date: 2026-06-29

## Delivery Status

The project is accepted as a demo-ready and interview-ready MVP.

Core delivery:

- Spring Boot fault lab with `order-service`, `inventory-service`, and `payment-mock-service`.
- Python FastAPI diagnosis agent with rule-based and DeepSeek-powered runtime modes.
- Evidence collection from Prometheus metrics, file logs, deployment records, and runbooks.
- Evidence-governed Top-3 root cause ranking with supporting evidence IDs.
- LLM guardrails for mandatory evidence collection, hypothesis reranking, and status downgrade protection.
- Prometheus and Grafana observability on the VM.
- One-command demo script for the MySQL slow-query scenario.

## Runtime Topology

Windows host:

- Java services:
  - `order-service`: `localhost:9081`
  - `inventory-service`: `localhost:9082`
  - `payment-mock-service`: `localhost:9083`
- Python agent:
  - `localhost:8000`
  - Conda interpreter: `D:\yangjw\software\Miniconda\envs\incident-agent\python.exe`

VM `192.168.85.66`:

- MySQL
- Redis
- Elasticsearch
- Docker
- Prometheus: `http://192.168.85.66:9090`
- Grafana: `http://192.168.85.66:3000`

Prometheus scrapes the Windows services through the VMnet8 host address:

- `192.168.85.1:9081`
- `192.168.85.1:9082`
- `192.168.85.1:9083`

## Final Demo Command

From the project root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\run-demo.ps1
```

Expected diagnosis:

- `Status: DIAGNOSED`
- Top cause: `DATABASE_SLOW_QUERY`
- Evidence includes:
  - Prometheus `latency_p95`
  - Prometheus `db_pool_active_ratio` as negative evidence against pool exhaustion
  - file log evidence from `order-service.log`
  - deployment background evidence
  - MySQL slow-query runbook match when the LLM chooses to search runbooks

## Final Verification Commands

Python:

```powershell
cd D:\yangjw\workspace\incident-diagnosis-agent\python
D:\yangjw\software\Miniconda\envs\incident-agent\python.exe -m ruff check app
D:\yangjw\software\Miniconda\envs\incident-agent\python.exe -m pytest app\tests -q
D:\yangjw\software\Miniconda\envs\incident-agent\python.exe -m app.evaluation.run_full_eval
```

Java:

```powershell
cd D:\yangjw\workspace\incident-diagnosis-agent\java
mvn test -q
```

Observability:

```powershell
cd D:\yangjw\workspace\incident-diagnosis-agent
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify-vm-connection.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify-local-observability.ps1
```

## Latest Verified Results

- Ruff: passed.
- Python tests: 113 passed.
- Evaluation dataset: 48 cases.
- Rule-based Top-1 accuracy: 100%.
- Rule-based Top-3 recall: 100%.
- Forbidden conclusion violations: 0%.
- Java tests: passed.
- Grafana dashboard: service health, request rate, latency, JVM threads, and JVM memory panels show data.

## Interview Talking Points

Use this framing:

> I built an evidence-driven incident diagnosis agent for Spring Boot microservices.
> The system collects bounded evidence from Prometheus, logs, deployment records, and runbooks, then ranks root cause hypotheses with traceable evidence IDs.
> DeepSeek is used for planning, synthesis, and explanation, but deterministic guardrails prevent hallucinated or evidence-free conclusions.

Important technical depth:

- LLM is not allowed to diagnose without evidence.
- Mandatory evidence collection prevents the LLM from skipping key metrics.
- Negative evidence removes contradicted hypotheses, such as low DB pool usage refuting connection pool exhaustion.
- Rule-based evaluation provides a stable CI-quality baseline.
- Prometheus/file providers make the demo realistic without coupling the agent to one storage backend.

## Known Non-Issues

- The project does not need a custom frontend for the MVP. Grafana handles metric visualization, and the FastAPI response is the diagnosis product surface.
- `python/.env` must remain local and must not be committed.
- PyCharm Spring Boot services should show only the three current Java services. If a deleted service appears, remove the stale local run configuration from the IDE.
