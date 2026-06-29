#!/bin/bash
# Run fault injection tests for the incident diagnosis agent

set -e

echo "=== Running Fault Injection Tests ==="

# Check if services are running
echo "Checking service availability..."
curl -s http://localhost:9081/actuator/health > /dev/null || echo "Warning: order-service not responding"
curl -s http://localhost:9082/actuator/health > /dev/null || echo "Warning: inventory-service not responding"
curl -s http://localhost:9083/actuator/health > /dev/null || echo "Warning: payment-mock-service not responding"

echo ""
echo "Available fault scenarios:"
echo "  1. MySQL slow query"
echo "  2. MySQL connection pool exhaustion"
echo "  3. Redis timeout"
echo "  4. Redis hot key"
echo "  5. Payment service timeout"
echo "  6. Payment service 5xx errors"
echo "  7. HTTP connection pool exhaustion"
echo "  8. Thread pool queue full"
echo "  9. Configuration error"
echo "  10. NullPointerException after deployment"
echo "  11. Rate limiting/circuit breaker trigger"
echo "  12. RocketMQ consumer lag"
echo ""
echo "Usage: ./scripts/trigger-fault.sh <service> <fault_id>"
echo "Example: ./scripts/trigger-fault.sh order-service mysql-slow-query"
