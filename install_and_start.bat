@echo off
setlocal
set "ROOT=%~dp0"

where py >nul 2>nul
if not errorlevel 1 (
  set "BOOTSTRAP=py -3"
) else (
  where python >nul 2>nul
  if errorlevel 1 (
    echo Python 3.10 or newer was not found.
    echo Install Python from https://www.python.org/downloads/ and enable Add Python to PATH.
    pause
    exit /b 1
  )
  set "BOOTSTRAP=python"
)

if not exist "%ROOT%.venv\Scripts\python.exe" (
  echo Creating Python environment...
  %BOOTSTRAP% -m venv "%ROOT%.venv"
  if errorlevel 1 goto :failed
)

echo Installing or updating AntPlot dependencies...
"%ROOT%.venv\Scripts\python.exe" -m pip install --upgrade pip
"%ROOT%.venv\Scripts\python.exe" -m pip install -r "%ROOT%requirements.txt"
if errorlevel 1 goto :failed

call "%ROOT%start_portable.bat"
exit /b 0

:failed
echo.
echo Installation failed. Check your Python installation and network connection, then try again.
pause
exit /b 1
