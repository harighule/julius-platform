#!/bin/bash
# ─── Complete JULIUS Deployment Script ──────────────────────────────────
# Starts: backend, auto-rotation, frontend (optional)

set -e

echo "🔒 JULIUS Deployment Starting..."

# ── 1. Check for VPN/Tor (optional) ────────────────────────────────────
if [ "$1" == "--tor" ]; then
    echo "🛡️ Connecting VPN..."
    protonvpn-cli connect --fastest || echo "VPN connection failed."

    echo "🧅 Starting Tor..."
    sudo systemctl start tor || echo "Tor already running"
fi

# ── 2. Activate Virtual Environment ─────────────────────────────────────
cd /home/kali/JULIUS
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi
source venv/bin/activate

# ── 3. Install/Update Dependencies ──────────────────────────────────────
echo "📦 Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt
pip install paramiko  # For SSH node control
# If you want full AI features, uncomment the next line:
# pip install torch --index-url https://download.pytorch.org/whl/cpu

# ── 4. Start Auto-Rotation (API key) ─────────────────────────────────────
echo "🔄 Starting API key auto-rotation..."
nohup python3 auto_rotate.py > logs/rotation.log 2>&1 &
echo $! > logs/rotation.pid

# ── 5. Start Backend ─────────────────────────────────────────────────────
echo "🚀 Starting JULIUS backend..."
if [ "$1" == "--tor" ]; then
    echo "   (via Tor)"
    torsocks nohup python3 -m backend.main > logs/backend.log 2>&1 &
else
    nohup python3 -m backend.main > logs/backend.log 2>&1 &
fi
echo $! > logs/backend.pid
echo "   Backend PID: $(cat logs/backend.pid)  |  Logs: logs/backend.log"

# ── 6. Start Frontend (optional) ────────────────────────────────────────
if [ "$2" != "--no-frontend" ]; then
    echo "🖥️ Starting frontend..."
    cd frontend
    if [ ! -d "node_modules" ]; then
        npm install
    fi
    nohup npm run dev > ../logs/frontend.log 2>&1 &
    echo $! > ../logs/frontend.pid
    cd ..
    echo "   Frontend PID: $(cat logs/frontend.pid)  |  Logs: logs/frontend.log"
fi

# ── 7. Show Status ──────────────────────────────────────────────────────
echo ""
echo "✅ JULIUS Deployment Complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📡 Backend:  http://localhost:8000"
echo "🌐 Frontend: http://localhost:5173 (if started)"
echo ""
echo "API Key (from .env):"
grep API_KEY .env | head -1
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "To stop all services, run: pkill -f 'backend.main|auto_rotate|vite'"
echo "To view logs: tail -f logs/backend.log"
