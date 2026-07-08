"""REAL Tor connection for anonymous dark web access."""

import socket
import httpx
from typing import Optional

class RealTorConnection:
    def __init__(self, socks_port: int = 9150):
        self.socks_port = socks_port
        self._client: Optional[httpx.Client] = None
        self._connected = False
    
    def connect(self) -> bool:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            result = sock.connect_ex(('127.0.0.1', self.socks_port))
            sock.close()
            if result != 0:
                return False
            self._client = httpx.Client(
                proxy=f"socks5://127.0.0.1:{self.socks_port}",
                timeout=30.0
            )
            self._connected = True
            return True
        except Exception:
            return False
    
    def get(self, url: str) -> Optional[str]:
        if not self._connected or not self._client:
            return None
        try:
            response = self._client.get(url)
            return response.text
        except Exception:
            return None
    
    def get_onion(self, onion_address: str, path: str = "") -> Optional[str]:
        full_url = f"http://{onion_address}.onion/{path.lstrip('/')}"
        return self.get(full_url)
    
    def close(self):
        if self._client:
            self._client.close()
        self._connected = False