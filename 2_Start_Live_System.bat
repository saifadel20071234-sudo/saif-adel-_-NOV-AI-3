@echo off
echo ===================================================
echo PowerStep Grid - Live System Startup
echo ===================================================
echo.

cd /d "%~dp0"
call venv\Scripts\activate

set PYTHONIOENCODING=utf-8
set TF_CPP_MIN_LOG_LEVEL=3
set TF_ENABLE_ONEDNN_OPTS=0

echo Starting Simulated Sensors (Background)...
start "Sensors Simulator" cmd /c "call venv\Scripts\activate && python simulate_sensors.py"

echo Starting Realtime AI Inference (Background)...
start "AI Inference Engine" cmd /c "call venv\Scripts\activate && python realtime_inference.py"

echo Starting Streamlit Dashboard...
python -m streamlit run dashboard.py

pause
