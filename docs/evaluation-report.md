# Evaluation Report: Incident Diagnosis Pipeline

## Overview

This report records the reproducible evaluation for the diagnosis pipeline. The default evaluation command runs the deterministic rule-based agent over 48 labeled cases. LLM integration is available as a primary runtime path with rule-based fallback, but live LLM scores depend on API availability and are not used as the default CI-quality gate.

**Test date:** 2026-06-29
**LLM model:** deepseek-v4-flash
**Test scenarios:** 12 fault templates x 4 variants = 48 evaluation cases
**Command:** `cd python && python -m app.evaluation.run_full_eval`

## Architecture Comparison

| Aspect | Rule-Based Baseline | LLM-Powered Runtime |
|---|---|---|
| Plan creation | Deterministic per alert type | LLM generates dynamically |
| Evidence collection | Controlled tools | Controlled tools |
| Hypothesis generation | Evidence pattern matching | Semantic evidence analysis |
| Report generation | Template-based actions | Contextual recommendations |
| Fallback | N/A | Auto-fallback to rule-based |
| Token cost | 0 | Estimated ~900 tokens per diagnosis |
| Latency | Near-zero in fake-tool evaluation | Estimated 1-5s network + inference |

## Scenario Coverage

| Scenario | Expected Cause Code | Rule-Based Result |
|---|---|---|
| MySQL slow query | DATABASE_SLOW_QUERY | Pass |
| MySQL connection pool exhausted | DATABASE_CONNECTION_POOL_EXHAUSTED | Pass |
| Redis timeout | REDIS_TIMEOUT | Pass |
| Redis hot key | REDIS_TIMEOUT | Pass |
| Downstream payment timeout | DOWNSTREAM_SERVICE_FAILURE | Pass |
| Downstream payment 5xx | DOWNSTREAM_SERVICE_FAILURE | Pass |
| HTTP connection pool exhausted | RESOURCE_EXHAUSTION | Pass |
| Thread pool full | RESOURCE_EXHAUSTION | Pass |
| Configuration error | APPLICATION_ERROR_SPIKE | Pass |
| Deployment NPE | RECENT_DEPLOYMENT_REGRESSION | Pass |
| Rate limit / circuit breaker | RESOURCE_EXHAUSTION | Pass |
| MQ consumer lag | MQ_CONSUMER_ERROR | Pass |

## Evaluation Metrics

| Metric | Rule-Based Baseline | Notes |
|---|---:|---|
| Total cases | 48 | 12 faults x 4 variants |
| Root cause Top-1 accuracy | 100.0% | 48/48 |
| Root cause Top-3 recall | 100.0% | 48/48 |
| Forbidden violation rate | 0.0% | No forbidden root cause appears |
| Inconclusive rate | 0.0% | All cases diagnosed |
| Diagnosed rate | 100.0% | All cases reached DIAGNOSED |
| Average latency | ~0.1ms | Local deterministic fake-tool evaluation |

## Controlled Experiments

| Experiment | Result |
|---|---|
| Raw/no-tools vs agent with tools | Agent with tools: Top-1 12/12; raw baseline: Top-1 12/12 in the deterministic simulation |
| With vs without runbook | With runbook: Top-1 12/12; without runbook: Top-1 11/12 |
| With vs without verification | With verification: Top-1 12/12; without verification: Top-1 11/12 |
| Full logs vs deduplicated logs | Same Top-1 result; deduplicated logs reduce processing cost and latency |

## Quality Observations

1. Case-specific evidence is required. The evaluation runner now injects fault-specific logs, metrics, deployment records, and runbooks for each case instead of scoring every case against the same MySQL evidence.
2. The deterministic rule-based pipeline is a stable CI-quality baseline for the fixed 12-fault MVP scope.
3. LLM-powered diagnosis remains useful for richer explanations and recommendations, but should be evaluated separately when live API access is available.
4. Forbidden conclusions are explicitly checked so symptom/root-cause confusion is visible in metrics.

## Fallback Behavior

When the LLM API is unavailable, such as an empty API key or network error:

1. `LLMDiagnosisAgent.diagnose()` checks `llm_client.is_available`.
2. If unavailable, it delegates to the rule-based fallback.
3. The fallback produces the deterministic baseline result.
4. The full Python test suite passes with 102 tests.

## Conclusions

1. The deterministic baseline now passes the full labeled evaluation: 48/48 Top-1, 48/48 Top-3, and 0 forbidden violations.
2. Cost is zero for the rule-based baseline and estimated at about $0.0005 per LLM diagnosis.
3. LLM latency is acceptable for incident diagnosis workflows, where seconds are usually tolerable.
4. Keep the rule-based pipeline as the CI-quality baseline and use LLM-powered diagnosis as the richer runtime path with automatic fallback.
