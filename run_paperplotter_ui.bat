@echo off
setlocal
set "PY=%LocalAppData%\Programs\Python\Python312\python.exe"
set "DATA=%~1"
if "%DATA%"=="" if exist "D:\CSV" set "DATA=D:\CSV"
if "%DATA%"=="" set "DATA=%~dp0"
if exist "%PY%" (
  "%PY%" "%~dp0main.py" ui "%DATA%"
  goto :end
)
python "%~dp0main.py" ui "%DATA%"
:end
pause
