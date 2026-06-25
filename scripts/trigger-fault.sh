# Fault Trigger Script
# Usage: bash scripts/trigger-fault.sh <service-name> <fault-id> [delay_ms]

set -e

if [ $# -lt 2 ]; then
  echo "Usage: $0 <service-name> <fault-id> [delay_ms]"
  echo "Example: $0 order-service mysql-slow-query-001 1800"
  exit 1
fi

SERVICE_NAME=$1
FAULT_ID=$2
DELAY_MS=${3:-1000}

declare -A SERVICE_PORTS
SERVICE_PORTS=(
  ["order-service"]=9081
  ["inventory-service"]=9082
  ["payment-mock-service"]=9083
)

PORT=${SERVICE_PORTS[$SERVICE_NAME]}

if [ -z "$PORT" ]; then
  echo "Error: Unknown service $SERVICE_NAME"
  echo "Available services: ${!SERVICE_PORTS[@]}"
  exit 1
fi

echo "Triggering fault: $FAULT_ID on $SERVICE_NAME (port $PORT)..."
echo "Parameters: delay_ms=$DELAY_MS"

curl -s -X POST "http://localhost:$PORT/internal/v1/faults/$FAULT_ID/activate" \
  -H "Content-Type: application/json" \
  -d "{\"delay_ms\": $DELAY_MS}"

echo ""
echo "Fault triggered successfully!"
echo "Test with: curl http://localhost:$PORT/api/..."
echo "Reset with: bash scripts/reset-faults.sh"
