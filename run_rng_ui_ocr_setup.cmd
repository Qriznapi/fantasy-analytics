@echo off
setlocal
set ROOT=%~dp0
set PY=%ROOT%.venv\Scripts\python.exe
if not exist "%PY%" echo Python environment not found: %PY% & pause & exit /b 1
echo Installing the Python OCR bridge into this project environment...
"%PY%" -m pip install -r "%ROOT%requirements-ocr.txt"
echo.
echo Install Tesseract OCR separately, then restart the UI.
echo Recommended Windows command in an Administrator terminal:
echo winget install --id UB-Mannheim.TesseractOCR
pause
