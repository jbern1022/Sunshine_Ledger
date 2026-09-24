# One-time setup on the Powerstation: run Ollama from Task Scheduler instead
# of the tray app's sign-in auto-start, plus a 5-minute watchdog.
#
# Run in an ADMINISTRATOR PowerShell, from this folder:
#   powershell -ExecutionPolicy Bypass -File .\install-ollama-tasks.ps1
#
# What it does:
#   - copies ollama-serve.ps1 / ollama-watchdog.ps1 to C:\ProgramData\SunshineLedger\ollama
#   - sets machine env OLLAMA_HOST=0.0.0.0:11434 and OLLAMA_CONTEXT_LENGTH=8192
#   - registers "Ollama Server": at startup, after a 2-minute delay (so the
#     NVIDIA driver is ready), runs whether or not anyone is signed in
#   - registers "Ollama Watchdog": every 5 minutes
#   - moves the tray app's Startup shortcut aside (backup, not deleted) so the
#     tray app doesn't also start a server at sign-in
#
# Tasks run as the current user with S4U logon ("run whether user is logged on
# or not", no stored password). That keeps Ollama's models in the same
# %USERPROFILE%\.ollama as today. S4U has no network credentials, which Ollama
# doesn't need.
#
# Undo: uninstall-ollama-tasks.ps1

$ErrorActionPreference = "Stop"

$principalCheck = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principalCheck.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Run this in an administrator PowerShell."
}

$Here       = Split-Path -Parent $MyInvocation.MyCommand.Path
$InstallDir = "C:\ProgramData\SunshineLedger\ollama"
$Ollama     = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"
$User       = "$env:USERDOMAIN\$env:USERNAME"

if (-not (Test-Path $Ollama)) { throw "Ollama not found at $Ollama" }

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
Copy-Item -Force (Join-Path $Here "ollama-serve.ps1")    $InstallDir
Copy-Item -Force (Join-Path $Here "ollama-watchdog.ps1") $InstallDir

[Environment]::SetEnvironmentVariable("OLLAMA_HOST", "0.0.0.0:11434", "Machine")
[Environment]::SetEnvironmentVariable("OLLAMA_CONTEXT_LENGTH", "8192", "Machine")

$ps = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$principal = New-ScheduledTaskPrincipal -UserId $User -LogonType S4U -RunLevel Limited

# --- Ollama Server ---
$serveAction  = New-ScheduledTaskAction -Execute $ps `
    -Argument "-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$InstallDir\ollama-serve.ps1`""
$serveTrigger = New-ScheduledTaskTrigger -AtStartup
$serveTrigger.Delay = "PT2M"
$serveSettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) `
    -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName "Ollama Server" -Action $serveAction -Trigger $serveTrigger `
    -Principal $principal -Settings $serveSettings -Force `
    -Description "Runs ollama serve for Sunshine Ledger (see scripts/powerstation in the repo)." | Out-Null

# --- Ollama Watchdog ---
$dogAction  = New-ScheduledTaskAction -Execute $ps `
    -Argument "-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$InstallDir\ollama-watchdog.ps1`""
$dogTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(5) `
    -RepetitionInterval (New-TimeSpan -Minutes 5)
$dogSettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 3) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName "Ollama Watchdog" -Action $dogAction -Trigger $dogTrigger `
    -Principal $principal -Settings $dogSettings -Force `
    -Description "Restarts 'Ollama Server' if the API is down or it fell back to CPU." | Out-Null

# --- Stop the tray app from also starting a server at sign-in ---
$startupLnk = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup\Ollama.lnk"
$backupDir  = Join-Path $InstallDir "startup-shortcut-backup"
if (Test-Path $startupLnk) {
    New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
    Move-Item -Force $startupLnk $backupDir
    Write-Host "Moved tray-app Startup shortcut to $backupDir"
}

Write-Host ""
Write-Host "Installed. Next:"
Write-Host "  1. Quit the Ollama tray app (right-click tray icon > Quit Ollama)."
Write-Host "  2. Start-ScheduledTask 'Ollama Server'   (or reboot and wait ~2 minutes)"
Write-Host "  3. Check: Invoke-WebRequest -UseBasicParsing http://127.0.0.1:11434/api/version"
Write-Host "     and look for the RTX 5070 in $env:LOCALAPPDATA\Ollama\serve-task.log"
