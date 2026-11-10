@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
 echo Run 1_install.bat first.
 pause
 exit /b 1
)
echo Demo address: http://127.0.0.1:8765/demo.html
echo Keep this window open. Ctrl+C stops the demo server.
.venv\Scripts\python.exe -m http.server 8765 --bind 127.0.0.1
pause
