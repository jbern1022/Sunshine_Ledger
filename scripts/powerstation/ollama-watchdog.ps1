# Ollama watchdog, run every 5 minutes by the "Ollama Watchdog" scheduled task.
#
# Restarts the "Ollama Server" task when either:
#   1. the API doesn't answer on http://127.0.0.1:11434, or
#   2. the server's latest start fell back to CPU instead of the GPU.
#
# Case 2 is the failure seen on 2026-09-23: started too early after boot, the
# server's GPU discovery timed out and it ran CPU-only with a 4096 context,
# which silently truncates bill prompts. It stays "up", so a plain health
# check would never catch it.
#
# A GPU-fallback restart is attempted at most once per $GpuRetryMinutes, so a
# genuinely broken driver can't cause a restart loop; that case needs a human
# and shows up in watchdog.log.

$ErrorActionPreference = "Continue"

$TaskName        = "Ollama Server"
$ApiUrl          = "http://127.0.0.1:11434/api/version"
$LogDir          = Join-Path $env:LOCALAPPDATA "Ollama"
$ServeLog        = Join-Path $LogDir "serve-task.log"
$WatchdogLog     = Join-Path $LogDir "watchdog.log"
$StateFile       = Join-Path $LogDir "watchdog-last-gpu-restart.txt"
$GpuRetryMinutes = 30
$StartupGraceSec = 90   # don't judge a server that only just started

function Write-Log($msg) {
    Add-Content -Path $WatchdogLog -Value "$(Get-Date -Format o) $msg"
}

function Restart-OllamaTask($reason) {
    Write-Log "RESTART: $reason"
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    # The task's child ollama.exe can outlive the wrapper; make sure it's gone.
    Get-Process -Name "ollama" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 5
    Start-ScheduledTask -TaskName $TaskName
}

$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if (-not $task) {
    Write-Log "ERROR: scheduled task '$TaskName' not found - run install-ollama-tasks.ps1"
    exit 1
}

# 1. Is the API answering?
$apiOk = $false
try {
    $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 10 -Uri $ApiUrl
    $apiOk = ($r.StatusCode -eq 200)
} catch { $apiOk = $false }

if (-not $apiOk) {
    $proc = Get-Process -Name "ollama" -ErrorAction SilentlyContinue |
        Sort-Object StartTime -Descending | Select-Object -First 1
    if ($proc -and ((Get-Date) - $proc.StartTime).TotalSeconds -lt $StartupGraceSec) {
        exit 0   # still starting up
    }
    Restart-OllamaTask "API not answering at $ApiUrl"
    exit 0
}

# 2. Did the most recent start find the GPU?
if (-not (Test-Path $ServeLog)) { exit 0 }

$lines = Get-Content -Path $ServeLog -Tail 400
$lastStart = ($lines | Select-String -Pattern 'Listening on' | Select-Object -Last 1)
if (-not $lastStart) { exit 0 }

$after   = $lines[($lastStart.LineNumber - 1)..($lines.Count - 1)]
$compute = $after | Select-String -Pattern 'msg="inference compute"' | Select-Object -Last 1
if (-not $compute) { exit 0 }   # discovery not finished yet

if ($compute.Line -match 'library=cpu') {
    $last = $null
    if (Test-Path $StateFile) { $last = [datetime](Get-Content $StateFile -Raw).Trim() }
    if ($last -and ((Get-Date) - $last).TotalMinutes -lt $GpuRetryMinutes) {
        Write-Log "WARN: still CPU-only after a recent restart ($last); leaving it for a human"
        exit 0
    }
    Set-Content -Path $StateFile -Value (Get-Date -Format o)
    Restart-OllamaTask "server fell back to CPU (GPU not detected at startup)"
}
