@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv
    if errorlevel 1 goto error
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 goto error
)
echo Open http://127.0.0.1:5050 in your browser.
".venv\Scripts\python.exe" run.py
pause
exit /b
:error
echo Setup failed. Install Python 3.11 or newer and try again.
pause
