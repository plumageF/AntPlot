@echo off
cd /d "%~dp0"

set PYTHON_EXE=
if exist ".venv\Scripts\python.exe" set PYTHON_EXE=.venv\Scripts\python.exe
if "%PYTHON_EXE%"=="" where python >nul 2>nul && set PYTHON_EXE=python
if "%PYTHON_EXE%"=="" where py >nul 2>nul && set PYTHON_EXE=py

if "%PYTHON_EXE%"=="" (
  echo Python was not found. Please install Python or create .venv first.
  pause
  exit /b 1
)

echo Starting backend-matched preview server on http://127.0.0.1:8765
"%PYTHON_EXE%" -m src.hfss_paperplotter.preview_server
pause
