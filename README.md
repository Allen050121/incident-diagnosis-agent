# Incident Diagnosis Agent

Evidence-driven root cause analysis for Spring Boot microservices.

The project builds a small, repeatable fault lab and a Python diagnosis agent that collects evidence from logs, metrics, deployments, and runbooks. It outputs Top-3 root cause candidates with traceable evidence and recommended next actions. DeepSeek V4 Flash can be used for richer reasoning, with a deterministic rule-based fallback.

## Architecture

```text
Java fault targets
  order-service              :9081
  inventory-service          :9082
  payment-mock-service       :9083
        |
        v
Python Diagnosis Agent       :8000
  FastAPI + diagnosis graph
  Tools: logs, metrics, deployments, runbooks
  LLM path: DeepSeek V4 Flash
  Fallback: rule-based diagnosis
        |
        v
Infrastructure VM            192.168.85.66
  MySQL                      :3306
  Redis                      :6379
  Elasticsearch              :9200
  Prometheus                 :9090
  Grafana                    :3000
```

## Tech Stack

| Layer | Technology |
|---|---|
| Java backend | Java 21 + Spring Boot 3.2 + Micrometer |
| Python agent | Python 3.12 + FastAPI + Pydantic v2 |
| LLM | DeepSeek V4 Flash via OpenAI-compatible API |
| Database | MySQL 8 |
| Cache / queue | Redis |
| Search / RAG | Elasticsearch + BM25 runbook search |
| Monitoring | Prometheus + Grafana + Loki |
| Deployment | Docker Compose on VM + local Java/Python services |

## Project Structure

```text
.
|-- java/
|   |-- order-service/              # Order entry service (:9081)
|   |-- inventory-service/          # Inventory service (:9082)
|   `-- payment-mock-service/       # Payment mock (:9083)
|-- python/
|   |-- .env.example                # Config template
|   |-- app/
|   |   |-- agent/                  # Rule-based and LLM diagnosis graphs
|   |   |-- api/                    # FastAPI routes
|   |   |-- domain/                 # Incident, Evidence, Hypothesis models
|   |   |-- evaluation/             # 48-case evaluation pipeline
|   |   |-- infrastructure/         # Tools, queue, RAG, tracing
|   |   `-- tests/                  # 113 Python tests
|   `-- requirements.txt
|-- docker/                         # Infrastructure config
|-- scripts/                        # Fault injection and VM checks
`-- docs/                           # Setup, fault inventory, evaluation report
```

## Quick Start

### 1. Verify VM Infrastructure

```bash
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-vm-connection.ps1
```

Expected VM host: `192.168.85.66`.

To start Prometheus and Grafana on the VM, run this from the project root on the VM:

```bash
bash scripts/install-observability-vm.sh
```

Prometheus scrapes the Java services through the Windows VMnet8 host address `192.168.85.1`.

To let the Python diagnosis API use Prometheus for `query_metrics`, set this in `python/.env`:

```env
METRICS_PROVIDER=prometheus
PROMETHEUS_URL=http://192.168.85.66:9090
LOG_PROVIDER=file
LOG_BASE_DIR=../logs
AGENT_MODE=llm
```

The Java services write logs to the project `logs/` directory:

- `logs/order-service.log`
- `logs/inventory-service.log`
- `logs/payment-mock-service.log`

Restart the Java services after this configuration is added so the log files are created.

Check local Java health, Prometheus endpoints, and log files:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-local-observability.ps1
```

Import the demo Grafana dashboard from Windows:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/import-grafana-dashboard.ps1
```

Dashboard URL: `http://192.168.85.66:3000/d/incident-diagnosis-overview/incident-diagnosis-overview`

Run the end-to-end demo:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run-demo.ps1
```

The script prints the active agent mode. Use `AGENT_MODE=rule` for deterministic rule-based demos, or `AGENT_MODE=llm` to call DeepSeek with rule fallback.

Walkthrough: `docs/demo-walkthrough.md`.
Final acceptance notes: `docs/final-acceptance.md`.

### 2. Build Java Services

```bash
cd java
mvn clean install
```

### 3. Start Java Services

Open three terminals:

```bash
cd java/order-service
mvn spring-boot:run
```

```bash
cd java/inventory-service
mvn spring-boot:run
```

```bash
cd java/payment-mock-service
mvn spring-boot:run
```

### 4. Start Python Agent

```powershell
cd python
D:\yangjw\software\Miniconda\envs\incident-agent\python.exe -m uvicorn app.main:app --reload --port 8000
```

Copy `python/.env.example` to `python/.env` and set your real `LLM_API_KEY`. Do not commit `python/.env`.

### 5. Run Diagnosis

```bash
curl -X POST http://localhost:8000/api/v1/diagnose \
  -H "Content-Type: application/json" \
  -d '{
    "incident_id": "INC-001",
    "service": "order-service",
    "alert_type": "P95_LATENCY_HIGH",
    "value": 5000,
    "threshold": 1000,
    "started_at": "2026-06-29T10:00:00"
  }'
```

### 6. Inject Faults

```bash
curl -X POST http://localhost:9081/internal/v1/faults/mysql-slow-query/activate \
  -H "Content-Type: application/json" \
  -d '{"delay_ms": 1800}'
```

Reset:

```bash
bash scripts/reset-faults.sh
```

## Features

### Fault Lab And Observability

- 12 deterministic fault scenarios across 3 Spring Boot services
- Fault activation/reset APIs
- Log, metric, deployment, and topology query surfaces

### Diagnosis Pipeline

- Controlled tool usage: `query_logs`, `query_metrics`, `query_deployments`, `search_runbooks`
- Evidence IDs on every collected signal
- Evidence details with source, summary, query window, and bounded content
- Top-3 hypotheses with supporting and contradicting evidence
- Rule-based deterministic fallback

### Evidence Governance And RAG

- Log deduplication, normalization, trimming, and desensitization
- Runbook versioning and BM25 search
- Evidence traceability checks
- Expandable evidence details for demos and UI integration

### Async Tasks And Recovery

- Redis Streams task queue
- Checkpointer for crash recovery
- SSE event streaming
- Task cancellation and deadline handling

### LLM Integration

- DeepSeek V4 Flash for plan, hypothesis, and report generation
- Reasoning content support
- Token and cost tracking
- Automatic fallback when LLM is unavailable

## Verification

```powershell
cd python
D:\yangjw\software\Miniconda\envs\incident-agent\python.exe -m ruff check app
D:\yangjw\software\Miniconda\envs\incident-agent\python.exe -m pytest app/tests/ -q
D:\yangjw\software\Miniconda\envs\incident-agent\python.exe -m app.evaluation.run_full_eval
```

Expected current results:

- Ruff: `All checks passed`
- Python tests: `103 passed`
- Evaluation: Top-1 `100.0%`, Top-3 `100.0%`, forbidden violations `0.0%`

Java:

```bash
cd java
mvn test
```

## Configuration

| Variable | Description |
|---|---|
| `DB_HOST` | MySQL host, usually `192.168.85.66` |
| `DB_PORT` | MySQL port, usually `3306` |
| `REDIS_HOST` | Redis host, usually `192.168.85.66` |
| `REDIS_PORT` | Redis port, usually `6379` |
| `ELASTICSEARCH_URL` | Runbook search URL, usually `http://192.168.85.66:9200` |
| `LLM_API_KEY` | DeepSeek API key |
| `LLM_MODEL` | Default `deepseek-v4-flash` |
| `LLM_BASE_URL` | Default `https://api.deepseek.com` |

## Documentation

- [Setup Guide](docs/SETUP.md)
- [Agent State Diagram](docs/agent-state-diagram.md)
- [Fault Inventory](docs/fault-inventory.md)
- [Evaluation Report](docs/evaluation-report.md)

## Known Limitations

- The fault lab is much smaller than a production system.
- Logs, deployments, and runbooks use deterministic providers by default.
- Logs can use real Spring Boot log files via `LOG_PROVIDER=file`.
- Metrics can use either deterministic fake data or the Prometheus provider via `METRICS_PROVIDER=prometheus`.
- Evaluation focuses on single-fault scenarios.
- Root cause labels use a fixed vocabulary.
- Deployment data is mocked rather than integrated with a real CMDB.
- The system diagnoses and recommends; it does not auto-remediate.

These limits are intentional for the MVP. The goal is to validate controlled tool use, evidence chains, and repeatable diagnosis evaluation.

## License

MIT
