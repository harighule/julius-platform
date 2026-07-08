"""REAL Provider Mailbox Storage - Encrypted message storage.

This implements store-and-forward for offline clients.
Messages persist until retrieved by recipient.
"""

import sqlite3
import json
import os
import hashlib
from datetime import datetime
from typing import Optional, List, Dict, Any
from cryptography.fernet import Fernet


class RealProviderMailbox:
    """
    REAL mailbox storage for provider nodes.
    
    Features:
    - Messages stored encrypted
    - FIFO retrieval
    - Configurable retention period
    - Offline client support
    """
    
    def __init__(self, db_path: str = "E:/JULIUS/data/mailbox.db"):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                recipient_id TEXT NOT NULL,
                sender_id TEXT NOT NULL,
                ciphertext BLOB NOT NULL,
                encrypted_key BLOB NOT NULL,
                created_at TEXT NOT NULL,
                retrieved_at TEXT,
                ttl_seconds INTEGER DEFAULT 604800
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_recipient ON messages(recipient_id, retrieved_at)
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS providers (
                provider_id TEXT PRIMARY KEY,
                public_key TEXT NOT NULL,
                endpoint TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        conn.commit()
        conn.close()
    
    def store_message(self, recipient_id: str, sender_id: str, 
                      ciphertext: bytes, encrypted_key: bytes,
                      ttl_seconds: int = 604800) -> str:
        """
        Store an encrypted message in recipient's mailbox.
        
        Returns message ID.
        """
        message_id = hashlib.sha3_256(
            f"{recipient_id}{sender_id}{datetime.utcnow().isoformat()}".encode()
        ).hexdigest()[:16]
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO messages (id, recipient_id, sender_id, ciphertext, encrypted_key, created_at, ttl_seconds)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (message_id, recipient_id, sender_id, ciphertext, encrypted_key,
              datetime.utcnow().isoformat(), ttl_seconds))
        conn.commit()
        conn.close()
        
        return message_id
    
    def retrieve_messages(self, recipient_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Retrieve pending messages for recipient.
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, sender_id, ciphertext, encrypted_key, created_at
            FROM messages
            WHERE recipient_id = ? AND retrieved_at IS NULL
            ORDER BY created_at ASC
            LIMIT ?
        """, (recipient_id, limit))
        
        rows = cursor.fetchall()
        messages = [dict(row) for row in rows]
        
        # Mark as retrieved
        for msg in messages:
            cursor.execute("""
                UPDATE messages SET retrieved_at = ?
                WHERE id = ?
            """, (datetime.utcnow().isoformat(), msg['id']))
        
        conn.commit()
        conn.close()
        
        return messages
    
    def delete_old_messages(self):
        """Delete expired messages."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            DELETE FROM messages
            WHERE datetime(created_at, '+' || ttl_seconds || ' seconds') < datetime('now')
            OR retrieved_at IS NOT NULL
        """)
        
        conn.commit()
        conn.close()


# Global instance
_mailbox = None


def get_mailbox() -> RealProviderMailbox:
    global _mailbox
    if _mailbox is None:
        _mailbox = RealProviderMailbox()
    return _mailbox