$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw "Execute .\scripts\setup.ps1 primeiro."
}
Push-Location $projectRoot
try {
    & $pythonExe -m ruff check .
    if ($LASTEXITCODE -ne 0) { throw "Ruff encontrou problemas." }
    & $pythonExe -m pytest @args
    if ($LASTEXITCODE -ne 0) { throw "Os testes falharam (codigo $LASTEXITCODE)." }
} finally {
    Pop-Location
}
