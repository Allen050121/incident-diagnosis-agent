---
title: "阶段5：异步任务与恢复"
task_id: "phase5-async-recovery"
status: "completed"
owner: "dispatcher"
task_type: "implementation"
delivery_stage: "build"
mode: "serial"
work_mode: "MVP"
workflow_mode: "standard"
created: "2026-06-29"
dependencies:
  - phase4-evidence-rag
verification_status: passed
last_run_id: phase5-async-recovery-executor-20260629120000
last_result: passed
blocked_reason:
branch:
github_issue:
github_pr:
ci_status:
tags:
  - ai-team/task
---

# Task: 阶段5：异步任务与恢复

## Status

- Task ID: `phase5-async-recovery`
- Owner: `dispatcher`
- Work Mode: `MVP`
- Workflow Mode: `standard`

## Business Goal

Implement async task processing with Redis Streams, crash recovery via Checkpointer, SSE real-time push, and task cancellation/timeout.

## Implementation Scope

### Redis Streams Task Queue
- Streams: `incident:diagnosis:tasks`, `incident:diagnosis:retry`, `incident:diagnosis:dlq`
- Outbox/Pending/Claim pattern
- Task claim with timeout, auto-retry

### Checkpointer
- Save agent state at key nodes
- Redis-based persistence
- Crash recovery: resume from last checkpoint

### SSE Real-time Push
- Events: investigation started, tool called, evidence received, hypothesis formed, diagnosis complete
- Per-task event streams
- SSE disconnect does not affect task execution

### Task Cancellation & Timeout
- Cancel running tasks
- Deadline enforcement
- Cleanup on cancellation

### Testing
- 10+ tests covering queue, checkpoint, SSE, cancellation

## Exit Criteria

- [x] Worker宕机后任务可恢复
- [x] SSE断开不影响任务执行
- [x] 任务可取消和超时

## Verification

- ✅ Run `pytest` - 43/43 tests pass (1.35s)
- ✅ Async diagnosis API tested
- ✅ Task status and cancel API tested
- ✅ SSE event streaming tested
