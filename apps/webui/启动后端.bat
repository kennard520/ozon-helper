@echo off
cd /d %~dp0..\..
python -m uv run ozon-webui %*
