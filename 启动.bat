@echo off
cd /d "%~dp0"

where python >nul 2>nul
if %errorlevel%==0 (
    set PY=python
    goto :run
)
where py >nul 2>nul
if %errorlevel%==0 (
    set PY=py
    goto :run
)

echo [ERROR] Python not found.
echo         Please install Python from https://www.python.org/downloads/
echo         (During install, check "Add Python to PATH")
pause
exit /b 1

:run
echo Starting legacy app at http://localhost:8000 ...
%PY% server.py
pause
