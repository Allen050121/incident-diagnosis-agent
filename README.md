# 微服务故障诊断 Agent | Log, Metrics & Runbook Evidence-Driven RCA

面向 Spring Boot 微服务的研发故障诊断 Agent,能够根据告警自动调用受控工具收集证据,输出 Top-3 根因候选、证据和下一步处置建议。

## 项目定位

当线上接口出现超时、错误率升高或消息积压时,Agent 可以:
- 自动查询日志、指标和最近变更
- 检索相关 Runbook/历史案例
- 形成根因假设并验证关键假设
- 输出可追溯证据的诊断报告

## 技术栈

**Java 后端:**
- Java 21 + Spring Boot 3
- Micrometer + Actuator
- MySQL 8 + Redis
- Resilience4j

**Python Agent:**
- Python 3.12
- FastAPI + LangGraph
- Pydantic v2
- Elasticsearch/Loki + Prometheus

**基础设施:**
- Docker Compose
- GitHub Actions

## 项目结构

```text
.
├── java/                          # Java 模块
│   ├── order-service/            # 订单入口服务
│   ├── inventory-service/        # 库存服务
│   ├── payment-mock-service/     # 支付模拟服务
│   └── incident-platform/        # 诊断平台(告警、任务管理)
├── python/                        # Python Agent
│   └── app/
│       ├── api/                  # HTTP API
│       ├── agent/                # LangGraph 工作流
│       ├── domain/               # 领域模型
│       ├── infrastructure/       # 工具、LLM、检索
│       └── tests/                # 测试
├── docker/                        # Docker Compose 配置
├── scripts/                       # 故障注入、评测脚本
└── docs/                          # 设计文档
```

## 快速开始

### 前置条件

- Docker & Docker Compose v2
- JDK 21
- Python 3.12

### 启动环境

```bash
# 启动基础设施
docker-compose up -d mysql redis loki prometheus

# 启动 Java 服务
cd java/incident-platform && ./mvnw spring-boot:run

# 启动 Python Agent
cd python && pip install -r requirements.txt && uvicorn app.main:app --reload
```

### 运行故障注入测试

```bash
./scripts/run-fault-injection.sh
```

## 核心功能

- **告警解析**: 将告警转换为结构化诊断任务
- **受控调查工具**: query_logs, query_metrics, query_deployments, search_runbooks
- **调查计划**: 根据告警类型选择 2-4 个调查步骤
- **根因假设与验证**: 形成最多三个候选假设并验证
- **诊断报告**: 输出 Top-3 根因、证据和建议

## 故障场景

首期支持 12 类确定性故障:
1. MySQL 慢 SQL
2. MySQL 连接池耗尽
3. Redis 请求超时
4. Redis 热 Key
5. 下游支付接口超时
6. 下游支付接口返回 5xx
7. HTTP 连接池耗尽
8. 线程池队列满
9. 配置错误
10. 发布后空指针异常
11. 限流或熔断触发
12. RocketMQ 消费积压

## 评测指标

- Root Cause Top-1 Accuracy
- Root Cause Top-3 Recall
- Evidence Precision
- Tool Selection Accuracy
- 平均诊断耗时和 Token 成本

## 开发阶段

当前处于 **阶段 0: 故障与评测定义**

详见 [开发文档](02-研发故障诊断Agent-MVP产品与开发文档.md)

## License

MIT
