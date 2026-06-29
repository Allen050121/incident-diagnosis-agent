# Demo Walkthrough

This walkthrough shows the project as a complete incident-diagnosis product
without building a custom frontend.

## Demo Goal

Show a full RCA loop:

```text
fault injection -> traffic -> logs and metrics -> diagnosis API -> evidence-backed report
```

Grafana is used as the observability UI. FastAPI returns the diagnosis report.

## Prerequisites

1. VM infrastructure is running:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-vm-connection.ps1
```

2. Java services are running on Windows:

- order-service: `localhost:9081`
- inventory-service: `localhost:9082`
- payment-mock-service: `localhost:9083`

3. Python agent is running:

```powershell
cd python
D:\yangjw\software\Miniconda\envs\incident-agent\python.exe -m uvicorn app.main:app --reload --port 8000
```

4. For live evidence, set in `python/.env`:

```env
METRICS_PROVIDER=prometheus
PROMETHEUS_URL=http://192.168.85.66:9090
LOG_PROVIDER=file
LOG_BASE_DIR=../logs
AGENT_MODE=llm
```

Use `AGENT_MODE=rule` for deterministic rule-based demos. Use `AGENT_MODE=llm`
to call DeepSeek with the same live evidence providers and rule fallback.

## One-Command Demo

From the project root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run-demo.ps1
```

Optional reset at the end:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run-demo.ps1 -ResetAfter
```

## What To Show

### 1. Grafana

Open:

```text
http://192.168.85.66:3000/d/incident-diagnosis-overview/incident-diagnosis-overview
```

Point out:

- service health
- request rate
- max request latency
- JVM live threads
- JVM memory

### 2. Diagnosis API Output

The script prints:

- `status`
- Top-3 root causes
- supporting evidence IDs
- `evidence_details`
- recommended actions

The strongest explanation point is `evidence_details`: it connects each final
claim back to a bounded log, metric, deployment, or runbook summary.

## Interview Explanation

Recommended narrative:

> I intentionally did not build a custom frontend first. Grafana already solves
> metric visualization well. The product depth is in controlled evidence
> collection, hypothesis ranking, evidence governance, and repeatable
> evaluation. The API exposes structured RCA output, so a frontend can be added
> later without changing the diagnosis pipeline.

## Reset Faults

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:9081/internal/v1/faults/reset
Invoke-RestMethod -Method Post -Uri http://localhost:9082/internal/v1/faults/reset
Invoke-RestMethod -Method Post -Uri http://localhost:9083/internal/v1/faults/reset
```

## Troubleshooting

If `logs/*.log` is missing, restart the Java services after the latest
`application.yml` changes. The log path defaults to:

```text
D:/yangjw/workspace/incident-diagnosis-agent/logs
```

If Prometheus targets are down, check:

```text
http://192.168.85.66:9090/targets
```
