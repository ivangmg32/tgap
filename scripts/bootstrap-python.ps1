$ErrorActionPreference = 'Stop'
$TgapRoot = Split-Path -Parent $PSScriptRoot
Write-Host 'Python is missing. TGAP needs Python 3.10 or later to create its environment.'
$TgapAnswer = Read-Host 'Install the official Python 3.11 Windows runtime for your user? [y/N]'
if ($TgapAnswer -notin @('y', 'Y', 'yes', 'YES')) { exit 1 }
$TgapInstaller = Join-Path $env:TEMP 'tgap-python-3.11.9.exe'
Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe' -OutFile $TgapInstaller
$TgapSignature = Get-AuthenticodeSignature -LiteralPath $TgapInstaller
if ($TgapSignature.Status -ne 'Valid' -or $TgapSignature.SignerCertificate.Subject -notmatch 'Python Software Foundation') {
    throw 'Python installer signature verification failed.'
}
Start-Process -FilePath $TgapInstaller -ArgumentList '/quiet InstallAllUsers=0 PrependPath=1 Include_test=0' -WindowStyle Hidden -Wait
$TgapPython = Join-Path $env:LOCALAPPDATA 'Programs/Python/Python311/python.exe'
if (-not (Test-Path -LiteralPath $TgapPython)) { throw 'Python installation did not complete.' }
& $TgapPython (Join-Path $TgapRoot 'bootstrap.py') @args
exit $LASTEXITCODE
