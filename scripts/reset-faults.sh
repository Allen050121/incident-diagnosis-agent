# Fault Reset Script
# Usage: bash scripts/reset-faults.sh

set -e

SERVICES=(
  "order-service:9081"
  "inventory-service:9082"
  "payment-mock-service:9083"
)

echo "Resetting all fault toggles..."

for service in "${SERVICES[@]}"; do
  name="${service%%:*}"
  port="${service##*:}"
  echo "  Resetting $name (port $port)..."
  curl -s -X POST "http://localhost:$port/internal/v1/faults/reset" || echo "  Warning: Failed to reset $name"
done

echo "All faults reset successfully!"
