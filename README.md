# Incident Diagnosis Agent | Log, Metrics & Runbook Evidence-Driven RCA

AI-powered incident diagnosis agent for Spring Boot microservices. Automatically collects evidence from logs, metrics, deployments, and runbooks, then uses LLM (DeepSeek V4 Flash) to identify root causes with traceable evidence.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   incident-platform                  │
│              (Alert & Task Management)               │
│                   Port: 9084                         │
├──────────┬──────────┬───────────────┬───────────────┤
│  order-  │inventory-│   payment-    │               │
│  service │ service  │ mock-service  │               │
│  :9081   │  :9082   │   :9083       │               │
└──────────┴──────────┴───────────────┴───────────────┘
         │              │               │
         ▼              ▼               ▼
┌─────────────────────────────────────────────────────┐
│              Python Diagnosis Agent                   │
│         FastAPI + LangGraph + DeepSeek V4 Flash       │
│                   Port: 8000                          │
│                                                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐   │
│  │ LLM Plan │→ │ Evidence │→ │ LLM Hypotheses   │   │
│  │ Creation │  │ Collect  │  │ + Report Gen     │   │
│  └──────────┘  └──────────┘  └──────────────────┘   │
│        ↕              ↕               ↕              │
│  [Rule-Based Fallback when LLM unavailable]          │
└─────────────────────────────────────────────────────┘
         │              │               │
    ┌────┴───┐   ┌─────┴────┐   ┌─────┴──────┐
    │ MySQL  │   │  Redis   │   │Elasticsearch│
    │  :3306 │   │  :6379   │   │  :9200      │
    └────────┘   └──────────┘   └─────────────┘
```

## Tech Stack

| Layer | Technology |
|---|---|
| Java Backend | Java 21 + Spring Boot 3.2 + Micrometer |
| Python Agent | Python 3.12 + FastAPI + Pydantic v2 |
| LLM | DeepSeek V4 Flash (OpenAI-compatible API) |
| Database | MySQL 8 |
| Cache / Queue | Redis (config + task queue + SSE) |
| Search / RAG | Elasticsearch (Runbook BM25 search) |
| Monitoring | Prometheus + Grafana + Loki |
| Deployment | Docker Compose |

## Project Structure

```text
.
├── java/                          # 4 Spring Boot microservices
│   ├── order-service/             # Order entry service (:9081)
│   ├── inventory-service/         # Inventory service (:9082)
│   ├── payment-mock-service/      # Payment mock (:9083)
│   └── incident-platform/         # Diagnosis platform (:9084)
├── python/                        # Python FastAPI Agent
│   ├── .env.example               # Config template (copy to .env)
│   ├── app/
│   │   ├── agent/                 # Diagnosis pipeline
│   │   │   ├── graph.py           # Rule-based agent
│   │   │   ├── llm_graph.py       # LLM-powered agent
│   │   │   └── service.py         # Factory functions
│   │   ├── infrastructure/
│   │   │   ├── llm/               # DeepSeek LLM client
│   │   │   ├── tool_*.py          # Tool definitions & executor
│   │   │   └── evidence_*.py      # Evidence governance
│   │   ├── evaluation/            # LLM vs rule-based comparison
│   │   ├── domain/                # Incident, Evidence, Hypothesis models
│   │   └── tests/                 # 71 tests (all phases)
│   └── requirements.txt
├── docker/                        # Infrastructure configs
├── scripts/                       # Fault injection & eval scripts
└── docs/                          # Documentation
    ├── agent-state-diagram.md     # Pipeline state machine
    ├── fault-inventory.md         # 12 fault scenarios
    └── evaluation-report.md       # LLM vs rule-based analysis
```

## Quick Start

### Prerequisites

- Docker & Docker Compose v2
- JDK 21 + Maven
- Python 3.12 + Conda

### 1. Start Infrastructure

```bash
docker-compose up -d mysql redis loki prometheus elasticsearch
```

### 2. Start Java Services

```bash
cd java
mvn clean install
cd incident-platform && mvn spring-boot:run &
cd ../order-service && mvn spring-boot:run &
cd ../inventory-service && mvn spring-boot:run &
cd ../payment-mock-service && mvn spring-boot:run &
```

### 3. Start Python Agent

```bash
cd python
cp .env.example .env     # Edit .env with your API key
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 4. Run Diagnosis

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

### 5. Inject Faults

```bash
# Activate MySQL slow query
curl -X POST http://localhost:9081/internal/v1/faults/mysql-slow-query/activate \
  -H "Content-Type: application/json" \
  -d '{"delay_ms": 1800}'

# Reset
curl -X POST http://localhost:9081/internal/v1/faults/mysql-slow-query/reset
```

## Features

### Phase 1-2: Fault Injection & Observability
- 12 deterministic fault scenarios across 3 services
- Log/Metrics/Deployment/Topology query APIs

### Phase 3: Agent Diagnosis Pipeline
- 4 investigation tools: `query_logs`, `query_metrics`, `query_deployments`, `search_runbooks`
- Rule-based hypothesis generation with evidence tracking
- Top-3 root cause identification

### Phase 4: Evidence Governance & RAG
- Log deduplication, normalization, and trimming
- Runbook versioning and BM25 search
- Evidence traceability validation

### Phase 5: Async Tasks & Recovery
- Redis Streams task queue with claim/timeout pattern
- Checkpointer for crash recovery
- SSE real-time event streaming
- Task cancellation and deadline enforcement

### Phase 6: LLM Integration
- DeepSeek V4 Flash for plan/hypothesis/report generation
- Reasoning model support (content + reasoning_content)
- Token usage and cost tracking
- Auto-fallback to rule-based when LLM unavailable
- Evaluation module for LLM vs rule-based comparison

## Testing

```bash
cd python
pytest app/tests/ -v
# 71 tests across all phases
```

## Configuration

Copy `python/.env.example` to `python/.env` and configure:

| Variable | Description |
|---|---|
| `LLM_API_KEY` | DeepSeek API key (get from platform.deepseek.com) |
| `LLM_MODEL` | Model name (default: `deepseek-v4-flash`) |
| `LLM_BASE_URL` | API base URL (default: `https://api.deepseek.com`) |
| `DB_HOST` | MySQL host |
| `REDIS_HOST` | Redis host |
| `PLATFORM_URL` | incident-platform URL |

**Important:** Never commit `.env` to git. Only `.env.example` with placeholder values is tracked.

## Documentation

- [Agent State Diagram](docs/agent-state-diagram.md) - Pipeline visualization
- [Fault Inventory](docs/fault-inventory.md) - 12 fault scenarios
- [Evaluation Report](docs/evaluation-report.md) - LLM vs rule-based analysis

## License

MIT
