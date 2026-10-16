param([ValidateSet('Install','Start','Stop','Status')][string]$Action='Status')
$ErrorActionPreference = 'Stop'
$TgapHome = $PSScriptRoot
$TgapPython = Join-Path $TgapHome '.venv/Scripts/python.exe'
$TgapTask = 'TGAP-Laboratory'
$TgapStopped = Join-Path $TgapHome 'data/service.stopped'
if ($Action -eq 'Install') {
    $TgapArguments = '"' + (Join-Path $TgapHome 'sandbox/serve.py') + '" --home "' + $TgapHome + '"'
    $TgapTaskAction = New-ScheduledTaskAction -Execute $TgapPython -Argument $TgapArguments -WorkingDirectory $TgapHome
    $TgapTrigger = New-ScheduledTaskTrigger -AtStartup
    $TgapSettings = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -StartWhenAvailable
    $TgapPrincipal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
    Register-ScheduledTask -TaskName $TgapTask -Action $TgapTaskAction -Trigger $TgapTrigger -Settings $TgapSettings -Principal $TgapPrincipal -Description 'Private TGAP experimentation laboratory, port 8080.' -Force | Out-Null
    if (-not (Get-NetFirewallRule -DisplayName 'TGAP Laboratory TCP 8080' -ErrorAction SilentlyContinue)) {
        New-NetFirewallRule -DisplayName 'TGAP Laboratory TCP 8080' -Direction Inbound -Protocol TCP -LocalPort 8080 -Action Allow | Out-Null
    }
    $Action = 'Start'
}
if ($Action -eq 'Start') {
    if (Test-Path -LiteralPath $TgapStopped) { Remove-Item -LiteralPath $TgapStopped }
    Enable-ScheduledTask -TaskName $TgapTask | Out-Null
    Start-ScheduledTask -TaskName $TgapTask
    Write-Host 'TGAP startup task enabled and started.'
}
if ($Action -eq 'Stop') {
    'Stopped by operator.' | Set-Content -LiteralPath $TgapStopped
    Disable-ScheduledTask -TaskName $TgapTask | Out-Null
    Stop-ScheduledTask -TaskName $TgapTask
    $TgapRuntime = Join-Path $TgapHome 'data/runtime.json'
    if (Test-Path -LiteralPath $TgapRuntime) {
        $TgapRecord = Get-Content -LiteralPath $TgapRuntime -Raw | ConvertFrom-Json
        foreach ($TgapProcessId in @($TgapRecord.server_pid, $TgapRecord.supervisor_pid)) {
            $TgapProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$TgapProcessId" -ErrorAction SilentlyContinue
            if ($TgapProcess -and $TgapProcess.CommandLine -match 'sandbox.app:app|sandbox[/\\]serve.py') { Stop-Process -Id $TgapProcessId -Force -ErrorAction SilentlyContinue }
        }
    }
    Write-Host 'TGAP stopped and automatic startup disabled.'
}
if ($Action -eq 'Status') {
    Get-ScheduledTask -TaskName $TgapTask | Select-Object TaskName,State
    Invoke-RestMethod -Uri 'http://127.0.0.1:8080/api/health' -TimeoutSec 3
}
