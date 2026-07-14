@echo off
setlocal
cd /d "%~dp0"

set "PYTHON_EXE=%LocalAppData%\Programs\Python\Python312\python.exe"
if exist "%PYTHON_EXE%" goto run_installed_python

where python >nul 2>nul
if not errorlevel 1 goto run_python

echo Python was not found.
echo Install Python 3.10 or newer and select "Add Python to PATH".
goto end

:run_installed_python
"%PYTHON_EXE%" "%~dp0plot_direction_patterns.py"
goto end

:run_python
python "%~dp0plot_direction_patterns.py"

:end
echo.
pause
