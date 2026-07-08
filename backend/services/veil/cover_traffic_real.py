"""REAL Cover Traffic Injection - Actual UDP packet sending."""

import socket
import random
import threading
import time
import os
import hashlib
from typing import Optional, List, Tuple
from dataclasses import dataclass
import numpy as np


@dataclass
class CoverTrafficConfig:
    drop_rate: float = 1.0
    loop_rate: float = 0.5
    packet_size: int = 32768


class RealCoverTraffic:
    """
    REAL cover traffic injection - actual UDP packets.
    """
    
    def __init__(self):
        self._running = False
        self._threads = []
        self.config = CoverTrafficConfig()
        self._sock: Optional[socket.socket] = None
        self._targets: List[Tuple[str, int]] = [("127.0.0.1", 9100)]
    
    def _init_socket(self):
        if self._sock is None:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    def _generate_packet(self) -> bytes:
        """Generate dummy Sphinx packet."""
        payload = os.urandom(self.config.packet_size - 64)
        alpha = os.urandom(32)
        gamma = hashlib.sha3_256(payload).digest()
        return alpha + gamma + payload
    
    def _send_packet(self, target: Tuple[str, int]):
        try:
            self._init_socket()
            packet = self._generate_packet()
            self._sock.sendto(packet, target)
        except Exception:
            pass
    
    def _run_drop_cover(self):
        while self._running and self.config.drop_rate > 0:
            interval = np.random.exponential(1.0 / self.config.drop_rate)
            time.sleep(interval)
            target = random.choice(self._targets)
            self._send_packet(target)
    
    def _run_loop_cover(self):
        while self._running and self.config.loop_rate > 0:
            interval = np.random.exponential(1.0 / self.config.loop_rate)
            time.sleep(interval)
            target = random.choice(self._targets)
            self._send_packet(target)
    
    def start(self):
        self._running = True
        
        drop_thread = threading.Thread(target=self._run_drop_cover, daemon=True)
        drop_thread.start()
        self._threads.append(drop_thread)
        
        loop_thread = threading.Thread(target=self._run_loop_cover, daemon=True)
        loop_thread.start()
        self._threads.append(loop_thread)
        
        print(f"[CoverTraffic] Started - Drop rate: {self.config.drop_rate}/s, Loop rate: {self.config.loop_rate}/s")
    
    def stop(self):
        self._running = False
        for thread in self._threads:
            thread.join(timeout=2)
        if self._sock:
            self._sock.close()
        print("[CoverTraffic] Stopped")
    
    def set_targets(self, targets: List[Tuple[str, int]]):
        self._targets = targets


_cover_traffic = None


def start_cover_traffic():
    global _cover_traffic
    if _cover_traffic is None:
        _cover_traffic = RealCoverTraffic()
    _cover_traffic.start()
    return _cover_traffic


def stop_cover_traffic():
    global _cover_traffic
    if _cover_traffic:
        _cover_traffic.stop()


def get_cover_traffic():
    return _cover_traffic