# Project Setup Guide

## Prerequisites

- JDK 21
- Maven 3.8+
- Conda environment: `D:\yangjw\software\Miniconda\envs\incident-agent`
- Infrastructure VM: `192.168.85.66`

The VM hosts MySQL, Redis, Elasticsearch, Docker-managed infrastructure, and the optional Prometheus/Grafana observability stack.

## Verify Infrastructure

From the project root:

```bash
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-vm-connection.ps1
```

Expected open ports:

| Service | Host | Port |
|---|---|---:|
| MySQL | 192.168.85.66 | 3306 |
| Redis | 192.168.85.66 | 6379 |
| Elasticsearch | 192.168.85.66 | 9200 |
| Prometheus | 192.168.85.66 | 9090 |
| Grafana | 192.168.85.66 | 3000 |

If Prometheus is not reachable, check whether the container is running and whether the VM firewall exposes `9090/tcp`.

## Install Prometheus And Grafana On The VM

Copy or pull this project onto the VM, then run from the project root:

```bash
bash scripts/install-observability-vm.sh
```

Prometheus is configured in `docker/prometheus/prometheus.yml` to scrape the Java services at:

- `192.168.85.1:9081/actuator/prometheus`
- `192.168.85.1:9082/actuator/prometheus`
- `192.168.85.1:9083/actuator/prometheus`

`192.168.85.1` is the Windows host address on the VMware VMnet8 network. If the Java services move into the VM later, update the Prometheus targets accordingly.

To make the Python diagnosis API use Prometheus-backed metrics, set this in `python/.env`:

```env
METRICS_PROVIDER=prometheus
PROMETHEUS_URL=http://192.168.85.66:9090
LOG_PROVIDER=file
LOG_BASE_DIR=../logs
```

Keep `METRICS_PROVIDER=fake` when running deterministic tests and evaluation.
Keep `LOG_PROVIDER=fake` for deterministic tests; use `LOG_PROVIDER=file` for live demos.

The Java services write logs to the project `logs/` directory when started from their module directories:

- `logs/order-service.log`
- `logs/inventory-service.log`
- `logs/payment-mock-service.log`

Restart the Java services after changing `application.yml`; already-running processes will not pick up the file logging configuration.

Verify local Java observability:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-local-observability.ps1
```

Import the demo dashboard from Windows:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/import-grafana-dashboard.ps1
```

Then open:

```text
http://192.168.85.66:3000/d/incident-diagnosis-overview/incident-diagnosis-overview
```

## Build Java Services

```bash
cd java
mvn clean install -DskipTests
```

## Run Java Services

Start each service in a separate terminal:

```bash
cd java/order-service
mvn spring-boot:run
```

```bash
cd java/inventory-service
mvn spring-boot:run
```

```bash
cd java/payment-mock-service
mvn spring-boot:run
```

The Java services are configured to use MySQL and Redis on `192.168.85.66`.

## Run Python Agent

```powershell
cd python
D:\yangjw\software\Miniconda\envs\incident-agent\python.exe -m uvicorn app.main:app --reload --port 8000
```

Use `python/.env.example` as the template for `python/.env`. Do not commit the real `.env` because it contains secrets.

## Verify Local Services

- Order Service: http://localhost:9081/actuator/health
- Inventory Service: http://localhost:9082/actuator/health
- Payment Mock: http://localhost:9083/actuator/health
- Python Agent: http://localhost:8000/health

## Evaluation And Tests

```powershell
cd python
D:\yangjw\software\Miniconda\envs\incident-agent\python.exe -m pytest app/tests/ -q
D:\yangjw\software\Miniconda\envs\incident-agent\python.exe -m ruff check app
D:\yangjw\software\Miniconda\envs\incident-agent\python.exe -m app.evaluation.run_full_eval
```

Expected evaluation result:

- Top-1 accuracy: 100.0%
- Top-3 recall: 100.0%
- Forbidden violation rate: 0.0%

## Trigger Faults

```bash
bash scripts/trigger-fault.sh order-service mysql-slow-query
```

Reset faults:

```bash
bash scripts/reset-faults.sh
```

## Troubleshooting

### Database Connection Issues

Check MySQL on the VM:

```bash
mysql -h 192.168.85.66 -u root -p incident_db
```

Also check `bind-address = 0.0.0.0` and the VM firewall.

### Redis Connection Issues

```bash
redis-cli -h 192.168.85.66 -p 6379 ping
```

### Prometheus Not Reachable

Check the VM container and firewall:

```bash
docker ps | grep prometheus
sudo firewall-cmd --add-port=9090/tcp --permanent
sudo firewall-cmd --add-port=3000/tcp --permanent
sudo firewall-cmd --reload
```

### Port Conflicts

Modify service ports in `java/*/src/main/resources/application.yml` if `9081-9083` are already in use.
