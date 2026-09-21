@echo off
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=C:\Users\admin\.codex\.chatgpt-projects\g-p-6aaf84be34dc8191ba8b77e668647931\.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
  echo Please install Python and dependencies in .venv first.
  pause
  exit /b 1
)
start "" http://127.0.0.1:8501
"%PYTHON_EXE%" -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501 --browser.gatherUsageStats false
pause
