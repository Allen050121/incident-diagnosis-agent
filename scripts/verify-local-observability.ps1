param(
    [string]$LogDir = "logs"
)

$ErrorActionPreference = "Continue"

Write-Host "=== Verifying Local Java Observability ==="

$services = @(
    @{ Name = "order-service"; Port = 9081; Log = "order-service.log" },
    @{ Name = "inventory-service"; Port = 9082; Log = "inventory-service.log" },
    @{ Name = "payment-mock-service"; Port = 9083; Log = "payment-mock-service.log" }
)

$allOk = $true
foreach ($service in $services) {
    Write-Host ""
    Write-Host "Checking $($service.Name)..."
    try {
        $health = Invoke-RestMethod -Uri "http://localhost:$($service.Port)/actuator/health" -TimeoutSec 3
        Write-Host "Health: $($health.status)"
    }
    catch {
        Write-Host "Warning: health endpoint not reachable on port $($service.Port)"
        $allOk = $false
    }

    try {
        $promContent = & curl.exe -s "http://localhost:$($service.Port)/actuator/prometheus"
        if ($LASTEXITCODE -eq 0 -and $promContent -match "jvm_threads_live_threads") {
            Write-Host "Prometheus endpoint reachable"
        }
        else {
            Write-Host "Warning: Prometheus endpoint returned unexpected content"
            $allOk = $false
        }
    }
    catch {
        Write-Host "Warning: Prometheus endpoint not reachable on port $($service.Port)"
        $allOk = $false
    }

    $logPath = Join-Path $LogDir $service.Log
    if (Test-Path $logPath) {
        Write-Host "Log file: $logPath"
    }
    else {
        Write-Host "Warning: log file not found: $logPath"
        $allOk = $false
    }
}

Write-Host ""
if ($allOk) {
    Write-Host "Local Java observability is ready."
    exit 0
}

Write-Host "Some local observability checks failed. Start the Java services and generate at least one request per service."
exit 1
