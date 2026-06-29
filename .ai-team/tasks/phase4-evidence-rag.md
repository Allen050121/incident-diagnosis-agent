---
title: "阶段4：证据治理与RAG"
task_id: "phase4-evidence-rag"
status: "completed"
owner: "dispatcher"
task_type: "implementation"
delivery_stage: "build"
mode: "serial"
work_mode: "MVP"
workflow_mode: "standard"
created: "2026-06-29"
dependencies:
  - phase3-agent-diagnosis
verification_status: passed
last_run_id: phase4-evidence-rag-executor-20260629110000
last_result: passed
blocked_reason:
branch:
github_issue:
github_pr:
ci_status:
tags:
  - ai-team/task
---

# Task: 阶段4：证据治理与RAG

## Status

- Task ID: `phase4-evidence-rag`
- Owner: `dispatcher`
- Work Mode: `MVP`
- Workflow Mode: `standard`

## Business Goal

Implement evidence governance: log dedup/trimming, runbook versioning with lifecycle, BM25 search, no-evidence conclusion validation, and full evidence traceability.

## Implementation Scope

### Log Processing
- Template-based dedup (normalize similar log messages)
- Aggregate error counts by level
- Keep representative samples
- Max character/entry limits

### Runbook Store
- Runbook model with version, status (valid/deprecated/pending_verification)
- effective_from/effective_to dates, content_hash
- In-memory store for MVP

### BM25 Search
- BM25 text scoring for runbook retrieval
- Recall@K and MRR evaluation metrics

### Evidence Governance
- No-evidence conclusion validation (reject unverified hypotheses)
- Evidence traceability (report conclusions must reference real evidence)
- Expired/deprecated runbooks excluded from high-confidence evidence

### Testing
- 10+ unit tests covering all new modules

## Exit Criteria

- [x] 最终报告中的每条关键结论都可追溯
- [x] 过期或版本不适用的Runbook不会成为有效依据
- [x] 日志去重后保留代表性样本
- [x] BM25检索可返回相关Runbook

## Verification

- ✅ Run `pytest` - 30/30 tests pass (1.24s)
- ✅ Test diagnosis API with curl - evidence traceability verified
- ✅ Runbook versioning and lifecycle tested
- ✅ BM25 search and MRR evaluation tested
