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

:: Open browser automatically ONLY when the server is fully ready
start /B python wait_and_open.py

:: Start Backend Server
cd backend
python -m uvicorn app:app --host 0.0.0.0 --port 8000
