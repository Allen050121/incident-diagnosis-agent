# 研发故障诊断 Agent MVP 产品与开发文档

> 文档定位：用于指导个人项目开发、故障样本构造、自动评测和面试准备。  
> 核心原则：不做大而全 AIOps，只解决一次告警后的证据收集与根因候选生成。  
> MVP 模式：自建小型、可重复、可标注的微服务故障靶场。

## 1. 项目定位

### 1.1 项目名称

**面向 Spring Boot 微服务的研发故障诊断 Agent**

简历可用名称：

> 微服务故障诊断 Agent｜日志、指标与 Runbook 证据驱动 RCA

### 1.2 要解决的实际问题

当线上接口出现超时、错误率升高或消息积压时，研发人员通常需要在多个系统之间切换：

- 查看告警信息。
- 查询相关服务日志。
- 查看数据库、Redis、线程池和接口指标。
- 检查最近发布和配置变更。
- 阅读 Runbook 和历史故障记录。
- 形成根因假设并继续验证。

真正耗时的部分不是生成一段“可能是数据库问题”的文字，而是收集足够上下文、区分症状与根因、给出可追溯证据。

本项目的目标是让 Agent 根据一次告警自动调用受控工具收集证据，输出 Top-3 根因候选、证据和下一步处置建议。

### 1.3 产品目标

MVP 验证四个目标：

1. Agent 能否根据告警选择正确的调查工具。
2. Agent 能否在有限预算内形成和验证根因假设。
3. 输出结论能否引用真实日志、指标、发布记录或 Runbook。
4. 在工具失败、证据冲突和信息不足时能否正确表达不确定性。

### 1.4 非目标

首期明确不做：

- Kubernetes、多云和真实生产集群接入。
- 自动修改配置、扩容、重启或回滚。
- 自动执行修复命令。
- 完整 CMDB、APM 或告警平台。
- 复杂多 Agent 并行协作。
- 通用日志问答机器人。
- 机器学习异常检测模型训练。
- 全量日志直接输入大模型。
- 为展示而引入 Kafka、Flink、ClickHouse 等重型组件。

## 2. 使用者与业务流程

### 2.1 目标用户

- Java 后端开发：快速获取排查方向。
- 测试开发：运行故障注入和诊断回归。
- SRE/运维：查看诊断证据和 Runbook 建议。

### 2.2 MVP 主流程

```text
故障注入器触发一个已知故障
  -> 告警服务生成 Incident
  -> Java 创建诊断任务并写入 Redis Streams
  -> Python Agent 消费任务
  -> 解析告警并读取服务拓扑
  -> 生成受约束的调查计划
  -> 查询日志、指标和最近变更
  -> 检索相关 Runbook/历史案例
  -> 形成根因假设
  -> 调用工具验证关键假设
  -> 输出 Top-3 根因、证据和建议
  -> 自动与故障标签比较并生成评测报告
```

### 2.3 MVP 系统范围

故障靶场只包含三个 Java 服务：

- `order-service`：订单入口和核心请求链路。
- `inventory-service`：库存查询与扣减模拟。
- `payment-mock-service`：支付服务模拟。

基础设施：

- MySQL。
- Redis。
- RocketMQ 可选；若加入只用于构造消息积压案例。

不要搭建更多业务模块。项目重点是诊断链路，不是业务系统规模。

## 3. 故障场景设计

### 3.1 首期故障类型

建议实现 12 个确定性故障模板，每类生成不同参数的测试实例：

1. MySQL 慢 SQL。
2. MySQL 连接池耗尽。
3. Redis 请求超时。
4. Redis 热 Key 导致局部延迟。
5. 下游支付接口超时。
6. 下游支付接口返回 5xx。
7. HTTP 连接池耗尽。
8. 线程池队列满。
9. 配置错误导致接口启动后持续失败。
10. 发布新版本后空指针异常。
11. 限流或熔断触发。
12. RocketMQ 消费积压，可作为进阶项。

### 3.2 故障模板结构

每个模板必须定义：

```yaml
fault_id: mysql-slow-query-001
category: DATABASE
root_cause: MISSING_INDEX
affected_service: order-service
trigger:
  type: feature_toggle
  parameters:
    delay_ms: 1800
expected_signals:
  logs:
    - "query execution exceeded threshold"
  metrics:
    - "db_query_p95 > 1500ms"
  deployments: []
expected_tools:
  - query_metrics
  - query_logs
  - search_runbooks
forbidden_conclusions:
  - REDIS_TIMEOUT
```

故障必须可重复触发、可清理、可回到初始状态。

### 3.3 故障标签

区分：

- `root_cause`：真正原因。
- `symptoms`：错误率、延迟等表现。
- `contributing_factors`：放大故障的条件。
- `affected_components`：受影响组件。

评测时不能将症状命中当作根因命中。

## 4. 核心功能

### 4.1 告警解析

输入：

```json
{
  "incidentId": "INC-1001",
  "service": "order-service",
  "endpoint": "/api/orders",
  "alertType": "P95_LATENCY_HIGH",
  "value": 2840,
  "threshold": 1000,
  "startedAt": "2026-06-22T10:00:00+08:00"
}
```

输出：

```json
{
  "incidentType": "LATENCY",
  "scope": "SINGLE_ENDPOINT",
  "timeWindow": {
    "start": "2026-06-22T09:55:00+08:00",
    "end": "2026-06-22T10:05:00+08:00"
  },
  "initialHypotheses": [
    "DOWNSTREAM_LATENCY",
    "DATABASE_LATENCY",
    "RESOURCE_SATURATION"
  ]
}
```

时间窗口必须受限，避免查询海量日志。

### 4.2 受控调查工具

首期只实现四个工具：

#### `query_logs`

输入：

- 服务名。
- 时间范围。
- 关键词或 Trace ID。
- 最大返回条数。

输出：

- 日志摘要。
- 原始日志引用 ID。
- 错误类型统计。
- 是否发生截断。

#### `query_metrics`

可查询的指标白名单：

- 请求量。
- 错误率。
- p50/p95 延迟。
- JVM 线程池活跃数。
- 数据库连接池使用率。
- Redis 调用延迟。
- 下游接口延迟。
- MQ Lag，可选。

不允许 Agent 生成任意 PromQL。MVP 使用结构化参数映射到预定义查询模板，降低安全风险并方便评测。

#### `query_deployments`

查询：

- 最近版本。
- 发布时间。
- Git Commit。
- 配置变更摘要。
- 发布人使用虚拟数据。

#### `search_runbooks`

检索：

- 故障排查手册。
- 历史故障案例。
- 服务拓扑说明。
- 中间件使用约束。

工具返回必须带证据 ID，最终报告只能引用真实返回内容。

### 4.3 调查计划

Agent 根据告警类型选择 2-4 个步骤，不允许生成无限计划。

示例：

```json
{
  "steps": [
    {
      "tool": "query_metrics",
      "purpose": "确认延迟发生在应用、数据库还是下游"
    },
    {
      "tool": "query_logs",
      "purpose": "查找同一时间窗口的异常和超时"
    },
    {
      "tool": "query_deployments",
      "purpose": "确认是否存在同时段发布变更"
    }
  ]
}
```

计划不是最终事实，后续可以根据工具结果增加一次验证步骤，但总工具调用次数受预算限制。

### 4.4 根因假设与验证

Agent 形成最多三个候选假设：

```json
{
  "hypothesis": "DATABASE_CONNECTION_POOL_EXHAUSTED",
  "supportingEvidence": ["METRIC-102", "LOG-883"],
  "contradictingEvidence": ["DEPLOY-EMPTY"],
  "nextVerification": {
    "tool": "query_metrics",
    "parameters": {
      "metric": "db_pool_active_ratio"
    }
  }
}
```

要求：

- 支持证据和反证都必须保存。
- 没有证据的假设不得排在第一位。
- Agent 必须区分“确定”“可能”“证据不足”。
- 置信度必须有校准说明，不能当作统计概率。

### 4.5 诊断报告

输出：

```json
{
  "incidentId": "INC-1001",
  "status": "DIAGNOSED",
  "topCauses": [
    {
      "rank": 1,
      "causeCode": "DATABASE_CONNECTION_POOL_EXHAUSTED",
      "confidence": "HIGH",
      "evidenceIds": ["METRIC-102", "LOG-883"],
      "reasoningSummary": "数据库连接池活跃连接持续达到上限..."
    }
  ],
  "recommendedActions": [
    "检查慢查询和未释放连接",
    "核对连接池上限与数据库最大连接数"
  ],
  "missingEvidence": [],
  "toolFailures": []
}
```

MVP 不执行建议动作。

## 5. 技术架构

### 5.1 总体架构

```text
故障控制台 / Vue 3
  | REST / SSE
Spring Boot 3 诊断平台 + 故障靶场
  | Redis Streams: Incident 任务
  | HTTP/JSON: 日志、指标、发布查询
FastAPI + LangGraph Agent
  | Elasticsearch/Loki: 日志与 Runbook
  | Prometheus: 指标
  | Langfuse/OpenTelemetry: Agent Trace
MySQL + Redis
```

### 5.2 技术栈

Java：

- Java 21
- Spring Boot 3
- Spring Boot Actuator
- Micrometer
- Resilience4j
- MySQL 8
- Redis
- Spring Data Redis
- JUnit 5
- Testcontainers
- Toxiproxy，用于网络故障注入

Python：

- Python 3.12
- FastAPI
- LangGraph
- Pydantic v2
- redis-py
- HTTPX
- pytest + pytest-asyncio
- Ruff + mypy

日志与指标：

- Prometheus。
- Grafana 可用于展示，不是核心依赖。
- Loki 或 Elasticsearch 二选一。
- OpenTelemetry 可在第二阶段接入 Trace；首期先保证日志和指标稳定。

RAG：

- Runbook 和历史案例数量较小时优先使用 Elasticsearch BM25。
- 只有同义表达导致召回不足时再增加向量检索。
- 不把全部日志做向量化。

部署：

- Docker Compose。
- GitHub Actions。
- 故障注入脚本。

### 5.3 为什么不直接二开大型 AIOps 项目

大型开源项目通常依赖 Kubernetes、多云、PagerDuty、Datadog 或复杂多 Agent。直接 Fork 会带来：

- 环境过重。
- 无法证明核心代码由自己实现。
- 难以构建确定性标准答案。
- 面试时容易停留在配置和部署层。

本项目只参考它们的调查流程、证据模型和报告结构，故障靶场、工具、状态图和评测由自己实现。

可参考：

- `Arvo-AI/aurora`
- `martinimarcello00/SRE-agent`
- `awesome-LLM-AIOps`

## 6. 工程结构

### 6.1 Java 模块

```text
com.example.incident
├── interfaces
├── application
├── domain
│   ├── incident
│   ├── diagnosis
│   ├── faultscenario
│   └── agenttask
└── infrastructure
    ├── persistence
    ├── redis
    ├── observability
    ├── faultinjection
    └── config
```

核心模型：

- `Incident`
- `DiagnosisTask`
- `DiagnosisReport`
- `FaultScenario`

状态：

```text
OPEN
  -> QUEUED
  -> INVESTIGATING
  -> DIAGNOSED / INCONCLUSIVE / FAILED / CANCELLED
```

### 6.2 Python 模块

```text
app
├── api
├── application
├── domain
│   ├── incident.py
│   ├── evidence.py
│   ├── hypothesis.py
│   └── report.py
├── agent
│   ├── graph.py
│   ├── state.py
│   ├── nodes
│   └── prompts
├── infrastructure
│   ├── tools
│   ├── llm
│   ├── retrieval
│   ├── redis_stream
│   └── observability
└── tests
```

工具通过统一执行器调用：

```text
参数校验
  -> 权限和白名单
  -> 超时
  -> 执行
  -> 结果截断
  -> 证据登记
  -> Trace
  -> 错误归一化
```

## 7. Agent 工作流

### 7.1 状态

```text
incident
service_topology
investigation_plan
evidence
hypotheses
tool_failures
budget
final_report
trace_context
```

### 7.2 节点

```text
load_incident
  -> classify_incident
  -> load_topology
  -> create_plan
  -> collect_initial_evidence
  -> build_hypotheses
  -> select_verification
  -> verify_hypotheses
  -> validate_evidence
  -> generate_report
  -> complete / inconclusive / fail
```

### 7.3 循环边界

允许“假设 -> 验证”循环，但必须同时满足：

- 尚未达到最大验证轮次。
- 尚未超过工具调用预算。
- 尚未超过 Token 预算。
- 存在可以通过工具验证的假设。
- 任务未超过总时限。

达到边界后输出 `INCONCLUSIVE`，不能强行给出根因。

## 8. Java 与 Python 通信

### 8.1 Redis Streams

任务流：

```text
incident:diagnosis:tasks
incident:diagnosis:retry
incident:diagnosis:dlq
```

事件流：

```text
incident:diagnosis:events:{taskId}
```

消息只包含任务标识和必要元数据，不放完整日志：

```json
{
  "messageId": "M1001",
  "taskId": "D1001",
  "incidentId": "INC-1001",
  "schemaVersion": 1,
  "traceId": "TRACE-1001",
  "deadlineAt": "2026-06-22T10:02:00+08:00"
}
```

### 8.2 HTTP 工具接口

Python 调用 Java 或观测网关：

- `/internal/v1/logs/query`
- `/internal/v1/metrics/query`
- `/internal/v1/deployments/query`
- `/internal/v1/topology/{service}`

工具接口必须做：

- 服务身份认证。
- 参数范围限制。
- 时间窗口限制。
- 返回条数限制。
- 查询审计。

### 8.3 SSE

向前端推送：

- 调查开始。
- 调用工具。
- 收到证据。
- 形成假设。
- 验证假设。
- 诊断完成或证据不足。

不直接展示完整 Chain-of-Thought，只展示结构化步骤、工具状态和可验证证据。

## 9. 证据与上下文工程

### 9.1 日志裁剪

禁止将全部日志传给模型。处理流程：

```text
限定服务与时间窗口
  -> 按 Trace ID/异常级别筛选
  -> 模板化去重
  -> 聚合错误计数
  -> 保留代表性样本
  -> 限制最大字符数
```

记录是否截断，避免模型误以为看到完整数据。

### 9.2 指标上下文

指标返回结构化趋势：

```json
{
  "metric": "db_pool_active_ratio",
  "window": "10m",
  "baseline": 0.42,
  "peak": 1.0,
  "anomalyStart": "2026-06-22T09:59:30+08:00"
}
```

尽量不把大量原始时序点传给模型。

### 9.3 Runbook RAG

Runbook 文档应围绕具体故障：

- 症状。
- 检查步骤。
- 关键指标。
- 常见根因。
- 安全处置建议。
- 不适用条件。

检索结果是参考资料，不是事实证据。最终根因必须由当前 Incident 的日志、指标或变更记录支持。

### 9.4 上下文预算

为不同类型数据设置预算：

- 告警和拓扑：固定保留。
- 日志摘要：最大 N 条代表样本。
- 指标：最大 N 个关键指标。
- Runbook：Top-K。
- 历史步骤：保留结构化摘要。

## 10. 故障处理与可靠性

### 10.1 工具错误分类

| 错误 | 策略 |
|---|---|
| 查询参数非法 | 不重试，修正一次 |
| 日志服务超时 | 重试一次，记录证据缺失 |
| 指标服务不可用 | 熔断，继续使用其余证据 |
| 权限不足 | 立即终止对应工具 |
| 无数据 | 标记为空，不让模型补造 |
| 返回过大 | 截断并记录 |

### 10.2 任务恢复

- 每个关键节点写入 LangGraph Checkpoint。
- Agent 结果和证据索引持久化。
- Python Worker 崩溃后通过 Pending Claim 恢复。
- 已登记的证据使用 ID 去重。
- 工具查询尽量只读，降低重复执行风险。

### 10.3 取消

用户取消任务后：

- Java 更新任务状态。
- Python 每个节点开始前检查取消标记。
- 停止后续模型和工具调用。
- 保留已收集证据和 Token 成本。

## 11. 模型路由和成本

### 11.1 首期路由

不要设计复杂动态路由。首期：

- 小模型：告警分类、日志结构化摘要。
- 主模型：调查计划、假设和报告。
- 备用模型：主模型不可用时降级。

保留路由的条件：

- 小模型方案降低成本。
- 任务成功率没有显著下降。
- 总延迟可以接受。

### 11.2 任务预算

每次诊断限制：

- 最大计划步骤数。
- 最大工具调用次数。
- 最大验证轮次。
- 最大模型调用次数。
- 最大输入/输出 Token。
- 最大执行时间。
- 最大模型费用。

超预算返回 `INCONCLUSIVE_BUDGET_EXCEEDED`。

## 12. 评测方案

### 12.1 数据集

首期 12 个故障模板，每个生成 3-5 个实例，总计 40-60 个案例。

变化参数：

- 故障持续时间。
- 告警阈值。
- 噪声日志比例。
- 是否同时存在无关发布记录。
- 某个工具是否临时不可用。
- 是否存在相似但错误的 Runbook。

### 12.2 核心指标

- Root Cause Top-1 Accuracy。
- Root Cause Top-3 Recall。
- Symptom-as-Cause Error Rate。
- Evidence Precision。
- Evidence Coverage。
- Tool Selection Accuracy。
- Tool Argument Accuracy。
- Unsupported Conclusion Rate。
- Inconclusive Precision：选择证据不足是否合理。
- 平均工具调用次数。
- p50/p95 诊断耗时。
- 单任务 Token 与成本。

### 12.3 指标定义注意

Top-1 命中：

> 排名第一的 `causeCode` 与故障模板标准根因一致。

Top-3 命中：

> 标准根因出现在前三个候选中。

证据有效：

> 引用的证据真实存在，时间窗口正确，并能够支持对应结论。

不能仅使用 LLM-as-a-Judge 判断根因正确性；根因代码和证据 ID 可以程序化比较。

### 12.4 对照实验

至少执行：

1. 直接将告警交给模型 vs Agent 调工具。
2. 无 Runbook vs 加入 Runbook RAG。
3. 无验证轮次 vs 一次假设验证。
4. 全量日志截取 vs 日志模板去重与摘要。

目标是证明每个复杂设计确实改善命中率、证据质量或成本。

### 12.5 故障注入测试

自动脚本流程：

```text
reset environment
  -> trigger fault
  -> wait for alert
  -> create diagnosis task
  -> wait for completion
  -> compare result
  -> collect metrics
  -> clean fault
```

每次运行保存：

- Git Commit。
- 故障模板版本。
- 模型和 Prompt 版本。
- 工具配置。
- 原始 Agent Trace。
- 最终报告。

## 13. 可观测性

统一 Trace：

```text
incident_id
  -> diagnosis_task_id
  -> message_id
  -> graph_node
  -> model_call_id
  -> tool_call_id
  -> evidence_id
```

必须回答：

- 任务排队多久？
- 模型和工具分别耗时多久？
- 哪个工具失败？
- 哪条证据支持最终根因？
- Agent 为什么增加验证步骤？
- Token 花在日志、Runbook 还是报告生成？
- 失败属于模型、工具、数据还是流程？

## 14. 安全边界

即使只读，也要控制：

- Agent 不允许执行 Shell。
- Agent 不允许生成任意 SQL 或 PromQL。
- 工具使用白名单参数。
- 时间范围和返回量有限制。
- 日志中的用户输入视为不可信内容。
- 日志脱敏手机号、Token、密码和请求头。
- Runbook 内的命令只作为文本，不自动执行。
- 前端不展示模型私有推理过程。

参考 OWASP Agentic Application 风险，重点关注：

- 工具滥用。
- 不可信上下文诱导。
- 过度权限。
- 资源耗尽。
- 敏感数据泄露。

## 15. 开发阶段

### 阶段 0：故障与评测定义

交付物：

- 12 个故障模板设计。
- 根因、症状、证据定义。
- 15 条种子测试。
- 评测指标。

退出条件：

- 每个故障都能通过程序判断标准根因。

### 阶段 1：最小故障靶场

实现：

- 三个 Spring Boot 服务。
- MySQL 和 Redis。
- Actuator/Micrometer。
- 故障开关。
- 自动重置脚本。

退出条件：

- 12 个故障均可重复触发和清理。
- 日志和指标能呈现预期信号。

### 阶段 2：观测查询 API

实现：

- 日志查询。
- 指标查询。
- 发布查询。
- 服务拓扑。
- 查询限制和结构化返回。

退出条件：

- 不使用 LLM 也能通过 API 获取标准证据。

### 阶段 3：Agent 最小诊断链路

实现：

- Incident 解析。
- 调查计划。
- 四个工具。
- 假设和报告。
- Fake Tool 单元测试。

退出条件：

- 15 条种子测试可完整运行。

### 阶段 4：证据治理与 RAG

实现：

- 日志聚合、去重和裁剪。
- Runbook 入库。
- 证据 ID。
- 支持证据和反证。
- 无证据结论校验。

退出条件：

- 最终报告中的每条关键结论都可追溯。

### 阶段 5：异步任务与恢复

实现：

- Redis Streams。
- Outbox。
- Pending/Claim。
- Checkpointer。
- SSE。
- 取消和超时。

退出条件：

- Worker 宕机后任务可恢复。
- SSE 断开不影响任务执行。

### 阶段 6：完整评测

实现：

- 40-60 个案例。
- 故障注入流水线。
- 对照实验。
- Token、成本和延迟报告。
- 失败归因。

退出条件：

- 一条命令运行完整测试。
- 每次架构修改可以自动回归。

### 阶段 7：展示与简历证据

交付物：

- README。
- 系统拓扑图。
- Agent 状态图。
- 故障清单。
- 评测报告。
- 一次 Worker 崩溃恢复演示。
- 一次证据不足返回 `INCONCLUSIVE` 的演示。

## 16. MVP 验收标准

功能：

- 支持 12 类故障。
- 支持四个调查工具。
- 输出 Top-3 根因。
- 输出证据和建议。
- 工具失败时允许降级。
- 证据不足时可以不下结论。

工程：

- 故障可重复触发。
- Agent 可恢复。
- 工具调用可审计。
- Fake Tool 可单测。
- Docker Compose 一键启动。

数据：

- 40-60 条固定案例。
- Top-1、Top-3、证据和成本报告。
- 至少四组对照实验。

## 17. 重点面试问题

- 为什么是 Agent，而不是固定告警规则？
- 如何区分症状和根因？
- 为什么不直接把日志全部给模型？
- 日志和指标冲突时怎么处理？
- 如何定义 Top-3 根因命中率？
- 为什么 Runbook 不是事实证据？
- 工具查询失败时是否还能下结论？
- 如何避免模型伪造日志？
- 为什么不自动修复？
- Redis Streams 如何恢复宕机任务？
- 为什么不使用多 Agent？
- 模型路由是否真的降低成本？
- 故障样本是否足够接近生产？

## 18. 已知不足

- 故障靶场规模远小于真实生产系统。
- 指标和日志模式由自己设计，存在数据偏差。
- 单故障为主，复杂连锁故障覆盖不足。
- 根因标签是封闭集合，泛化能力有限。
- 没有接入真实 CMDB 和变更平台。
- 无自动修复闭环。

这些不足应在 README 和面试中主动说明，并解释 MVP 优先验证的是工具使用、证据链和可评测诊断流程。

## 19. 后续优化

按数据暴露的问题推进：

- 增加组合故障和噪声事件。
- 引入 OpenTelemetry Trace。
- 使用真实开源微服务 Demo 作为第二套靶场。
- 根据失败案例优化调查策略。
- 对高置信度、低风险建议增加人工确认后的半自动处置。
- 对 Agent 诊断结果进行线上反馈闭环。
- 使用 OpenTelemetry GenAI 语义规范统一模型和工具 Span。

## 20. 参考资料

- [LangGraph Overview](https://docs.langchain.com/oss/python/langgraph/overview)
- [LangGraph Durable Persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
- [Redis Streams](https://redis.io/docs/latest/develop/data-types/streams/)
- [OpenTelemetry AI Agent Observability](https://opentelemetry.io/blog/2025/ai-agent-observability/)
- [OWASP Agentic AI Threats and Mitigations](https://genai.owasp.org/resource/agentic-ai-threats-and-mitigations/)
- [Exploring LLM-based Agents for Root Cause Analysis](https://arxiv.org/html/2403.04123v1)
- [Awesome LLM AIOps](https://github.com/Jun-jie-Huang/awesome-LLM-AIOps)
- [Aurora](https://github.com/Arvo-AI/aurora)
- [SRE-agent](https://github.com/martinimarcello00/SRE-agent)

