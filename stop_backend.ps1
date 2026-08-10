$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PidFile = Join-Path $ProjectRoot "backend.pid"

if (-not (Test-Path $PidFile)) {
    Write-Host "Backend PID file not found. Not running?"
    exit 0
}

$pid = Get-Content $PidFile -ErrorAction SilentlyContinue
if (-not $pid) {
    Write-Host "PID file is empty"
    Remove-Item $PidFile -Force
    exit 0
}

$proc = Get-Process -Id $pid -ErrorAction SilentlyContinue
if ($proc -and $proc.ProcessName -like "*python*") {
    Stop-Process -Id $pid -Force
    Write-Host "Backend stopped (PID: $pid)"
} else {
    Write-Host "Process $pid not found or not python"
}

Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
