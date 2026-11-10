@echo off
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
 echo Python 3.10 or later is required. Install Python, then retry.
 pause
 exit /b 1
)
py -3 -m venv .venv
if errorlevel 1 goto fail
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto fail
.venv\Scripts\python.exe -m playwright install chromium
if errorlevel 1 goto fail
echo Installation completed. Open 2_start.bat.
pause
exit /b 0
:fail
echo Installation failed. Check your internet connection and Python installation.
pause
exit /b 1
