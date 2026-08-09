@echo off
REM ── Plutus Accountant Automation Suite launcher ──────────────────────────
REM Starts the backend engine and the web interface, then opens the browser.
cd /d "%~dp0"

if not exist venv\Scripts\python.exe (
    echo [ERROR] Python environment not found.
    echo Please complete Part 3 of SETUP_GUIDE.md first:  python -m venv venv
    pause
    exit /b 1
)

if not exist .env (
    echo [ERROR] .env file not found.
    echo Please complete Part 3 of SETUP_GUIDE.md: copy .env.example .env
    echo and put your Anthropic API key inside it.
    pause
    exit /b 1
)

if not exist frontend\node_modules (
    echo [ERROR] Frontend not installed yet.
    echo Please complete Part 4 of SETUP_GUIDE.md:  cd frontend ^&^& npm install
    pause
    exit /b 1
)

echo Starting Plutus backend (port 8000)...
start "Plutus - Engine" cmd /k "venv\Scripts\activate && uvicorn api.server:app --port 8000"

echo Starting Plutus web interface (port 5173)...
start "Plutus - Web UI" cmd /k "cd frontend && npm run dev"

echo Waiting for servers to come up...
timeout /t 6 /nobreak >nul

echo Opening browser...
start http://localhost:5173

echo.
echo Plutus is running. Keep the two new windows open while you work.
echo Close them (or press Ctrl+C inside them) to stop the system.
