$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    & py -3.12 -c "import sys; assert sys.version_info[:2] == (3,12), 'Python 3.12 e necessario'"
    if ($LASTEXITCODE -ne 0) { throw "Instale Python 3.12 com o launcher py." }
    $pythonExe = Join-Path $projectRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $pythonExe)) {
        if (Test-Path -LiteralPath (Join-Path $projectRoot ".venv")) {
            throw "A pasta .venv existe, mas nao contem um Python Windows valido. Preserve-a e renomeie antes de continuar."
        }
        & py -3.12 -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw "Falha ao criar ambiente virtual." }
    }
    & $pythonExe -c "import sys; assert sys.version_info[:2] == (3,12), 'A .venv deve usar Python 3.12'"
    if ($LASTEXITCODE -ne 0) { throw "A .venv usa outra versao. Preserve-a e renomeie antes de continuar." }
    foreach ($tool in @("ffmpeg", "ffprobe")) {
        if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
            throw "$tool nao encontrado. Instale FFmpeg, adicione bin ao PATH e reabra o PowerShell."
        }
    }
    & $pythonExe -m pip install -e ".[dev,api]"
    if ($LASTEXITCODE -ne 0) { throw "Falha ao instalar dependencias." }
    & $pythonExe -m multipost --diagnostics
    if ($LASTEXITCODE -ne 0) { throw "Diagnostico encontrou um problema. Veja a mensagem acima." }
    Write-Host "Instalacao concluida. Execute .\scripts\run.ps1 para abrir."
} finally {
    Pop-Location
}
