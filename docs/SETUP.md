# Project Setup Guide

## Prerequisites

- JDK 21
- Maven 3.8+
- Python 3.12
- Docker & Docker Compose v2

## Quick Start

### 1. Start Infrastructure

```bash
docker-compose up -d mysql redis loki prometheus elasticsearch
```

Verify services:
```bash
docker-compose ps
```

### 2. Build Java Services

```bash
cd java
mvn clean install -DskipTests
```

### 3. Run Java Services (in separate terminals)

```bash
# Terminal 1 - Incident Platform
cd java/incident-platform
mvn spring-boot:run

# Terminal 2 - Order Service
cd java/order-service
mvn spring-boot:run

# Terminal 3 - Inventory Service
cd java/inventory-service
mvn spring-boot:run

# Terminal 4 - Payment Mock Service
cd java/payment-mock-service
mvn spring-boot:run
```

### 4. Setup Python Environment

```bash
cd python
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 5. Run Python Agent

```bash
uvicorn app.main:app --reload --port 8000
```

### 6. Verify All Services

- Incident Platform: http://localhost:8080/actuator/health
- Order Service: http://localhost:8081/actuator/health
- Inventory Service: http://localhost:8082/actuator/health
- Payment Mock: http://localhost:8083/actuator/health
- Python Agent: http://localhost:8000/health
- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000 (admin/admin)
- Loki: http://localhost:3100

## Next Steps

1. Configure fault injection scenarios in `java/incident-platform/src/main/java/com/example/incident/faultscenario/`
2. Implement LangGraph workflow in `python/app/agent/graph.py`
3. Add tool implementations in `python/app/infrastructure/tools/`
4. Create Runbook documents for RAG

## Troubleshooting

### Database Connection Issues

Check MySQL is running and credentials match `application.yml` settings.

### Redis Connection Issues

Verify Redis is accessible: `redis-cli ping`

### Port Conflicts

Modify port numbers in `application.yml` files if ports 8080-8083 are already in use.
