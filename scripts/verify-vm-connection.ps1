param(
    [string]$VmHost = "192.168.85.66",
    [int]$TimeoutMs = 3000
)

$ErrorActionPreference = "Continue"

Write-Host "=== Verifying Virtual Machine Connectivity ==="
Write-Host "VM host: $VmHost"

$ports = @(
    @{ Name = "MySQL"; Port = 3306 },
    @{ Name = "Redis"; Port = 6379 },
    @{ Name = "Elasticsearch"; Port = 9200 },
    @{ Name = "Prometheus"; Port = 9090 },
    @{ Name = "Grafana"; Port = 3000 }
)

$allReachable = $true
foreach ($item in $ports) {
    Write-Host ""
    Write-Host "Checking $($item.Name) port ($($item.Port))..."
    $client = [System.Net.Sockets.TcpClient]::new()
    $async = $client.BeginConnect($VmHost, [int]$item.Port, $null, $null)
    $connected = $async.AsyncWaitHandle.WaitOne($TimeoutMs, $false)
    if ($connected -and $client.Connected) {
        $client.EndConnect($async)
        Write-Host "$($item.Name) reachable"
    }
    else {
        Write-Host "Warning: $($item.Name) port not reachable"
        $allReachable = $false
    }
    $client.Close()
}

Write-Host ""
if ($allReachable) {
    Write-Host "All configured VM ports are reachable."
    exit 0
}

Write-Host "Some ports are not reachable. Check VM containers and firewall:"
Write-Host "  sudo firewall-cmd --add-port=3306/tcp --permanent"
Write-Host "  sudo firewall-cmd --add-port=6379/tcp --permanent"
Write-Host "  sudo firewall-cmd --add-port=9200/tcp --permanent"
Write-Host "  sudo firewall-cmd --add-port=9090/tcp --permanent"
Write-Host "  sudo firewall-cmd --add-port=3000/tcp --permanent"
Write-Host "  sudo firewall-cmd --reload"
exit 1
