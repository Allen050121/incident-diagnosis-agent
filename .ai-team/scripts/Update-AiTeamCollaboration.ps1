param(
    [ValidateSet("status", "start", "handoff", "complete")]
    [string]$Action = "status",

    [ValidateSet("codex", "claude", "other")]
    [string]$Client = "codex",

    [string]$TaskId = "",

    [ValidateSet("dispatcher", "executor", "reviewer", "integration", "memory", "unknown")]
    [string]$Role = "unknown",

    [string]$SessionId = "",

    [string]$Summary = "",

    [string]$NextAction = "",

    [string[]]$Files = @(),

    [switch]$Json
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$stateDir = Join-Path $ProjectRoot ".ai-team\state"
$collaborationPath = Join-Path $stateDir "collaboration.json"

New-Item -ItemType Directory -Force -Path $stateDir | Out-Null

function New-CollaborationState {
    return [pscustomobject]@{
        version = 1
        active = @()
        handoffs = @()
        updatedAt = $null
        notes = @(
            "Shared lightweight coordination state for Codex and Claude working on the same project.",
            "Use .ai-team/scripts/Update-AiTeamCollaboration.ps1 to start, hand off, complete, or inspect sessions.",
            "Keep summaries compact. Do not store full chat logs."
        )
    }
}

function Read-CollaborationState {
    if (-not (Test-Path -LiteralPath $collaborationPath)) {
        return New-CollaborationState
    }

    try {
        $state = Get-Content -LiteralPath $collaborationPath -Encoding UTF8 -Raw | ConvertFrom-Json
    }
    catch {
        throw "Collaboration state exists but could not be parsed: $collaborationPath"
    }

    if (-not $state.PSObject.Properties["active"]) {
        $state | Add-Member -NotePropertyName "active" -NotePropertyValue @()
    }
    if (-not $state.PSObject.Properties["handoffs"]) {
        $state | Add-Member -NotePropertyName "handoffs" -NotePropertyValue @()
    }
    return $state
}

function Save-CollaborationState {
    param([object]$State)

    $State.updatedAt = (Get-Date).ToString("o")
    $State | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $collaborationPath -Encoding UTF8
}

function Write-StateSummary {
    param([object]$State)

    if ($Json) {
        $State | ConvertTo-Json -Depth 10
        return
    }

    Write-Host "AI Team collaboration"
    Write-Host "State: $collaborationPath"
    if ($State.updatedAt) { Write-Host "Updated: $($State.updatedAt)" }
    Write-Host ""
    Write-Host "Active sessions:"
    $active = @($State.active)
    if ($active.Count -eq 0) {
        Write-Host "- none"
    }
    else {
        foreach ($session in $active) {
            Write-Host ("- {0} task={1}; client={2}; role={3}; started={4}" -f $session.session_id, $session.task_id, $session.client, $session.role, $session.started_at)
            if ($session.files -and @($session.files).Count -gt 0) {
                Write-Host ("  files: {0}" -f (@($session.files) -join ", "))
            }
            if ($session.summary) { Write-Host ("  summary: {0}" -f $session.summary) }
        }
    }

    Write-Host ""
    Write-Host "Recent handoffs:"
    $handoffs = @($State.handoffs)
    if ($handoffs.Count -eq 0) {
        Write-Host "- none"
    }
    else {
        $handoffs |
            Sort-Object @{ Expression = { $_.created_at }; Descending = $true } |
            Select-Object -First 5 |
            ForEach-Object {
                Write-Host ("- {0} task={1}; from={2}; created={3}" -f $_.handoff_id, $_.task_id, $_.client, $_.created_at)
                if ($_.summary) { Write-Host ("  summary: {0}" -f $_.summary) }
                if ($_.next_action) { Write-Host ("  next: {0}" -f $_.next_action) }
            }
    }
}

$state = Read-CollaborationState
$now = (Get-Date).ToString("o")

if ($Action -in @("start", "handoff", "complete") -and -not $TaskId) {
    throw "-TaskId is required for action: $Action"
}

if (-not $SessionId -and $TaskId) {
    $safeTaskId = $TaskId -replace "[^a-zA-Z0-9._-]", "-"
    $SessionId = "{0}-{1}-{2}" -f $safeTaskId, $Client, (Get-Date -Format "yyyyMMddHHmmss")
}

$active = @($state.active)
$handoffs = @($state.handoffs)

switch ($Action) {
    "start" {
        $sameTask = @($active | Where-Object { $_.task_id -eq $TaskId -and $_.session_id -ne $SessionId })
        if ($sameTask.Count -gt 0) {
            Write-Host "Warning: another active session already references task '$TaskId'."
            foreach ($session in $sameTask) {
                Write-Host ("- {0} client={1}; role={2}; started={3}" -f $session.session_id, $session.client, $session.role, $session.started_at)
            }
        }

        $active = @($active | Where-Object { $_.session_id -ne $SessionId })
        $active += [pscustomobject][ordered]@{
            session_id = $SessionId
            task_id = $TaskId
            client = $Client
            role = $Role
            started_at = $now
            updated_at = $now
            files = @($Files)
            summary = $Summary
        }
        $state.active = $active
        Save-CollaborationState $state
    }
    "handoff" {
        $handoffId = "{0}-{1}-{2}" -f ($TaskId -replace "[^a-zA-Z0-9._-]", "-"), $Client, (Get-Date -Format "yyyyMMddHHmmss")
        $handoffs += [pscustomobject][ordered]@{
            handoff_id = $handoffId
            session_id = $SessionId
            task_id = $TaskId
            client = $Client
            role = $Role
            created_at = $now
            files = @($Files)
            summary = $Summary
            next_action = $NextAction
        }
        $active = @($active | Where-Object { $_.session_id -ne $SessionId })
        $state.active = $active
        $state.handoffs = $handoffs
        Save-CollaborationState $state
    }
    "complete" {
        $active = @($active | Where-Object { $_.session_id -ne $SessionId -and $_.task_id -ne $TaskId })
        $state.active = $active
        Save-CollaborationState $state
    }
}

Write-StateSummary $state

