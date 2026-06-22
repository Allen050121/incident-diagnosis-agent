# 项目初始化完成总结

## 已完成的工作

### 1. 项目基础结构
- [x] README.md - 项目介绍和快速开始
- [x] .gitignore - Git 忽略配置
- [x] 目录结构 (java/, python/, docker/, scripts/, docs/)

### 2. Docker Compose 基础设施
- [x] docker-compose.yml - MySQL, Redis, Prometheus, Grafana, Loki, Elasticsearch, RocketMQ
- [x] docker/prometheus/prometheus.yml - Prometheus 抓取配置

### 3. Java Spring Boot 项目 (4个微服务)
- [x] java/pom.xml - 父 POM (Spring Boot 3.2.0, Java 21)
- [x] incident-platform - 诊断平台 (端口 8080)
  - Incident 实体类
  - IncidentController REST API
  - application.yml 配置
- [x] order-service - 订单服务 (端口 8081)
- [x] inventory-service - 库存服务 (端口 8082)
- [x] payment-mock-service - 支付模拟服务 (端口 8083)

### 4. Python FastAPI Agent
- [x] python/requirements.txt - 依赖 (LangGraph, FastAPI, Pydantic等)
- [x] app/main.py - FastAPI 主应用
- [x] app/config.py - 应用配置
- [x] app/api/router.py - API 路由
- [x] app/domain/incident.py - 领域模型 (Incident, Evidence, Hypothesis, DiagnosisReport)

### 5. 脚本和文档
- [x] scripts/run-fault-injection.sh - 故障注入脚本框架
- [x] docs/SETUP.md - 详细设置指南

## 下一步工作 (按开发阶段)

### 阶段 0: 故障与评测定义
- [ ] 实现 12 个故障模板的 YAML 定义
- [ ] 创建故障标签和根因分类体系
- [ ] 设计评测指标计算逻辑

### 阶段 1: 最小故障靶场
- [ ] 实现故障开关机制 (feature toggle)
- [ ] 添加慢 SQL、连接池耗尽等故障注入代码
- [ ] 实现自动重置脚本
- [ ] 验证日志和指标信号

### 阶段 2: 观测查询 API
- [ ] 实现 /internal/v1/logs/query
- [ ] 实现 /internal/v1/metrics/query
- [ ] 实现 /internal/v1/deployments/query
- [ ] 实现 /internal/v1/topology/{service}

### 阶段 3: Agent 最小诊断链路
- [ ] 实现 LangGraph 工作流节点
- [ ] 实现四个工具 (query_logs, query_metrics, query_deployments, search_runbooks)
- [ ] 实现调查计划生成
- [ ] 实现假设形成和验证
- [ ] 实现诊断报告生成

### 阶段 4: 证据治理与 RAG
- [ ] 实现日志聚合、去重和裁剪
- [ ] 导入 Runbook 文档到 Elasticsearch
- [ ] 实现 BM25 检索
- [ ] 实现证据 ID 追踪

## 技术栈概览

```
Java 后端:          Spring Boot 3.2 + Java 21 + Micrometer + Resilience4j
Python Agent:       FastAPI + LangGraph + Pydantic v2
数据库:             MySQL 8 + Redis
日志存储:           Loki (或 Elasticsearch)
指标存储:           Prometheus
可视化:             Grafana
消息队列(可选):      RocketMQ
部署:               Docker Compose
```

## 端口分配

| 服务 | 端口 | 说明 |
|------|------|------|
| incident-platform | 8080 | 诊断平台 |
| order-service | 8081 | 订单服务 |
| inventory-service | 8082 | 库存服务 |
| payment-mock-service | 8083 | 支付模拟 |
| Python Agent | 8000 | Agent API |
| Prometheus | 9090 | 指标存储 |
| Grafana | 3000 | 可视化 |
| Loki | 3100 | 日志存储 |
| Elasticsearch | 9200 | Runbook RAG |
| MySQL | 3306 | 数据库 |
| Redis | 6379 | 缓存/任务队列 |
| RocketMQ | 9876/10909 | 消息队列 |

## 启动顺序

1. `docker-compose up -d` 启动基础设施
2. `cd java && mvn clean install` 构建 Java 项目
3. 分别启动 4 个 Java 服务
4. `cd python && pip install -r requirements.txt && uvicorn app.main:app --reload` 启动 Python Agent
