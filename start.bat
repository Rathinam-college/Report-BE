@echo off
echo ========================================================
echo Starting Rathinam Food Operations Backend (FastAPI)...
echo ========================================================
cd /d "%~dp0"
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
pause

