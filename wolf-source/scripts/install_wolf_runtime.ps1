param(
    [string]$Version = "3.703",
    [ValidateSet("mini", "full")]
    [string]$Edition = "mini",
    [string]$ToolsDir = "",
    [switch]$Force
)

$ErrorActionPreference = "Stop"

$sourceRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$wolfHome = Split-Path -Parent $sourceRoot
if ([string]::IsNullOrWhiteSpace($ToolsDir)) {
    $ToolsDir = if ($env:ATT_WOLF_TOOLS) { $env:ATT_WOLF_TOOLS } else { Join-Path $wolfHome "tools" }
}

$toolsPath = [System.IO.Path]::GetFullPath($ToolsDir)
$runtimeDir = Join-Path $toolsPath "wolf-runtime"
$archiveName = "WolfRPGEditor_$Version`_$Edition.zip"
$downloadUrl = "https://github.com/smokingwolf/tool_wolf_rpg_editor/releases/download/v$Version/$archiveName"
$downloadPath = Join-Path $toolsPath $archiveName
$tempDir = Join-Path $toolsPath "_wolf_runtime_extract"

New-Item -ItemType Directory -Force -Path $toolsPath | Out-Null

if ((Test-Path $runtimeDir) -and -not $Force) {
    throw "Runtime directory already exists: $runtimeDir. Re-run with -Force to replace it."
}

Write-Host "Downloading WOLF RPG Editor $Version $Edition..."
Invoke-WebRequest -Uri $downloadUrl -OutFile $downloadPath -Headers @{ "User-Agent" = "att-wolf-runtime-installer" }

if (Test-Path $tempDir) {
    Remove-Item -LiteralPath $tempDir -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $tempDir | Out-Null
Expand-Archive -LiteralPath $downloadPath -DestinationPath $tempDir -Force

$runtimeCandidates = @([pscustomobject]@{ FullName = $tempDir }) + @(Get-ChildItem -Path $tempDir -Recurse -Directory)
$runtimeSource = $runtimeCandidates |
    Where-Object {
        (Test-Path (Join-Path $_.FullName "Editor.exe")) -and
        (Test-Path (Join-Path $_.FullName "Game.exe"))
    } |
    Select-Object -First 1

if ($null -eq $runtimeSource) {
    throw "Downloaded archive did not contain an Editor.exe/Game.exe runtime directory."
}

if (Test-Path $runtimeDir) {
    Remove-Item -LiteralPath $runtimeDir -Recurse -Force
}
Copy-Item -LiteralPath $runtimeSource.FullName -Destination $runtimeDir -Recurse

$metadata = @(
    "version=$Version"
    "edition=$Edition"
    "source=$downloadUrl"
    "installed_at=$(Get-Date -Format o)"
)
$metadata | Set-Content -LiteralPath (Join-Path $runtimeDir "ATT_WOLF_RUNTIME_VERSION.txt") -Encoding UTF8

Remove-Item -LiteralPath $tempDir -Recurse -Force

Write-Host "Installed high-version WOLF runtime to $runtimeDir"
