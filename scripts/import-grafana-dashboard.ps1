param(
    [string]$GrafanaUrl = "http://192.168.85.66:3000",
    [string]$Username = "admin",
    [string]$Password = "admin",
    [string]$DashboardPath = "docker/grafana/dashboards/incident-overview.json"
)

$ErrorActionPreference = "Stop"

$resolvedDashboard = Resolve-Path $DashboardPath
$dashboard = Get-Content -Path $resolvedDashboard -Raw | ConvertFrom-Json

$body = @{
    dashboard = $dashboard
    overwrite = $true
    folderId = 0
} | ConvertTo-Json -Depth 100

$authText = "${Username}:${Password}"
$authBytes = [System.Text.Encoding]::ASCII.GetBytes($authText)
$authHeader = [Convert]::ToBase64String($authBytes)

$response = Invoke-RestMethod `
    -Method Post `
    -Uri "$GrafanaUrl/api/dashboards/db" `
    -Headers @{ Authorization = "Basic $authHeader" } `
    -ContentType "application/json" `
    -Body $body

Write-Host "Dashboard imported: $GrafanaUrl$($response.url)"
