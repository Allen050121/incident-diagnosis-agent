#!/bin/bash
# Verify infrastructure ports on the VM used by this project.

echo "=== Verifying Virtual Machine Connectivity ==="

VM_HOST="${VM_HOST:-192.168.85.66}"
TIMEOUT_MS="${TIMEOUT_MS:-3000}"

# Check network connectivity
echo "1. Checking network connectivity..."
ping -n 2 "$VM_HOST" || echo "Warning: Cannot ping VM"

check_port() {
  local name="$1"
  local port="$2"
  echo ""
  echo "Checking ${name} port (${port})..."
  powershell -NoProfile -Command "\$client = [System.Net.Sockets.TcpClient]::new(); \$async = \$client.BeginConnect('${VM_HOST}', ${port}, \$null, \$null); \$connected = \$async.AsyncWaitHandle.WaitOne(${TIMEOUT_MS}, \$false); if (\$connected -and \$client.Connected) { \$client.EndConnect(\$async); \$client.Close(); exit 0 } else { \$client.Close(); exit 1 }" \
    && echo "${name} reachable" \
    || echo "Warning: ${name} port not reachable"
}

check_port "MySQL" 3306
check_port "Redis" 6379
check_port "Elasticsearch" 9200
check_port "Prometheus" 9090
check_port "Grafana" 3000

echo ""
echo "=== Instructions ==="
echo ""
echo "If ports are not reachable, check VM firewall:"
echo "  sudo firewall-cmd --add-port=3306/tcp --permanent"
echo "  sudo firewall-cmd --add-port=6379/tcp --permanent"
echo "  sudo firewall-cmd --add-port=9200/tcp --permanent"
echo "  sudo firewall-cmd --add-port=9090/tcp --permanent"
echo "  sudo firewall-cmd --add-port=3000/tcp --permanent"
echo "  sudo firewall-cmd --reload"
echo ""
echo "For MySQL, also check bind-address in /etc/mysql/mysql.conf.d/mysqld.cnf:"
echo "  bind-address = 0.0.0.0"
echo ""
echo "Then run the SQL initialization script:"
echo "  mysql -u root -p < docker/init-db/01-init-database.sql"
