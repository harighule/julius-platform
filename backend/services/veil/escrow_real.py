"""REAL Escrow Service with Ed25519 cryptographic signatures."""

import hashlib
import uuid
import sqlite3
import os
from datetime import datetime
from typing import Optional, Dict, Any, Tuple
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives import serialization
from cryptography.exceptions import InvalidSignature

import pathlib as _pathlib

# Resolve DB path relative to this file so it works on any machine:
#   backend/services/veil/escrow_real.py  ->  parents[3] == project root
_PROJECT_ROOT = _pathlib.Path(__file__).resolve().parents[3]
DB_PATH = str(_PROJECT_ROOT / "data" / "julius.db")

class RealEscrowService:
    STANDARD_FEE = 0.025
    EXPRESS_FEE = 0.045
    
    def __init__(self):
        self._init_db()
    
    def _init_db(self):
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS real_escrows (
                id TEXT PRIMARY KEY,
                buyer_id TEXT NOT NULL,
                seller_id TEXT NOT NULL,
                seller_public_key TEXT NOT NULL,
                amount_usd REAL NOT NULL,
                fee_percentage REAL NOT NULL,
                fee_usd REAL NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                released_at TEXT,
                delivery_hash TEXT,
                signature TEXT
            )
        """)
        conn.commit()
        conn.close()
    
    def generate_seller_keys(self) -> Tuple[str, str]:
        private_key = Ed25519PrivateKey.generate()
        public_key = private_key.public_key()
        private_hex = private_key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption()
        ).hex()
        public_hex = public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        ).hex()
        return private_hex, public_hex
    
    def create_escrow(self, buyer_id: str, seller_id: str, seller_public_key_hex: str, amount_usd: float, express: bool = False) -> str:
        escrow_id = uuid.uuid4().hex[:16]
        fee_pct = self.EXPRESS_FEE if express else self.STANDARD_FEE
        fee_usd = amount_usd * fee_pct
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO real_escrows 
            (id, buyer_id, seller_id, seller_public_key, amount_usd, fee_percentage, fee_usd, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (escrow_id, buyer_id, seller_id, seller_public_key_hex, amount_usd, fee_pct * 100, fee_usd, 'pending', datetime.utcnow().isoformat()))
        conn.commit()
        conn.close()
        return escrow_id
    
    def verify_signature(self, delivery_hash: str, signature_hex: str, seller_public_key_hex: str) -> bool:
        try:
            signature = bytes.fromhex(signature_hex)
            public_key_bytes = bytes.fromhex(seller_public_key_hex)
            delivery_hash_bytes = delivery_hash.encode()
            public_key = Ed25519PublicKey.from_public_bytes(public_key_bytes)
            public_key.verify(signature, delivery_hash_bytes)
            return True
        except InvalidSignature:
            return False
        except Exception:
            return False
    
    def release_escrow(self, escrow_id: str, delivery_hash: str, signature_hex: str) -> Tuple[bool, float]:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM real_escrows WHERE id = ? AND status = 'pending'", (escrow_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return False, 0.0
        columns = [description[0] for description in cursor.description]
        escrow = dict(zip(columns, row))
        if not self.verify_signature(delivery_hash, signature_hex, escrow['seller_public_key']):
            conn.close()
            return False, 0.0
        cursor.execute("""
            UPDATE real_escrows SET status = 'released', released_at = ?, delivery_hash = ?, signature = ? WHERE id = ?
        """, (datetime.utcnow().isoformat(), delivery_hash, signature_hex, escrow_id))
        conn.commit()
        conn.close()
        return True, escrow['fee_usd']
    
    def get_escrow(self, escrow_id: str) -> Optional[Dict[str, Any]]:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM real_escrows WHERE id = ?", (escrow_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None
    
    def get_stats(self) -> Dict[str, Any]:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM real_escrows WHERE status = 'pending'")
        active = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM real_escrows WHERE status = 'released'")
        completed = cursor.fetchone()[0]
        cursor.execute("SELECT COALESCE(SUM(amount_usd), 0) FROM real_escrows")
        volume = cursor.fetchone()[0]
        cursor.execute("SELECT COALESCE(SUM(fee_usd), 0) FROM real_escrows WHERE status = 'released'")
        fees = cursor.fetchone()[0]
        conn.close()
        return {'active_escrows': active, 'completed_escrows': completed, 'total_volume_usd': volume, 'total_fees_collected_usd': fees}