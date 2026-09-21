@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "D:\chatgpt\investment-ai\start-background.ps1"
timeout /t 3 /nobreak >nul
start "" http://127.0.0.1:8501/

