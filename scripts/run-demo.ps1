param(
    [string]$Scenario = "mysql-slow-query",
    [string]$Service = "order-service",
    [string]$AgentUrl = "http://localhost:8000",
    [switch]$ResetAfter
)

$ErrorActionPreference = "Stop"

$servicePorts = @{
    "order-service" = 9081
    "inventory-service" = 9082
    "payment-mock-service" = 9083
}

$serviceProbe = @{
    "order-service" = @{ Method = "GET"; Path = "/api/orders" }
    "inventory-service" = @{ Method = "GET"; Path = "/api/inventory" }
    "payment-mock-service" = @{ Method = "POST"; Path = "/api/payment/process"; Body = @{ orderId = "DEMO-ORDER"; amount = 99.90 } }
}

if (-not $servicePorts.ContainsKey($Service)) {
    throw "Unknown service '$Service'. Valid values: $($servicePorts.Keys -join ', ')"
}

$port = $servicePorts[$Service]
$dashboardUrl = "http://192.168.85.66:3000/d/incident-diagnosis-overview/incident-diagnosis-overview"

function Invoke-JsonPost($Uri, $Body) {
    Invoke-RestMethod `
        -Method Post `
        -Uri $Uri `
        -ContentType "application/json" `
        -Body ($Body | ConvertTo-Json -Depth 20)
}

function Test-Http($Name, $Uri) {
    try {
        Invoke-RestMethod -Uri $Uri -TimeoutSec 5 | Out-Null
        Write-Host "[OK] $Name"
    }
    catch {
        throw "[FAIL] $Name is not reachable: $Uri"
    }
}

Write-Host "=== Incident Diagnosis Demo ==="
Write-Host "Scenario: $Scenario"
Write-Host "Service:  $Service"
Write-Host ""

Write-Host "[1/6] Checking dependencies..."
Test-Http "Java service health" "http://localhost:$port/actuator/health"
Test-Http "Python agent health" "$AgentUrl/health"
$agentConfig = Invoke-RestMethod -Uri "$AgentUrl/health/config" -TimeoutSec 5
Write-Host "[OK] Agent mode: $($agentConfig.agent_mode), metrics=$($agentConfig.metrics_provider), logs=$($agentConfig.log_provider), llm_configured=$($agentConfig.llm_configured)"
Test-Http "Prometheus" "http://192.168.85.66:9090/-/ready"
Test-Http "Grafana" "http://192.168.85.66:3000/api/health"

Write-Host ""
Write-Host "[2/6] Activating fault..."
$incidentStartedAt = (Get-Date).AddSeconds(-30).ToUniversalTime().ToString("o")
$faultBody = @{ delay_ms = 1800 }
Invoke-JsonPost "http://localhost:$port/internal/v1/faults/$Scenario/activate" $faultBody | Out-Null
Write-Host "[OK] Fault activated"

Write-Host ""
Write-Host "[3/6] Generating traffic and evidence..."
$probe = $serviceProbe[$Service]
for ($i = 1; $i -le 5; $i++) {
    try {
        $uri = "http://localhost:$port$($probe.Path)"
        if ($probe.Method -eq "POST") {
            Invoke-JsonPost $uri $probe.Body | Out-Null
        }
        else {
            Invoke-RestMethod -Uri $uri -TimeoutSec 10 | Out-Null
        }
        Write-Host "  request $i completed"
    }
    catch {
        Write-Host "  request $i produced expected fault signal: $($_.Exception.Message)"
    }
}

Write-Host ""
Write-Host "[4/6] Calling diagnosis API..."
$incident = @{
    incident_id = "DEMO-$($Scenario.ToUpper())"
    service = $Service
    endpoint = $probe.Path
    alert_type = "P95_LATENCY_HIGH"
    value = 5000
    threshold = 1000
    started_at = $incidentStartedAt
}
$report = Invoke-JsonPost "$AgentUrl/api/v1/diagnose" $incident

Write-Host ""
Write-Host "[5/6] Diagnosis summary"
Write-Host "Status: $($report.status)"
Write-Host "Top causes:"
foreach ($cause in $report.top_causes) {
    Write-Host "  #$($cause.rank) $($cause.cause_code) [$($cause.confidence)]"
    Write-Host "     $($cause.reasoning_summary)"
    Write-Host "     evidence: $($cause.supporting_evidence -join ', ')"
}

Write-Host ""
Write-Host "Evidence details:"
foreach ($evidence in $report.evidence_details) {
    Write-Host "  [$($evidence.evidence_id)] $($evidence.source): $($evidence.summary)"
}

Write-Host ""
Write-Host "Recommended actions:"
foreach ($action in $report.recommended_actions) {
    Write-Host "  - $action"
}

Write-Host ""
Write-Host "[6/6] Open Grafana dashboard:"
Write-Host "  $dashboardUrl"

if ($ResetAfter) {
    Write-Host ""
    Write-Host "Resetting faults..."
    Invoke-RestMethod -Method Post -Uri "http://localhost:$port/internal/v1/faults/reset" | Out-Null
    Write-Host "[OK] Faults reset"
}
else {
    Write-Host ""
    Write-Host "Reset when finished:"
    Write-Host "  Invoke-RestMethod -Method Post -Uri http://localhost:$port/internal/v1/faults/reset"
}
