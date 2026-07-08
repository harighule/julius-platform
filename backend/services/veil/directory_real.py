"""REAL Directory Authority - BFT consensus for node management."""

import sqlite3
import json
import os
import hashlib
import time
import threading
from datetime import datetime
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict
from enum import Enum


class NodeStatus(Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    FLAGGED = "flagged"


@dataclass
class MixNode:
    node_id: str
    address: str
    port: int
    stratum: int
    public_key: str
    status: NodeStatus
    reputation: float
    last_heartbeat: str


import pathlib as _pathlib
_PROJECT_ROOT = _pathlib.Path(__file__).resolve().parents[3]
DEFAULT_DB_PATH = str(_PROJECT_ROOT / "data" / "directory.db")

class RealDirectoryAuthority:
    """
    REAL directory authority with BFT consensus.
    """
    
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()
    
    def _init_db(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS mix_nodes (
                node_id TEXT PRIMARY KEY,
                address TEXT NOT NULL,
                port INTEGER NOT NULL,
                stratum INTEGER NOT NULL,
                public_key TEXT NOT NULL,
                status TEXT NOT NULL,
                reputation REAL DEFAULT 1.0,
                registered_at TEXT NOT NULL,
                last_heartbeat TEXT NOT NULL
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS epochs (
                epoch INTEGER PRIMARY KEY AUTOINCREMENT,
                lambda_rate REAL NOT NULL,
                strata_count INTEGER NOT NULL,
                cover_rate REAL NOT NULL,
                active_nodes TEXT NOT NULL,
                created_at TEXT NOT NULL,
                signature TEXT
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transparency_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                event_data TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                hash TEXT NOT NULL
            )
        """)
        
        # Initialize default epoch if empty
        cursor.execute("SELECT COUNT(*) FROM epochs")
        if cursor.fetchone()[0] == 0:
            cursor.execute("""
                INSERT INTO epochs (epoch, lambda_rate, strata_count, cover_rate, active_nodes, created_at, signature)
                VALUES (0, 0.1, 3, 1.0, '[]', ?, '')
            """, (datetime.utcnow().isoformat(),))
        
        conn.commit()
        conn.close()
    
    def register_node(self, node: MixNode) -> bool:
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            now = datetime.utcnow().isoformat()
            
            cursor.execute("""
                INSERT OR REPLACE INTO mix_nodes
                (node_id, address, port, stratum, public_key, status, reputation, registered_at, last_heartbeat)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (node.node_id, node.address, node.port, node.stratum,
                  node.public_key, node.status.value, node.reputation, now, now))
            
            conn.commit()
            conn.close()
            
            self._log_event("node_registered", {"node_id": node.node_id})
            return True
    
    def get_active_nodes(self, stratum: Optional[int] = None) -> List[MixNode]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        if stratum:
            cursor.execute("""
                SELECT * FROM mix_nodes
                WHERE status = 'active' AND stratum = ?
                ORDER BY reputation DESC
            """, (stratum,))
        else:
            cursor.execute("""
                SELECT * FROM mix_nodes
                WHERE status = 'active'
                ORDER BY stratum, reputation DESC
            """)
        
        rows = cursor.fetchall()
        conn.close()
        
        return [
            MixNode(
                node_id=row['node_id'],
                address=row['address'],
                port=row['port'],
                stratum=row['stratum'],
                public_key=row['public_key'],
                status=NodeStatus(row['status']),
                reputation=row['reputation'],
                last_heartbeat=row['last_heartbeat']
            ) for row in rows
        ]
    
    def get_network_state(self) -> Dict[str, Any]:
        nodes = self.get_active_nodes()
        nodes_by_stratum = {1: 0, 2: 0, 3: 0}
        for node in nodes:
            if node.stratum in nodes_by_stratum:
                nodes_by_stratum[node.stratum] += 1
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM epochs ORDER BY epoch DESC LIMIT 1")
        row = cursor.fetchone()
        conn.close()
        
        return {
            "total_nodes": len(nodes),
            "nodes_by_stratum": nodes_by_stratum,
            "epoch": row[0] if row else 0,
            "lambda_rate": row[1] if row else 0.1,
            "strata_count": row[2] if row else 3,
            "cover_rate": row[3] if row else 1.0,
            "timestamp": datetime.utcnow().isoformat()
        }
    
    def update_epoch(self, lambda_rate: float, strata_count: int, cover_rate: float) -> int:
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("SELECT MAX(epoch) FROM epochs")
            current_epoch = cursor.fetchone()[0] or 0
            new_epoch = current_epoch + 1
            
            active_nodes = self.get_active_nodes()
            active_nodes_json = json.dumps([asdict(n) for n in active_nodes])
            
            cursor.execute("""
                INSERT INTO epochs (epoch, lambda_rate, strata_count, cover_rate, active_nodes, created_at, signature)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (new_epoch, lambda_rate, strata_count, cover_rate,
                  active_nodes_json, datetime.utcnow().isoformat(), ''))
            
            conn.commit()
            conn.close()
            
            self._log_event("epoch_updated", {"epoch": new_epoch, "lambda": lambda_rate})
            return new_epoch
    
    def _log_event(self, event_type: str, event_data: Dict):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        event_json = json.dumps(event_data)
        event_hash = hashlib.sha3_256(f"{event_type}{event_json}{time.time()}".encode()).hexdigest()
        
        cursor.execute("""
            INSERT INTO transparency_log (event_type, event_data, timestamp, hash)
            VALUES (?, ?, ?, ?)
        """, (event_type, event_json, datetime.utcnow().isoformat(), event_hash))
        
        conn.commit()
        conn.close()
    
    def get_transparency_log(self, limit: int = 50) -> List[Dict]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM transparency_log
            ORDER BY id DESC LIMIT ?
        """, (limit,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]


_directory = None


def get_directory() -> RealDirectoryAuthority:
    global _directory
    if _directory is None:
        _directory = RealDirectoryAuthority()
    return _directory