@echo off
setlocal
cd /d "%~dp0"

set "PYTHON_EXE=%LocalAppData%\Programs\Python\Python312\python.exe"
if exist "%PYTHON_EXE%" goto run_installed_python

where py >nul 2>nul
if not errorlevel 1 goto run_py

where python >nul 2>nul
if not errorlevel 1 goto run_python

echo Python was not found.
echo Install Python 3.10 or newer and select "Add Python to PATH".
echo Then run: py -m pip install numpy matplotlib
goto end

:run_installed_python
"%PYTHON_EXE%" "%~dp0plot_s11.py"
goto end

:run_py
py "%~dp0plot_s11.py"
goto end

:run_python
python "%~dp0plot_s11.py"

:end

echo.
pause
