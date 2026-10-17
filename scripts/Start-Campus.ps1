[CmdletBinding()]
param([switch]$CheckOnly)

$ErrorActionPreference = 'Stop'
$campusRoot = Split-Path -Parent $PSScriptRoot
$campusPython = Join-Path $campusRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $campusPython)) {
    throw 'Virtual environment is missing. Follow LOCAL_RELEASE.md first-time setup.'
}
Push-Location -LiteralPath $campusRoot
try {
    if ($CheckOnly) {
        & $campusPython -m app.acceptance --base-url 'http://127.0.0.1:8000'
        if ($LASTEXITCODE -ne 0) { throw 'Local release acceptance failed; inspect the check names above.' }
        return
    }
    if ($env:APP_ENV -eq 'production') {
        throw 'This launcher is for localhost. Use the deployment runbook for production.'
    }
    $campusSocket = [System.Net.Sockets.TcpClient]::new()
    try {
        $campusListening = $campusSocket.ConnectAsync('127.0.0.1', 8000)
        try { $null = $campusListening.Wait(500) } catch { }
        if ($campusSocket.Connected) {
            throw 'Port 8000 is already in use. Check the running app with -CheckOnly or stop it in its terminal first.'
        }
    } finally { $campusSocket.Dispose() }
    if (-not $env:AUTH_SECRET) {
        & $campusPython -m app.cli init-secret
        if ($LASTEXITCODE -ne 0) { throw 'Signing secret initialization failed.' }
    }
    Write-Host 'Campus: http://127.0.0.1:8000/campus/  API: http://127.0.0.1:8000/docs'
    Write-Host 'Press Ctrl+C to stop. Run this script with -CheckOnly in another terminal to verify the release.'
    & $campusPython -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-proxy-headers --no-access-log
    if ($LASTEXITCODE -ne 0) { throw 'Server stopped with an error. Check startup configuration and database migrations.' }
} finally {
    Pop-Location
}
