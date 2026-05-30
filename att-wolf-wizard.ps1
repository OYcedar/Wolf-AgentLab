[CmdletBinding()]
param(
    [string]$GamePath = "",
    [string]$GameTitle = "",
    [string]$Workspace = "",
    [switch]$SkipLlmCheck,
    [switch]$PrepareOnly,
    [switch]$SkipSmallBatch,
    [int]$SmallBatchMaxBatches = 1,
    [int]$MaxBatches = 0,
    [switch]$RunFullTranslation,
    [int]$MaxFullTranslatePasses = 20,
    [switch]$WriteBack,
    [switch]$FinalizePatch,
    [switch]$CleanupWorkspace
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Init-Utf8 {
    [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
    [Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
    $OutputEncoding = [System.Text.UTF8Encoding]::new($false)
}

function ConvertTo-SafeName {
    param([string]$Name)
    return ($Name -replace '[<>:"/\\|?*]', '_')
}

function Get-AgentWorkspace {
    param([string]$Title)
    if ($Workspace) {
        return $Workspace
    }
    return (Join-Path (Join-Path $WorkspaceRoot (ConvertTo-SafeName -Name $Title)) "agent")
}

function Show-Report {
    param($Report)
    if ($null -ne $Report) {
        $Report | ConvertTo-Json -Depth 12 | Write-Host
    }
}

function Invoke-AttWolfJson {
    param(
        [string[]]$Arguments,
        [switch]$AllowWarning,
        [switch]$AllowError
    )

    Push-Location $Source
    try {
        $output = & uv run python main.py --agent-mode @Arguments --json
        $exitCode = $LASTEXITCODE
    }
    finally {
        Pop-Location
    }

    $text = ($output | Out-String).Trim()
    $report = $null
    if ($text) {
        try {
            $report = $text | ConvertFrom-Json
        }
        catch {
            $text | Write-Host
            throw "att-wolf returned non-JSON output for: $($Arguments -join ' ')"
        }
    }

    if ($exitCode -ne 0 -and -not $AllowError) {
        Show-Report -Report $report
        throw "att-wolf command failed: $($Arguments -join ' ')"
    }
    if ($null -ne $report -and $report.status -eq "error" -and -not $AllowError) {
        Show-Report -Report $report
        throw "att-wolf reported error: $($Arguments -join ' ')"
    }
    if ($null -ne $report -and $report.status -eq "warning" -and -not $AllowWarning) {
        Show-Report -Report $report
        throw "att-wolf reported warning: $($Arguments -join ' ')"
    }
    return $report
}

function Get-PendingCount {
    param($StatusReport)
    if ($null -eq $StatusReport -or $null -eq $StatusReport.summary) {
        return $null
    }
    $summary = $StatusReport.summary
    if ($summary.PSObject.Properties.Name -contains "pending_count") {
        return [int]$summary.pending_count
    }
    return $null
}

Init-Utf8

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Source = Join-Path $Root "wolf-source"
$WorkspaceRoot = Join-Path $Root "workspace"

New-Item -ItemType Directory -Force -Path `
    (Join-Path $Root "game"), `
    $WorkspaceRoot, `
    (Join-Path $Root "patches"), `
    (Join-Path $Root "tools") | Out-Null

if (-not (Test-Path -LiteralPath $Source)) {
    throw "Missing source directory: $Source"
}

if (-not $GameTitle) {
    if (-not $GamePath) {
        $GamePath = Read-Host "Wolf game directory"
    }
    $addReport = Invoke-AttWolfJson -Arguments @("add-game", "--path", $GamePath) -AllowWarning
    $GameTitle = [string]$addReport.summary.game_title
}

if (-not $GameTitle) {
    throw "Game title could not be resolved."
}

Write-Host "Target game: $GameTitle"

$doctorArgs = @("doctor", "--game", $GameTitle)
if ($SkipLlmCheck) {
    $doctorArgs += "--no-check-llm"
}
$doctorReport = Invoke-AttWolfJson -Arguments $doctorArgs -AllowWarning
if ($doctorReport.status -eq "warning") {
    Write-Host "doctor completed with warnings; review the JSON above if translation tools are missing."
}

Invoke-AttWolfJson -Arguments @("prepare-game", "--game", $GameTitle) -AllowWarning | Out-Null

$agentWorkspace = Get-AgentWorkspace -Title $GameTitle
Invoke-AttWolfJson -Arguments @(
    "prepare-agent-workspace",
    "--game", $GameTitle,
    "--output-dir", $agentWorkspace
) -AllowWarning | Out-Null

Write-Host "Prepared workspace: $agentWorkspace"

if ($PrepareOnly) {
    Write-Host "PrepareOnly set; stopping before LLM translation."
    exit 0
}

$smallBatchCount = $SmallBatchMaxBatches
if ($MaxBatches -gt 0) {
    $smallBatchCount = $MaxBatches
}

if (-not $SkipSmallBatch) {
    Write-Host "Running small translation batch: $smallBatchCount"
    Invoke-AttWolfJson -Arguments @(
        "translate",
        "--game", $GameTitle,
        "--max-batches", [string]$smallBatchCount
    ) -AllowWarning | Out-Null

    Invoke-AttWolfJson -Arguments @("audit-runtime", "--game", $GameTitle) -AllowWarning -AllowError | Out-Null
    $statusAfterSmallBatch = Invoke-AttWolfJson -Arguments @("translation-status", "--game", $GameTitle) -AllowWarning -AllowError
    Show-Report -Report $statusAfterSmallBatch
}

if ($RunFullTranslation) {
    for ($pass = 1; $pass -le $MaxFullTranslatePasses; $pass++) {
        $statusReport = Invoke-AttWolfJson -Arguments @("translation-status", "--game", $GameTitle) -AllowWarning -AllowError
        $pending = Get-PendingCount -StatusReport $statusReport
        if ($null -ne $pending -and $pending -le 0) {
            Write-Host "No pending translations remain."
            break
        }

        Write-Host "Full translation pass $pass / $MaxFullTranslatePasses"
        Invoke-AttWolfJson -Arguments @("translate", "--game", $GameTitle) -AllowWarning | Out-Null

        if ($pass -eq $MaxFullTranslatePasses) {
            $finalStatus = Invoke-AttWolfJson -Arguments @("translation-status", "--game", $GameTitle) -AllowWarning -AllowError
            Show-Report -Report $finalStatus
            $remaining = Get-PendingCount -StatusReport $finalStatus
            if ($null -eq $remaining -or $remaining -gt 0) {
                throw "Full translation stopped with pending items. Re-run with a higher -MaxFullTranslatePasses or inspect failures."
            }
        }
    }
}

if (-not $WriteBack) {
    Write-Host "WriteBack not set; stopping before restore-runtime, write-back, and patch generation."
    exit 0
}

Invoke-AttWolfJson -Arguments @("restore-runtime", "--game", $GameTitle) -AllowWarning | Out-Null
Invoke-AttWolfJson -Arguments @("quality-report", "--game", $GameTitle) | Out-Null
Invoke-AttWolfJson -Arguments @("audit-runtime", "--game", $GameTitle) | Out-Null
Invoke-AttWolfJson -Arguments @("write-back", "--game", $GameTitle) | Out-Null

$patchReport = Invoke-AttWolfJson -Arguments @("make-patch", "--game", $GameTitle)
$patchDir = [string]$patchReport.summary.patch_dir
Write-Host "Patch ready: $patchDir"

if ($FinalizePatch) {
    $finalizer = Join-Path $Root "finalize-patch-package.bat"
    if (-not (Test-Path -LiteralPath $finalizer)) {
        throw "Missing finalizer: $finalizer"
    }
    & $finalizer $patchDir
    if ($LASTEXITCODE -ne 0) {
        throw "Patch finalization failed."
    }
}

if ($CleanupWorkspace) {
    Write-Host "CleanupWorkspace requested, but automatic cleanup is intentionally not destructive. Remove temporary folders manually after release QA."
}
