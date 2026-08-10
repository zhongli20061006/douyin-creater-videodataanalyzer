param([int]$Port = 8001)

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PidFile = Join-Path $ProjectRoot "backend.pid"
$LogFile = Join-Path $ProjectRoot "backend.log"

if (Test-Path $PidFile) {
    $oldPid = Get-Content $PidFile -ErrorAction SilentlyContinue
    if ($oldPid) {
        $proc = Get-Process -Id $oldPid -ErrorAction SilentlyContinue
        if ($proc) {
            Write-Host "Backend is already running (PID: $oldPid)"
            exit 0
        }
    }
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
}

$pythonw = Join-Path $ProjectRoot ".venv\Scripts\pythonw.exe"
if (-not (Test-Path $pythonw)) {
    $pythonw = Get-Command pythonw.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source
    if (-not $pythonw) {
        Write-Error "pythonw.exe not found"
        exit 1
    }
}

Write-Host "Starting backend on port $Port ..."

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $pythonw
$psi.Arguments = "-m uvicorn api:app --host 0.0.0.0 --port $Port"
$psi.WorkingDirectory = $ProjectRoot
$psi.UseShellExecute = $false
$psi.CreateNoWindow = $true

$proc = [System.Diagnostics.Process]::Start($psi)
$proc.Id | Out-File -FilePath $PidFile -Encoding utf8

$started = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
"$started PID=$($proc.Id) Port=$Port" | Out-File -FilePath $LogFile -Encoding utf8

Write-Host "Backend started: http://localhost:$Port (PID: $($proc.Id))"
