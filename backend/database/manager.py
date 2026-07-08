"""JULIUS VEIL Database Manager - Pure SQLite, no external dependencies."""

import sqlite3
import os
from typing import Optional, Dict, Any, List
from datetime import datetime
import uuid

import pathlib as _pathlib

# Resolve DB path relative to this file so it works on any machine:
#   backend/database/manager.py  ->  parents[2] == project root
_PROJECT_ROOT = _pathlib.Path(__file__).resolve().parents[2]
DB_PATH = str(_PROJECT_ROOT / "data" / "julius.db")

class JuliusDatabase:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_tables()
    
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def _init_tables(self):
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS escrows (
                id TEXT PRIMARY KEY,
                buyer_id TEXT NOT NULL,
                seller_id TEXT NOT NULL,
                amount_usd REAL NOT NULL,
                fee_percentage REAL NOT NULL,
                fee_usd REAL NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                released_at TEXT,
                delivery_proof_hash TEXT
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS controlled_nodes (
                node_id TEXT PRIMARY KEY,
                node_type TEXT NOT NULL,
                host TEXT NOT NULL,
                port INTEGER NOT NULL,
                control_method TEXT NOT NULL,
                status TEXT NOT NULL,
                controlled_at TEXT NOT NULL,
                last_heartbeat TEXT,
                config TEXT
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS revenue_transactions (
                id TEXT PRIMARY KEY,
                transaction_type TEXT NOT NULL,
                amount_usd REAL NOT NULL,
                complexity REAL DEFAULT 1.0,
                scaling_multiplier REAL DEFAULT 1.0,
                destination TEXT,
                created_at TEXT NOT NULL
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS investigations (
                id TEXT PRIMARY KEY,
                query TEXT NOT NULL,
                refined_query TEXT,
                status TEXT NOT NULL,
                results_found INTEGER DEFAULT 0,
                pages_scraped INTEGER DEFAULT 0,
                analysis TEXT,
                complexity REAL DEFAULT 1.0,
                revenue_collected REAL DEFAULT 0.0,
                created_at TEXT NOT NULL,
                completed_at TEXT
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS revenue_summary (
                key TEXT PRIMARY KEY,
                value REAL NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        
        cursor.execute("INSERT OR IGNORE INTO revenue_summary (key, value, updated_at) VALUES ('total_revenue', 0, ?)", 
                      (datetime.utcnow().isoformat(),))
        
        conn.commit()
        conn.close()
    
    def create_escrow(self, buyer_id: str, seller_id: str, amount_usd: float, fee_percentage: float) -> str:
        escrow_id = uuid.uuid4().hex[:16]
        fee_usd = amount_usd * (fee_percentage / 100)
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO escrows (id, buyer_id, seller_id, amount_usd, fee_percentage, fee_usd, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (escrow_id, buyer_id, seller_id, amount_usd, fee_percentage, fee_usd, 'pending', datetime.utcnow().isoformat()))
        conn.commit()
        conn.close()
        return escrow_id
    
    def get_escrow(self, escrow_id: str) -> Optional[Dict[str, Any]]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM escrows WHERE id = ?", (escrow_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None
    
    def release_escrow(self, escrow_id: str, proof_hash: str) -> bool:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT fee_usd FROM escrows WHERE id = ? AND status = 'pending'", (escrow_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return False
        fee_usd = row['fee_usd']
        cursor.execute("""
            UPDATE escrows SET status = 'released', released_at = ?, delivery_proof_hash = ? WHERE id = ?
        """, (datetime.utcnow().isoformat(), proof_hash, escrow_id))
        self._add_revenue('escrow_release', fee_usd, 1.0, 1.0, f'escrow_{escrow_id}')
        conn.commit()
        conn.close()
        return True
    
    def get_escrow_stats(self) -> Dict[str, Any]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM escrows WHERE status = 'pending'")
        active = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM escrows WHERE status = 'released'")
        completed = cursor.fetchone()[0]
        cursor.execute("SELECT COALESCE(SUM(amount_usd), 0) FROM escrows")
        total_volume = cursor.fetchone()[0]
        cursor.execute("SELECT COALESCE(SUM(fee_usd), 0) FROM escrows WHERE status = 'released'")
        total_fees = cursor.fetchone()[0]
        conn.close()
        return {
            'active_escrows': active,
            'completed_escrows': completed,
            'total_volume_usd': float(total_volume),
            'total_fees_collected_usd': float(total_fees)
        }
    
    def add_controlled_node(self, node_id: str, node_type: str, host: str, port: int, method: str) -> bool:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO controlled_nodes 
            (node_id, node_type, host, port, control_method, status, controlled_at, config)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (node_id, node_type, host, port, method, 'controlled', datetime.utcnow().isoformat(), '{}'))
        conn.commit()
        conn.close()
        return True
    
    def get_controlled_nodes(self) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM controlled_nodes WHERE status = 'controlled'")
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]
    
    def get_controlled_nodes_count(self) -> int:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM controlled_nodes WHERE status = 'controlled'")
        count = cursor.fetchone()[0]
        conn.close()
        return count
    
    def _add_revenue(self, tx_type: str, amount_usd: float, complexity: float, multiplier: float, destination: str):
        conn = self._get_connection()
        cursor = conn.cursor()
        tx_id = uuid.uuid4().hex[:16]
        cursor.execute("""
            INSERT INTO revenue_transactions (id, transaction_type, amount_usd, complexity, scaling_multiplier, destination, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (tx_id, tx_type, amount_usd, complexity, multiplier, destination, datetime.utcnow().isoformat()))
        cursor.execute("SELECT value FROM revenue_summary WHERE key = 'total_revenue'")
        current_total = cursor.fetchone()[0]
        new_total = current_total + amount_usd
        cursor.execute("UPDATE revenue_summary SET value = ?, updated_at = ? WHERE key = 'total_revenue'", 
                      (new_total, datetime.utcnow().isoformat()))
        conn.commit()
        conn.close()
    
    def add_revenue(self, tx_type: str, amount_usd: float, complexity: float = 1.0, destination: str = "") -> float:
        multiplier = 1.5 ** complexity
        adjusted_amount = amount_usd * multiplier
        self._add_revenue(tx_type, adjusted_amount, complexity, multiplier, destination)
        return adjusted_amount
    
    def get_total_revenue(self) -> float:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM revenue_summary WHERE key = 'total_revenue'")
        total = cursor.fetchone()[0]
        conn.close()
        return float(total)
    
    def get_recent_transactions(self, limit: int = 50) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM revenue_transactions ORDER BY created_at DESC LIMIT ?", (limit,))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]
    
    def create_investigation(self, query: str, complexity: float = 1.0) -> str:
        inv_id = uuid.uuid4().hex[:12]
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO investigations (id, query, status, complexity, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (inv_id, query, 'starting', complexity, datetime.utcnow().isoformat()))
        conn.commit()
        conn.close()
        return inv_id
    
    def update_investigation(self, inv_id: str, updates: Dict[str, Any]):
        conn = self._get_connection()
        cursor = conn.cursor()
        set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
        values = list(updates.values()) + [inv_id]
        cursor.execute(f"UPDATE investigations SET {set_clause} WHERE id = ?", values)
        conn.commit()
        conn.close()
    
    def get_investigation(self, inv_id: str) -> Optional[Dict[str, Any]]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM investigations WHERE id = ?", (inv_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None


_db = None

def get_db() -> JuliusDatabase:
    global _db
    if _db is None:
        _db = JuliusDatabase()
    return _db