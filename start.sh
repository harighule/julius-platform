#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "============================================================"
echo "  JULIUS — Unified Security Operations Platform"
echo "============================================================"
echo ""

# Verify we're in the right directory
if [ ! -f "backend/main.py" ]; then
    echo "ERROR: Cannot find backend/main.py from $(pwd)"
    exit 1
fi

# Platform detection
OS=$(uname -s)
PYTHON_CMD="python3"
if ! command -v python3 &>/dev/null; then
    PYTHON_CMD="python"
fi

# Check Python version >= 3.10
PY_VERSION=$($PYTHON_CMD -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "0.0")
PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
    echo "ERROR: Python >= 3.10 required (found $PY_VERSION)"
    exit 1
fi
echo "  Python $PY_VERSION detected"

# Check Node version >= 18
NODE_VERSION=$(node --version 2>/dev/null | sed 's/v//' || echo "0.0.0")
NODE_MAJOR=$(echo "$NODE_VERSION" | cut -d. -f1)
if [ "$NODE_MAJOR" -lt 18 ]; then
    echo "ERROR: Node.js >= 18 required (found $NODE_VERSION)"
    exit 1
fi
echo "  Node.js v$NODE_VERSION detected"
echo ""

# Install Python deps
echo "[1/3] Checking Python dependencies..."
$PYTHON_CMD -m pip install -q -r requirements.txt 2>/dev/null

# Install frontend deps
echo "[2/3] Checking frontend dependencies..."
cd frontend
[ ! -d node_modules ] && npm install
cd "$SCRIPT_DIR"

echo "[3/3] Starting JULIUS..."
echo ""

# Start backend in background
echo "Starting backend on http://localhost:8000 ..."
$PYTHON_CMD -m backend.main &
BACKEND_PID=$!
sleep 3

# Start frontend
echo "Starting frontend on http://localhost:5173 ..."
cd frontend
npm run dev &
FRONTEND_PID=$!
cd "$SCRIPT_DIR"

echo ""
echo "============================================================"
echo "  JULIUS is running!"
echo "============================================================"
echo ""
echo "  Backend API:    http://localhost:8000"
echo "  Frontend UI:    http://localhost:5173"
echo "  API Docs:       http://localhost:8000/docs"
echo ""
echo "  Default login:  admin / Admin@1234"
echo ""
echo "  Press Ctrl+C to stop..."

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM
wait
