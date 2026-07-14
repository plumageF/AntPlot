@echo off
setlocal
set "ROOT=%~dp0"
set "PYTHON=%ROOT%.venv\Scripts\python.exe"

if not exist "%PYTHON%" (
  echo Python virtual environment was not found.
  echo Run the setup steps in README.md first.
  pause
  exit /b 1
)

where pnpm >nul 2>nul
if errorlevel 1 (
  echo pnpm was not found. Run: corepack enable
  pause
  exit /b 1
)

if not exist "%ROOT%frontend\dist\index.html" (
  echo Frontend build was not found. Run: cd frontend ^&^& pnpm build
  pause
  exit /b 1
)

echo Starting AntPlot backend and frontend...
start "AntPlot backend 8765" /min /D "%ROOT%" "%PYTHON%" -m src.hfss_paperplotter.preview_server
start "AntPlot frontend 4173" /min /D "%ROOT%frontend" pnpm preview --host 127.0.0.1 --port 4173

echo.
echo Frontend: http://127.0.0.1:4173/
echo Backend : http://127.0.0.1:8765/
echo.
pause
