#!/usr/bin/env bash
set -euo pipefail

# Run this on the infrastructure VM from the project root.
# It starts the optional observability stack used by the demo.

VM_HOST="${VM_HOST:-192.168.85.66}"

echo "Starting Prometheus and Grafana on ${VM_HOST}..."

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required on the VM." >&2
  exit 1
fi

if docker compose version >/dev/null 2>&1; then
  COMPOSE=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE=(docker-compose)
else
  echo "docker compose or docker-compose is required on the VM." >&2
  exit 1
fi

"${COMPOSE[@]}" up -d prometheus grafana

echo ""
echo "Prometheus: http://${VM_HOST}:9090"
echo "Grafana:    http://${VM_HOST}:3000"
echo ""
echo "If either port is not reachable from Windows, open the VM firewall:"
echo "  sudo firewall-cmd --add-port=9090/tcp --permanent"
echo "  sudo firewall-cmd --add-port=3000/tcp --permanent"
echo "  sudo firewall-cmd --reload"
