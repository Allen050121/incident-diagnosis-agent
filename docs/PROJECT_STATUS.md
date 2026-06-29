# 项目初始化完成总结

## 已完成的工作

### 1. 项目基础结构
- [x] README.md - 项目介绍和快速开始
- [x] .gitignore - Git 忽略配置
- [x] 目录结构 (java/, python/, docker/, scripts/, docs/)

### 2. Docker Compose 基础设施
- [x] docker-compose.yml - MySQL, Redis, Prometheus, Grafana, Loki, Elasticsearch, RocketMQ
- [x] docker/prometheus/prometheus.yml - Prometheus 抓取配置

### 3. Java Spring Boot 项目 (3个微服务)
- [x] java/pom.xml - 父 POM (Spring Boot 3.2.0, Java 21)
- [x] order-service - 订单服务 (端口 9081)
  - 故障注入: 12 种故障场景
  - 观测查询 API
- [x] inventory-service - 库存服务 (端口 9082)
  - 故障注入: 库存相关故障
- [x] payment-mock-service - 支付模拟服务 (端口 9083)
  - 故障注入: 支付相关故障

### 4. Python FastAPI Agent
- [x] python/requirements.txt - 依赖 (LangGraph, FastAPI, Pydantic等)
- [x] app/main.py - FastAPI 主应用
- [x] app/config.py - 应用配置
- [x] app/api/router.py - API 路由
- [x] app/domain/incident.py - 领域模型 (Incident, Evidence, Hypothesis, DiagnosisReport)
- [x] app/agent/graph.py - 规则诊断 Agent
- [x] app/agent/llm_graph.py - LLM 诊断 Agent (DeepSeek V4 Flash)
- [x] app/evaluation/ - 评估框架 (48 用例, 4 对照实验)
- [x] app/tests/ - 102 个测试全部通过

### 5. 脚本和文档
- [x] scripts/run-fault-injection.sh - 故障注入脚本框架
- [x] scripts/trigger-fault.sh - 故障触发脚本
- [x] scripts/reset-faults.sh - 故障重置脚本
- [x] docs/SETUP.md - 详细设置指南
- [x] docs/agent-state-diagram.md - Agent 状态流转图
- [x] docs/fault-inventory.md - 12 种故障场景清单
- [x] docs/evaluation-report.md - LLM vs 规则引擎评估报告
- [x] .github/workflows/ci.yml - GitHub Actions CI

## 技术栈概览

```
Java 后端:          Spring Boot 3.2 + Java 21 + Micrometer + Resilience4j
Python Agent:       FastAPI + LangGraph + Pydantic v2
LLM:               DeepSeek V4 Flash (OpenAI 兼容 API)
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
| order-service | 9081 | 订单服务 |
| inventory-service | 9082 | 库存服务 |
| payment-mock-service | 9083 | 支付模拟 |
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
3. 分别启动 3 个 Java 服务
4. `cd python && pip install -r requirements.txt && uvicorn app.main:app --reload` 启动 Python Agent
