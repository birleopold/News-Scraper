# Start Uganda Business Watch automatically (no window) when you sign in to Windows.
# Creates a per-user Task Scheduler task; no administrator rights needed.
# Undo with: .\uninstall-autostart.ps1
param([switch]$StartNow)
$ErrorActionPreference = 'Stop'

$root = $PSScriptRoot
$pythonw = Join-Path $root '.venv\Scripts\pythonw.exe'
$script = Join-Path $root 'run.py'
if (-not (Test-Path -LiteralPath $pythonw)) {
    throw "Missing $pythonw. Run start.ps1 once first to create the Python environment."
}

$user = "$env:USERDOMAIN\$env:USERNAME"
$action = New-ScheduledTaskAction -Execute $pythonw -Argument ('"{0}" --log-file' -f $script) -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
# No time limit (the default would stop the app after 3 days), one copy only,
# keep running on battery, and retry a few times if it exits unexpectedly.
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)

Register-ScheduledTask -TaskName 'Uganda Business Watch' -Description 'Local dashboard and scheduled fetching for Uganda Business Watch (http://127.0.0.1:5050).' `
    -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
Write-Output "Installed: Uganda Business Watch will start when $user signs in."

if ($StartNow) {
    Start-ScheduledTask -TaskName 'Uganda Business Watch'
    Write-Output 'Started now. Open http://127.0.0.1:5050'
}
