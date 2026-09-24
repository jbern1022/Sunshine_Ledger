# Undo install-ollama-tasks.ps1: remove both scheduled tasks, stop the server
# they started, and put the tray app's Startup shortcut back.
#
# Run in an ADMINISTRATOR PowerShell:
#   powershell -ExecutionPolicy Bypass -File .\uninstall-ollama-tasks.ps1
#
# Leaves the machine env vars (OLLAMA_HOST, OLLAMA_CONTEXT_LENGTH) in place;
# the tray app needs them too.

$ErrorActionPreference = "Continue"

foreach ($name in "Ollama Watchdog", "Ollama Server") {
    Stop-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
}
Get-Process -Name "ollama" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue

$backup = "C:\ProgramData\SunshineLedger\ollama\startup-shortcut-backup\Ollama.lnk"
$startupDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup"
if (Test-Path $backup) {
    Move-Item -Force $backup $startupDir
    Write-Host "Restored tray-app Startup shortcut."
}

Write-Host "Removed. Open Ollama from the Start menu to go back to the tray app."
