@echo off
title PowerStep Grid - AI & Web App
echo ===================================================
echo PowerStep Grid - Full AI & Web Integration
echo ===================================================
echo.

cd /d "%~dp0"

echo Activating virtual environment...
call venv\Scripts\activate

:: Suppress TensorFlow logging for a cleaner terminal
set TF_CPP_MIN_LOG_LEVEL=3
set PYTHONIOENCODING=utf-8

echo.
echo Starting the AI-powered Backend Server...
echo The browser will open automatically in 3 seconds...
echo.

:: Open browser automatically after a short delay
start "" cmd /c "timeout /t 3 /nobreak >nul & start http://127.0.0.1:8000"

:: Start Backend Server
cd backend
python -m uvicorn app:app --host 127.0.0.1 --port 8000
