@echo off
setlocal
where py >nul 2>nul
if %errorlevel% equ 0 goto usepy
where python >nul 2>nul
if %errorlevel% equ 0 goto usepython
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\bootstrap-python.ps1" %*
exit /b %errorlevel%
:usepy
py -3 "%~dp0bootstrap.py" %*
exit /b %errorlevel%
:usepython
python "%~dp0bootstrap.py" %*
exit /b %errorlevel%
