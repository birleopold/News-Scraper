# Stop Uganda Business Watch from starting automatically at sign-in.
# Your data in data\ is not touched. A copy that is already running keeps running
# until you sign out or end it (Task Manager > pythonw.exe).
$ErrorActionPreference = 'Stop'
$task = Get-ScheduledTask -TaskName 'Uganda Business Watch' -ErrorAction SilentlyContinue
if ($null -eq $task) {
    Write-Output 'Automatic start was not installed.'
} else {
    Unregister-ScheduledTask -TaskName 'Uganda Business Watch' -Confirm:$false
    Write-Output 'Removed: Uganda Business Watch will no longer start at sign-in.'
}
