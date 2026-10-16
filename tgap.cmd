@echo off
setlocal
where py >nul 2>nul
if errorlevel 1 goto checkpython
py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)" >nul 2>nul
if not errorlevel 1 goto usepy
:checkpython
where python >nul 2>nul
if errorlevel 1 goto checkpython3
python -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)" >nul 2>nul
if not errorlevel 1 goto usepython
:checkpython3
where python3 >nul 2>nul
if errorlevel 1 goto installpython
python3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)" >nul 2>nul
if not errorlevel 1 goto usepython3
:installpython
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\bootstrap-python.ps1" %*
exit /b %errorlevel%
:usepy
py -3 "%~dp0bootstrap.py" %*
exit /b %errorlevel%
:usepython
python "%~dp0bootstrap.py" %*
exit /b %errorlevel%
:usepython3
python3 "%~dp0bootstrap.py" %*
exit /b %errorlevel%
