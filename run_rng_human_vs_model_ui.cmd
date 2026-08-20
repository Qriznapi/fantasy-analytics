@echo off
setlocal
set ROOT=%~dp0
set PY=%ROOT%.venv\Scripts\python.exe
if not exist "%PY%" echo Python environment not found: %PY% & pause & exit /b 1
"%PY%" -m streamlit run "%ROOT%app\rng_human_vs_model.py" --server.headless false
pause
