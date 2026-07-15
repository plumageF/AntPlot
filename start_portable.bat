@echo off
setlocal
set "ROOT=%~dp0"
set "PYTHON=%ROOT%.venv\Scripts\python.exe"

if not exist "%PYTHON%" (
  echo AntPlot environment is not installed yet.
  echo Run install_and_start.bat first.
  pause
  exit /b 1
)

if not exist "%ROOT%frontend\dist\index.html" (
  echo Prebuilt frontend files are missing.
  pause
  exit /b 1
)

echo Starting AntPlot...
start "AntPlot backend 8765" /min /D "%ROOT%" "%PYTHON%" -m src.hfss_paperplotter.preview_server
start "AntPlot frontend 4173" /min /D "%ROOT%" "%PYTHON%" -m http.server 4173 --bind 127.0.0.1 --directory "%ROOT%frontend\dist"

echo.
echo Frontend: http://127.0.0.1:4173/
echo Backend : http://127.0.0.1:8765/
echo.
echo Keep this window open while using AntPlot.
pause
