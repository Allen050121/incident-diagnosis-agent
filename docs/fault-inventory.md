# Fault Inventory

12 deterministic fault scenarios for testing the diagnosis agent.

## Fault Categories

### Database Faults

| # | Fault ID | Service | Description | Activation |
|---|----------|---------|-------------|------------|
| 1 | `mysql-slow-query` | order-service | MySQL slow SQL (>1800ms) | `POST /internal/v1/faults/mysql-slow-query/activate` |
| 2 | `mysql-connection-pool` | order-service | HikariCP connection pool exhausted | `POST /internal/v1/faults/mysql-connection-pool/activate` |

### Cache Faults

| # | Fault ID | Service | Description | Activation |
|---|----------|---------|-------------|------------|
| 3 | `redis-timeout` | inventory-service | Redis command timeout (>3000ms) | `POST /internal/v1/faults/redis-timeout/activate` |
| 4 | `redis-hot-key` | inventory-service | Redis hot key causing single-node overload | `POST /internal/v1/faults/redis-hot-key/activate` |

### Downstream Faults

| # | Fault ID | Service | Description | Activation |
|---|----------|---------|-------------|------------|
| 5 | `downstream-payment-timeout` | payment-mock-service | Payment API timeout (>3000ms) | `POST /internal/v1/faults/downstream-payment-timeout/activate` |
| 6 | `downstream-payment-5xx` | payment-mock-service | Payment API returns 503 errors | `POST /internal/v1/faults/downstream-payment-5xx/activate` |

### Resource Faults

| # | Fault ID | Service | Description | Activation |
|---|----------|---------|-------------|------------|
| 7 | `http-connection-pool` | order-service | HTTP client connection pool exhausted | `POST /internal/v1/faults/http-connection-pool/activate` |
| 8 | `thread-pool-full` | order-service | Tomcat thread pool queue full | `POST /internal/v1/faults/thread-pool-full/activate` |

### Configuration Faults

| # | Fault ID | Service | Description | Activation |
|---|----------|---------|-------------|------------|
| 9 | `config-error` | inventory-service | Missing/invalid configuration property | `POST /internal/v1/faults/config-error/activate` |
| 10 | `deployment-npe` | order-service | NullPointerException after deployment | `POST /internal/v1/faults/deployment-npe/activate` |

### Traffic Faults

| # | Fault ID | Service | Description | Activation |
|---|----------|---------|-------------|------------|
| 11 | `rate-limit-triggered` | order-service | Rate limiting / circuit breaker triggered | `POST /internal/v1/faults/rate-limit-triggered/activate` |
| 12 | `mq-consumer-lag` | inventory-service | RocketMQ consumer lag increasing | `POST /internal/v1/faults/mq-consumer-lag/activate` |

## Alert Types

| Alert Type | Trigger Condition | Expected Faults |
|---|---|---|
| `P95_LATENCY_HIGH` | P95 latency > threshold | 1, 2, 3, 7 |
| `ERROR_RATE_HIGH` | Error rate > threshold | 4, 5, 6, 8, 9, 10 |
| `THROUGHPUT_LOW` | Request rate drops | 3, 7, 8, 11 |
| `MQ_LAG_HIGH` | Consumer lag increasing | 12 |

## Expected Diagnosis Outcomes

| Fault | Expected Root Cause Code | Confidence |
|---|---|---|
| mysql-slow-query | `DATABASE_SLOW_QUERY` | HIGH |
| mysql-connection-pool | `DATABASE_CONNECTION_POOL_EXHAUSTED` | HIGH |
| redis-timeout | `REDIS_TIMEOUT` | HIGH |
| redis-hot-key | `REDIS_TIMEOUT` | MEDIUM |
| downstream-payment-timeout | `DOWNSTREAM_SERVICE_FAILURE` | HIGH |
| downstream-payment-5xx | `DOWNSTREAM_SERVICE_FAILURE` | HIGH |
| http-connection-pool | `RESOURCE_EXHAUSTION` | MEDIUM |
| thread-pool-full | `RESOURCE_EXHAUSTION` | MEDIUM |
| config-error | `APPLICATION_ERROR_SPIKE` | MEDIUM |
| deployment-npe | `RECENT_DEPLOYMENT_REGRESSION` | HIGH |
| rate-limit-triggered | `RESOURCE_EXHAUSTION` | MEDIUM |
| mq-consumer-lag | `MQ_CONSUMER_ERROR` | MEDIUM |

## Activation Examples

```bash
# Activate a fault
curl -X POST http://localhost:8081/internal/v1/faults/mysql-slow-query/activate \
  -H "Content-Type: application/json" \
  -d '{"delay_ms": 1800}'

# Deactivate a fault
curl -X POST http://localhost:8081/internal/v1/faults/mysql-slow-query/reset

# List active faults
curl http://localhost:8081/internal/v1/faults
```

## Service Ports

| Service | Port |
|---|---|
| order-service | 8081 |
| inventory-service | 8082 |
| payment-mock-service | 8083 |
