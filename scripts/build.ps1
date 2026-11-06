$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw "Execute .\scripts\setup.ps1 primeiro."
}
if ([System.Environment]::OSVersion.Platform -ne [System.PlatformID]::Win32NT) {
    throw "O executavel Windows precisa ser construido no Windows."
}
Push-Location $projectRoot
try {
    & $pythonExe -m pip install -e ".[dev,api,build]"
    if ($LASTEXITCODE -ne 0) { throw "Falha ao instalar ferramentas de build." }
    & $pythonExe -m ruff check .
    if ($LASTEXITCODE -ne 0) { throw "Ruff encontrou problemas." }
    & $pythonExe -m pytest
    if ($LASTEXITCODE -ne 0) { throw "Os testes falharam; build interrompido." }
    & $pythonExe -m PyInstaller --noconfirm multipost.spec
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller falhou." }
    $outputExe = Join-Path $projectRoot "dist\MultiPost\MultiPost.exe"
    if (-not (Test-Path -LiteralPath $outputExe)) { throw "Executavel nao encontrado apos o build." }
    & $outputExe --diagnostics
    if ($LASTEXITCODE -ne 0) { throw "Diagnostico do executavel falhou." }
    Write-Host "Build pronto em dist\MultiPost. Distribua a pasta inteira. FFmpeg e ffprobe devem estar no PATH do destino."
} finally {
    Pop-Location
}
