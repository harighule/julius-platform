@echo off
setlocal

cd /d "%~dp0"

echo ============================================================
echo   JULIUS - Fullstack Launcher and Cleanup
echo ============================================================
echo.

if not exist "backend\main.py" (
    echo ERROR: backend\main.py not found.
    pause
    exit /b 1
)

if not exist "frontend\package.json" (
    echo ERROR: frontend\package.json not found.
    pause
    exit /b 1
)

python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH.
    pause
    exit /b 1
)

node --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Node.js is not installed or not in PATH.
    pause
    exit /b 1
)

echo [1/4] Cleaning unnecessary runtime files...
if exist "frontend\dev_output.log" del /q "frontend\dev_output.log"
if exist "backend\__pycache__" rmdir /s /q "backend\__pycache__"
if exist "tmp" rmdir /s /q "tmp"
if exist "launch_app.bat" del /q "launch_app.bat"

echo [2/4] Checking backend runtime...
python -c "import fastapi,uvicorn" >nul 2>&1
if errorlevel 1 (
    echo Backend packages missing. Installing requirements...
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo ERROR: Backend dependency installation failed.
        echo        Fix Python/pip issues, then run start.bat again.
        pause
        exit /b 1
    )
)

echo [3/4] Checking frontend runtime...
cd /d "%~dp0\frontend"
if not exist "node_modules" (
    echo node_modules missing. Installing frontend packages...
    npm install
    if errorlevel 1 (
        echo ERROR: Frontend dependency installation failed.
        cd /d "%~dp0"
        pause
        exit /b 1
    )
)
cd /d "%~dp0"

echo [4/4] Launching backend and frontend...
start "JULIUS Backend" cmd /k "cd /d ""%~dp0"" && python -m backend.main"
timeout /t 2 >nul
start "JULIUS Frontend" cmd /k "cd /d ""%~dp0frontend"" && npm run dev -- --host 0.0.0.0 --port 5173"

echo.
echo ============================================================
echo   JULIUS is starting in two windows
echo ============================================================
echo   Backend:  http://localhost:8000
echo   Frontend: http://localhost:5173
echo   Docs:     http://localhost:8000/docs
echo ============================================================
echo.
pause
