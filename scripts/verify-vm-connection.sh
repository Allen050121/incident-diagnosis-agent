#!/bin/bash
# Verify MySQL and Redis connection on 192.168.85.66

echo "=== Verifying Virtual Machine Connectivity ==="

# Check network connectivity
echo "1. Checking network connectivity..."
ping -n 2 192.168.85.66 || echo "Warning: Cannot ping VM"

# Check MySQL port
echo ""
echo "2. Checking MySQL port (3306)..."
powershell -Command "Test-NetConnection -ComputerName 192.168.85.66 -Port 3306" || echo "MySQL port not reachable"

# Check Redis port
echo ""
echo "3. Checking Redis port (6379)..."
powershell -Command "Test-NetConnection -ComputerName 192.168.85.66 -Port 6379" || echo "Redis port not reachable"

echo ""
echo "=== Instructions ==="
echo ""
echo "If ports are not reachable, check VM firewall:"
echo "  sudo firewall-cmd --add-port=3306/tcp --permanent"
echo "  sudo firewall-cmd --add-port=6379/tcp --permanent"
echo "  sudo firewall-cmd --reload"
echo ""
echo "For MySQL, also check bind-address in /etc/mysql/mysql.conf.d/mysqld.cnf:"
echo "  bind-address = 0.0.0.0"
echo ""
echo "Then run the SQL initialization script:"
echo "  mysql -u root -p < docker/init-db/01-init-database.sql"