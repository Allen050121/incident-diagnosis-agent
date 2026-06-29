# Agent State Diagram

## Diagnosis Pipeline Overview

```
                    +------------------+
                    |   INCIDENT       |
                    |   Received       |
                    +--------+---------+
                             |
                             v
                    +------------------+
                    |   OPEN           |
                    |   Parse &        |
                    |   Validate       |
                    +--------+---------+
                             |
                             v
                    +------------------+
                    |  INVESTIGATING   |
                    |                  |
                    | 1. Classify      |
                    |    Alert Type    |
                    +--------+---------+
                             |
              +--------------+--------------+
              |              |              |
              v              v              v
     +----------------+ +----------------+ +----------------+
     | P95_LATENCY    | | ERROR_RATE     | | THROUGHPUT_LOW |
     | _HIGH          | | _HIGH          | | / MQ_LAG_HIGH  |
     +-------+--------+ +-------+--------+ +-------+--------+
              |                  |                  |
              +------------------+------------------+
                                 |
                                 v
                    +------------------+
                    |  Create Plan     |
                    |  (2-4 steps)     |
                    |                  |
                    | Rule-based or    |
                    | LLM-generated    |
                    +--------+---------+
                             |
                             v
                    +------------------+
                    |  Collect Evidence|
                    |                  |
                    | query_logs       |
                    | query_metrics    |
                    | query_deployments|
                    | search_runbooks  |
                    +--------+---------+
                             |
                             v
                    +------------------+
                    |  Build Hypotheses|
                    |  (Top-3)         |
                    |                  |
                    | Rule-based or    |
                    | LLM-generated    |
                    +--------+---------+
                             |
                             v
                    +------------------+
                    |  Validate        |
                    |  Evidence        |
                    |  Traceability    |
                    +--------+---------+
                             |
              +--------------+--------------+
              |                             |
              v                             v
     +------------------+        +------------------+
     | Has Evidence?    |        | No Evidence?     |
     | YES              |        |                  |
     +--------+---------+        +--------+---------+
              |                             |
              v                             v
     +------------------+        +------------------+
     | Generate Report  |        | INCONCLUSIVE     |
     |                  |        |                  |
     | Rule-based or    |        | Status:          |
     | LLM-generated    |        | INCONCLUSIVE     |
     +--------+---------+        +------------------+
              |
              v
     +------------------+
     | DIAGNOSED        |
     |                  |
     | Top-3 Causes     |
     | + Evidence IDs   |
     | + Actions        |
     +------------------+
```

## State Transitions

```
OPEN ──────────────► INVESTIGATING ──────────► DIAGNOSED
  │                       │                        ▲
  │                       │                        │
  │                       └─────► INCONCLUSIVE ────┘
  │                       │       (no evidence)
  │                       │
  │                       └─────► FAILED
  │                               (system error)
  │
  └─────► QUEUED ──────► INVESTIGATING
          (async mode)
```

## Async Task Lifecycle (Phase 5)

```
            +-----------+
            | PENDING   |  Task created, waiting in Redis Stream
            +-----+-----+
                  |
                  v
            +-----------+
            | CLAIMED   |  Worker picked up the task
            +-----+-----+
                  |
         +--------+--------+
         |                 |
         v                 v
   +-----------+     +-----------+
   | RUNNING   |     | CANCELLED |  User cancelled
   +-----+-----+     +-----------+
         |
    +----+----+
    |         |
    v         v
+---------+ +---------+
| COMPLETED| | FAILED  |
+---------+ +---------+
    │
    └──► Checkpoint saved at each node
         (crash recovery supported)
```

## LLM vs Rule-Based Decision Points

| Pipeline Step | Rule-Based | LLM-Powered |
|---|---|---|
| Plan Creation | Hardcoded per alert type | LLM generates 2-4 steps dynamically |
| Hypothesis Generation | Pattern matching on evidence keywords | LLM analyzes evidence semantically |
| Report Generation | Template-based actions per cause code | LLM generates contextual recommendations |
| Fallback | N/A | Falls back to rule-based when LLM unavailable |

## Evidence Governance (Phase 4)

```
Evidence Collected
        │
        v
+------------------+
| Dedup similar    |  Merge log entries with same pattern
| log entries      |
+--------+---------+
         |
         v
+------------------+
| Trim to budget   |  Keep errors > warns > info
| (max tokens)     |
+--------+---------+
         |
         v
+------------------+
| Filter by level  |  Remove DEBUG/TRACE
+--------+---------+
         |
         v
+------------------+
| Assign Evidence  |  Each piece gets unique ID
| IDs              |  (LOG-xxxx, METRIC-xxxx, etc.)
+--------+---------+
         |
         v
+------------------+
| Traceability     |  Hypothesis must reference
| Check            |  real evidence IDs
+------------------+
```
