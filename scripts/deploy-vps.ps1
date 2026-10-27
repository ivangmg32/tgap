# TGAP VPS update for the layout on 144.172.97.105:
#   app:      C:\catalyst\tgap-sandbox   (startup task TGAP-Laboratory, service.ps1)
#   research: C:\catalyst\tgap           (config.json tgap_source)
# Keeps config.json, users.txt, data\ and study-data\ (accounts, sessions, study records).
# Run as Administrator from a checkout of the user-experiment branch:
#   powershell -ExecutionPolicy Bypass -File .\scripts\deploy-vps.ps1
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)   # repository root
$App = 'C:\catalyst\tgap-sandbox'
$Src = 'C:\catalyst\tgap'
if (-not (Test-Path "$App\service.ps1")) { throw "App folder $App not found - is this the TGAP server?" }

Write-Host '1/6 Stopping the lab' -ForegroundColor Cyan
& "$App\service.ps1" -Action Stop
Start-Sleep -Seconds 3

Write-Host '2/6 Backing up accounts, settings and study data' -ForegroundColor Cyan
$backup = "C:\catalyst\backup-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
New-Item -ItemType Directory -Force -Path $backup | Out-Null
foreach ($f in 'config.json', 'users.txt', 'data', 'study-data') {
  if (Test-Path "$App\$f") { Copy-Item "$App\$f" -Destination $backup -Recurse -Force }
}
Write-Host "    backup: $backup"

Write-Host '3/6 Updating the app (keeps config.json, users.txt, data, study-data)' -ForegroundColor Cyan
robocopy ".\workbench" $App /E /XD data study-data tests __pycache__ .venv /XF config.json users.txt users.txt.bak /NFL /NDL /NJH /NJS | Out-Null
if ($LASTEXITCODE -ge 8) { throw "Copying the app failed (robocopy $LASTEXITCODE)" }

Write-Host '4/6 Updating the research source (results the study shows)' -ForegroundColor Cyan
robocopy "." $Src /E /XD workbench .git .venv data __pycache__ .pytest_cache /XF update-server.ps1 /NFL /NDL /NJH /NJS | Out-Null
if ($LASTEXITCODE -ge 8) { throw "Copying the research source failed (robocopy $LASTEXITCODE)" }

Write-Host '5/6 Checking Python packages' -ForegroundColor Cyan
& "$App\.venv\Scripts\python.exe" -m pip install -q -r "$App\requirements.txt"

Write-Host '6/6 Starting the lab' -ForegroundColor Cyan
& "$App\service.ps1" -Action Start
Start-Sleep -Seconds 8
try {
  $r = Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:8080/static/study-links.js'
  if ($r.Content -match '1FAIpQLSe3n5rp') { Write-Host 'Running with the new version and Google Form links.' -ForegroundColor Green }
  else { Write-Host 'Running, but the new links were not found - check the copy step.' -ForegroundColor Yellow }
} catch { Write-Host "The lab did not answer yet: $_  Run: $App\service.ps1 -Action Status" -ForegroundColor Yellow }
Write-Host 'Open http://144.172.97.105:8080/ and press Ctrl+F5.' -ForegroundColor Green
