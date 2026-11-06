$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw "Execute .\scripts\setup.ps1 primeiro."
}
Push-Location $projectRoot
try {
    & $pythonExe -m multipost @args
    if ($LASTEXITCODE -ne 0) { throw "O MultiPost terminou com codigo $LASTEXITCODE." }
} finally {
    Pop-Location
}
