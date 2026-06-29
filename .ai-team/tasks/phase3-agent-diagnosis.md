---
title: "阶段3：Agent最小诊断链路"
task_id: "phase3-agent-diagnosis"
status: "completed"
owner: "dispatcher"
task_type: "implementation"
delivery_stage: "build"
mode: "serial"
work_mode: "MVP"
workflow_mode: "standard"
created: "2026-06-29"
dependencies:
  - phase2-observability-api
verification_status: passed
last_run_id: phase3-agent-diagnosis-executor-20260629101500
last_result: passed
blocked_reason:
branch:
github_issue:
github_pr:
ci_status:
tags:
  - ai-team/task
---

# Task: 阶段3：Agent最小诊断链路

## Status

- Task ID: `phase3-agent-diagnosis`
- Owner: `dispatcher`
- Work Mode: `MVP`
- Workflow Mode: `standard`

## Business Goal

Implement the minimal Agent diagnosis pipeline: incident parsing → investigation plan → 4 tools → hypothesis generation → diagnosis report. With Fake Tool unit tests.

## Implementation Scope

### Python Agent Core
- Domain models: InvestigationPlan, enhanced DiagnosisReport
- 4 tools: query_logs, query_metrics, query_deployments, search_runbooks
- Unified tool executor with evidence ID tracking
- Agent graph nodes: load_incident, classify, plan, evidence, hypotheses, report
- Synchronous diagnosis API endpoint

### Testing
- 15 seed unit tests with Fake Tool implementations
- Tests cover: each tool, plan generation, hypothesis building, report output

## Exit Criteria

- [x] 15 条种子测试可完整运行
- [x] POST /api/v1/diagnose returns diagnosis report
- [x] Tools return evidence IDs
- [x] Hypotheses have supporting/contradicting evidence
- [x] Report references only real evidence

## Verification

- ✅ Run `pytest` - all 15 tests pass (1.21s)
- ✅ Test diagnosis API with curl - returns DIAGNOSED status with evidence
