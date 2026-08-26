@echo off
echo ===================================================
echo PowerStep Grid - Training Pipeline
echo ===================================================
echo.

cd /d "%~dp0"
call venv\Scripts\activate

echo [1/2] Generating Training Data...
python generate_training_data.py

echo.
echo [2/2] Running Full AI Training Pipeline...
set PYTHONIOENCODING=utf-8
set TF_CPP_MIN_LOG_LEVEL=3
set TF_ENABLE_ONEDNN_OPTS=0
python run_pipeline.py

echo.
echo ===================================================
echo Training Completed Successfully!
echo ===================================================
pause
