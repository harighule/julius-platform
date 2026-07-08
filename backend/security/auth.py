"""
security/auth.py - Authentication for Julius BGP MITM
Supports both Bearer JWT and X-API-Key
"""

import os
import hmac
import json
import time
from pathlib import Path
from fastapi import HTTPException, Request
from functools import wraps
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent.parent
KEY_HISTORY = BASE_DIR / "data" / "api_key_history.json"

class SecurityManager:
    def __init__(self):
        self.current_key = os.getenv("API_KEY", "change-me")
        self.admin_ips = os.getenv("ADMIN_IPS", "127.0.0.1").split(",")
        self.admin_ips = [ip.strip() for ip in self.admin_ips if ip.strip()]
        self.failed_attempts = {}
        self.blocked_ips = set()
        self.valid_keys = self._load_valid_keys()
    
    def _load_valid_keys(self):
        valid = [self.current_key]
        if KEY_HISTORY.exists():
            try:
                with open(KEY_HISTORY, "r") as f:
                    history = json.load(f)
                    for entry in history[-10:]:
                        if entry.get("key"):
                            valid.append(entry["key"])
            except:
                pass
        return list(set(valid))
    
    def verify_api_key(self, api_key: str) -> bool:
        if not api_key:
            return False
        for key in self.valid_keys:
            if key and hmac.compare_digest(api_key, key):
                return True
        return False
    
    def check_ip_whitelist(self, client_ip: str) -> bool:
        if not self.admin_ips:
            return False
        if "*" in self.admin_ips:
            return True
        return client_ip in self.admin_ips
    
    def check_rate_limit(self, client_ip: str) -> bool:
        max_requests = int(os.getenv("RATE_LIMIT_PER_MINUTE", 10))
        if client_ip in self.blocked_ips:
            return False
        if client_ip not in self.failed_attempts:
            self.failed_attempts[client_ip] = []
        current_time = time.time()
        self.failed_attempts[client_ip] = [
            t for t in self.failed_attempts[client_ip] 
            if t > current_time - 60
        ]
        if len(self.failed_attempts[client_ip]) >= max_requests:
            self.blocked_ips.add(client_ip)
            with open("/var/log/fail2ban/julius.log", "a") as f:
                f.write(f"{current_time} {client_ip} BLOCKED\n")
            return False
        return True
    
    def record_attempt(self, client_ip: str):
        if client_ip not in self.failed_attempts:
            self.failed_attempts[client_ip] = []
        self.failed_attempts[client_ip].append(time.time())
    
    def get_current_key(self):
        return self.current_key

security = SecurityManager()

# Import database for JWT verification
from ..database import db

def secure_endpoint(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        request = None
        for arg in args:
            if isinstance(arg, Request):
                request = arg
                break
        if not request:
            request = kwargs.get('request')
        if not request:
            raise HTTPException(status_code=500, detail="Request not found")
        client_ip = request.client.host if request.client else "unknown"
        
        # Check rate limit
        if not security.check_rate_limit(client_ip):
            raise HTTPException(status_code=429, detail="Rate limit exceeded - IP blocked")
        
        # Check IP whitelist
        if not security.check_ip_whitelist(client_ip):
            security.record_attempt(client_ip)
            raise HTTPException(status_code=403, detail="IP not authorized")
        
        # ── Try Bearer JWT first ──
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            result = db.verify_jwt_token(token)
            if result.get("success"):
                # User authenticated, proceed
                return await func(*args, **kwargs)
            else:
                raise HTTPException(status_code=401, detail="Invalid JWT token")
        
        # ── Fallback to API key ──
        api_key = request.headers.get("X-API-Key")
        if not api_key:
            security.record_attempt(client_ip)
            raise HTTPException(status_code=401, detail="Authentication required (Bearer token or API key)")
        if not security.verify_api_key(api_key):
            security.record_attempt(client_ip)
            raise HTTPException(status_code=403, detail="Invalid API key")
        
        return await func(*args, **kwargs)
    return wrapper
