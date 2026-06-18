@echo off
cd /d "%~dp0"
echo ============================================
echo   Ozon Helper - starting local backend...
echo   Keep this BLACK WINDOW OPEN (do not close).
echo   It will auto-pick a free port and print it below.
echo ============================================
echo.
python run_api.py
echo.
echo ===== Backend stopped or FAILED. Read the message above. =====
echo If you see "python is not recognized", Python is not installed/on PATH.
pause
