# Runs `ollama serve` for the "Ollama Server" scheduled task, appending its
# output to a log the watchdog reads.
#
# Why a wrapper instead of pointing the task at ollama.exe directly: when the
# tray app starts the server it writes %LOCALAPPDATA%\Ollama\server.log, but a
# bare `ollama serve` only prints to stdout. The watchdog needs the startup
# lines ("inference compute ... name=cpu" vs the RTX 5070) to detect the
# CPU-fallback failure seen on 2026-09-23, so the output has to land in a file.
#
# Settings come from machine-level environment variables, not from here:
#   OLLAMA_HOST=0.0.0.0:11434        (listen on the LAN for docker-host)
#   OLLAMA_CONTEXT_LENGTH=8192       (bill prompts need more than the 4096 default)

$ErrorActionPreference = "Stop"

$Ollama = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"
$LogDir = Join-Path $env:LOCALAPPDATA "Ollama"
$Log    = Join-Path $LogDir "serve-task.log"
$MaxLogBytes = 20MB

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

# Keep one previous log; the watchdog only reads the current one.
if ((Test-Path $Log) -and ((Get-Item $Log).Length -gt $MaxLogBytes)) {
    Move-Item -Force $Log "$Log.1"
}

Add-Content -Path $Log -Value "=== ollama-serve.ps1 starting $(Get-Date -Format o) ==="

# 2>&1 so Ollama's log lines (it logs to stderr) are captured too. In Windows
# PowerShell 5.1, redirected native stderr arrives as error records, and with
# ErrorActionPreference=Stop the first one would kill this wrapper; Continue
# lets every line through to the log.
$ErrorActionPreference = "Continue"
& $Ollama serve 2>&1 | ForEach-Object { "$_" } | Add-Content -Path $Log
