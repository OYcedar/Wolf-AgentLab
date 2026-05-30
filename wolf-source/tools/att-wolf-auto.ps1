param()

$ErrorActionPreference = "Stop"
$SourceRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$WolfRoot = Split-Path -Parent $SourceRoot
$Wizard = Join-Path $WolfRoot "att-wolf-wizard.ps1"

if (-not (Test-Path -LiteralPath $Wizard)) {
    throw "Missing wizard script: $Wizard"
}

& powershell -NoProfile -ExecutionPolicy Bypass -File $Wizard @args
exit $LASTEXITCODE
