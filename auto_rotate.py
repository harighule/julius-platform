#!/usr/bin/env python3
import secrets, time, json
from pathlib import Path
from datetime import datetime

ENV_FILE = Path("/home/kali/JULIUS/.env")
KEY_HISTORY = Path("/home/kali/JULIUS/data/api_key_history.json")

def rotate():
    new_key = secrets.token_urlsafe(48)
    if not ENV_FILE.exists():
        return
    with open(ENV_FILE, "r") as f:
        lines = f.readlines()
    for i, line in enumerate(lines):
        if line.startswith("API_KEY="):
            lines[i] = f'API_KEY="{new_key}"\n'
            break
    with open(ENV_FILE, "w") as f:
        f.writelines(lines)
    KEY_HISTORY.parent.mkdir(parents=True, exist_ok=True)
    history = []
    if KEY_HISTORY.exists():
        with open(KEY_HISTORY, "r") as f:
            history = json.load(f)
    history.append({"key": new_key, "rotated_at": datetime.now().isoformat()})
    if len(history) > 100:
        history = history[-100:]
    with open(KEY_HISTORY, "w") as f:
        json.dump(history, f, indent=2)
    print(f"[{datetime.now()}] 🔑 API Key rotated: {new_key[:20]}...")

if __name__ == "__main__":
    while True:
        rotate()
        time.sleep(1800)  # 30 minutes
