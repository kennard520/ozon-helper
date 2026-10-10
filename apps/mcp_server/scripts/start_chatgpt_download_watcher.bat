@echo off
cd /d "%~dp0\..\..\.."
set "WATCH_DIR=%USERPROFILE%\Downloads\ozon-chatgpt-images"
if not exist "%WATCH_DIR%" mkdir "%WATCH_DIR%"
python apps\mcp_server\scripts\watch_chatgpt_downloads.py --mcp-url http://110.42.226.37:8586/mcp --watch-dir "%WATCH_DIR%"
