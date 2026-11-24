$startupDeadline = 30
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot
$pythonExe = 'python'
if (Test-Path '.venv/Scripts/python.exe') { $pythonExe = Join-Path $projectRoot '.venv/Scripts/python.exe' }
if (-not (Test-Path 'frontend/node_modules')) {
    Push-Location frontend
    npm.cmd ci
    if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed' }
    Pop-Location
}
& $pythonExe -m backend.db
if ($LASTEXITCODE -ne 0) { throw 'Database initialization failed' }
$backendProcess = Start-Process $pythonExe -ArgumentList @('-m', 'uvicorn', 'backend.main:app', '--host', '127.0.0.1', '--port', '8000') -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru
$frontendPushed = $false
try {
    $healthy = $false
    for ($attempt = 0; $attempt -lt $startupDeadline; $attempt++) {
        if ($backendProcess.HasExited) { throw 'Backend stopped during startup. Check port 8000.' }
        try {
            $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/health' -TimeoutSec 1
            if ($health.status -eq 'ok') { $healthy = $true; break }
        } catch {
            Start-Sleep -Seconds 1
        }
    }
    if (-not $healthy) { throw 'Backend health check timed out' }
    Write-Host 'GalStudy API ready. Open http://localhost:3000 after Next.js starts.'
    Push-Location frontend
    $frontendPushed = $true
    npm.cmd run dev
} finally {
    if ($frontendPushed) { Pop-Location }
    Stop-Process -Id $backendProcess.Id -ErrorAction SilentlyContinue
}
