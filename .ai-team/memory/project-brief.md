---
title: Project Brief
tags:
  - ai-team/memory
  - context
status: active
---

# Project Brief

> Keep this file short. It is loaded by every agent, so every stale sentence costs tokens and can cause mistakes.

## Project Identity

- Project name: incident-diagnosis-agent
- Current purpose: AI-powered root cause analysis for Spring Boot microservices
- Repository root: `D:/yangjw/workspace/incident-diagnosis-agent`
- Working directory: `D:/yangjw/workspace/incident-diagnosis-agent`

## Technical Context

- Language: Java 21, Python 3.12
- Framework: Spring Boot 3.2, FastAPI + LangGraph
- Package manager: Maven (Java), pip (Python)
- Deployment target: Docker Compose (local), Vercel (optional)

## Project Structure

- `java/` - Four Spring Boot microservices (order-service, inventory-service, payment-mock-service, incident-platform)
- `python/` - FastAPI Agent with LangGraph workflow
- `docker/` - Infrastructure configs (MySQL, Redis, Prometheus, Loki, Elasticsearch, RocketMQ)
- `scripts/` - Fault injection and evaluation scripts
- `docs/` - Design documents and setup guides

## Default Commands

- Install: `cd java && mvn clean install` / `cd python && pip install -r requirements.txt`
- Dev: `mvn spring-boot:run` (Java services) / `uvicorn app.main:app --reload` (Python)
- Build: `mvn package` (Java)
- Test: `mvn test` (Java) / `pytest` (Python)
- Lint: `ruff check .` (Python)

## Verification Policy

Every task card must list at least one verification command or a clear reason verification is not applicable.

