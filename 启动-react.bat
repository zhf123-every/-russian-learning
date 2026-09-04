@echo off
cd /d "%~dp0"

where npm >nul 2>nul
if %errorlevel%==0 (
    goto :run
)
echo [ERROR] Node.js / npm not found.
echo         Install Node.js from https://nodejs.org/
pause
exit /b 1

:run
echo Starting React app at http://localhost:5173 ...
npm run dev -- --open
pause
