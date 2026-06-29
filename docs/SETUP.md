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
# Terminal 1 - Order Service
cd java/order-service
mvn spring-boot:run

# Terminal 2 - Inventory Service
cd java/inventory-service
mvn spring-boot:run

# Terminal 3 - Payment Mock Service
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

- Order Service: http://localhost:9081/actuator/health
- Inventory Service: http://localhost:9082/actuator/health
- Payment Mock: http://localhost:9083/actuator/health
- Python Agent: http://localhost:8000/health
- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000 (admin/admin)
- Loki: http://localhost:3100

## Next Steps

1. Implement fault injection scenarios in `java/*/src/main/java/.../faultinjection/`
2. Run evaluation pipeline: `cd python && python -m app.evaluation.run_full_eval`
3. Inject faults and test diagnosis: `bash scripts/trigger-fault.sh order-service mysql-slow-query`

## Troubleshooting

### Database Connection Issues

Check MySQL is running and credentials match `application.yml` settings.

### Redis Connection Issues

Verify Redis is accessible: `redis-cli ping`

### Port Conflicts

Modify port numbers in `application.yml` files if ports 9081-9083 are already in use.
