"""REAL Database Manager with connection pooling and async support."""

import asyncpg
from typing import Optional, Dict, Any, List
from datetime import datetime
import json
import os


class RealDatabaseManager:
    """REAL PostgreSQL database manager."""
    
    def __init__(self, dsn: str):
        self.dsn = dsn
        self._pool: Optional[asyncpg.Pool] = None
    
    async def initialize(self):
        """Create connection pool and initialize tables."""
        self._pool = await asyncpg.create_pool(
            self.dsn,
            min_size=2,
            max_size=20,
            command_timeout=60
        )
        
        await self._create_tables()
    
    async def _create_tables(self):
        """Create all tables if they don't exist."""
        async with self._pool.acquire() as conn:
            # Escrows table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS escrows (
                    id TEXT PRIMARY KEY,
                    buyer_id TEXT NOT NULL,
                    seller_id TEXT NOT NULL,
                    amount_usd DECIMAL(20,2) NOT NULL,
                    fee_percentage DECIMAL(5,2) NOT NULL,
                    fee_usd DECIMAL(20,2) NOT NULL,
                    status TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL,
                    released_at TIMESTAMP,
                    delivery_hash TEXT,
                    buyer_signature TEXT,
                    seller_signature TEXT,
                    dispute_outcome TEXT,
                    arbitration_fee DECIMAL(20,2)
                )
            """)
            
            # Controlled nodes table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS controlled_nodes (
                    node_id TEXT PRIMARY KEY,
                    node_type TEXT NOT NULL,
                    host TEXT NOT NULL,
                    port INTEGER NOT NULL,
                    control_method TEXT NOT NULL,
                    status TEXT NOT NULL,
                    controlled_at TIMESTAMP NOT NULL,
                    last_heartbeat TIMESTAMP,
                    config JSONB,
                    ssh_key_fingerprint TEXT
                )
            """)
            
            # Revenue transactions table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS revenue_transactions (
                    id TEXT PRIMARY KEY,
                    transaction_type TEXT NOT NULL,
                    amount_usd DECIMAL(20,6) NOT NULL,
                    complexity DECIMAL(10,2),
                    scaling_multiplier DECIMAL(10,2),
                    destination TEXT,
                    created_at TIMESTAMP NOT NULL
                )
            """)
            
            # Investigations table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS investigations (
                    id TEXT PRIMARY KEY,
                    query TEXT NOT NULL,
                    refined_query TEXT,
                    status TEXT NOT NULL,
                    results_found INTEGER,
                    pages_scraped INTEGER,
                    analysis TEXT,
                    complexity DECIMAL(10,2),
                    revenue_collected DECIMAL(20,6),
                    created_at TIMESTAMP NOT NULL,
                    completed_at TIMESTAMP
                )
            """)
            
            # Create indexes
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_escrows_status ON escrows(status)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_escrows_created ON escrows(created_at)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_controlled_nodes_status ON controlled_nodes(status)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_revenue_created ON revenue_transactions(created_at)")
    
    async def create_escrow(self, escrow_data: Dict[str, Any]) -> str:
        """Create a new escrow record."""
        async with self._pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO escrows (
                    id, buyer_id, seller_id, amount_usd, fee_percentage, fee_usd,
                    status, created_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """,
                escrow_data['id'],
                escrow_data['buyer_id'],
                escrow_data['seller_id'],
                escrow_data['amount_usd'],
                escrow_data['fee_percentage'],
                escrow_data['fee_usd'],
                escrow_data['status'],
                escrow_data['created_at']
            )
        return escrow_data['id']
    
    async def get_escrow(self, escrow_id: str) -> Optional[Dict[str, Any]]:
        """Get escrow by ID."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM escrows WHERE id = $1", escrow_id)
            if row:
                return dict(row)
        return None
    
    async def update_escrow(self, escrow_id: str, updates: Dict[str, Any]):
        """Update escrow record."""
        set_clause = ", ".join([f"{k} = ${i+2}" for i, k in enumerate(updates.keys())])
        values = [escrow_id] + list(updates.values())
        async with self._pool.acquire() as conn:
            await conn.execute(f"UPDATE escrows SET {set_clause} WHERE id = $1", *values)
    
    async def get_escrow_stats(self) -> Dict[str, Any]:
        """Get escrow statistics."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT 
                    COALESCE(SUM(amount_usd), 0) as total_volume,
                    COALESCE(SUM(fee_usd), 0) as total_fees,
                    COUNT(CASE WHEN status = 'pending' THEN 1 END) as active,
                    COUNT(CASE WHEN status = 'released' THEN 1 END) as completed
                FROM escrows
            """)
            return {
                "total_volume_usd": float(row['total_volume']),
                "total_fees_collected_usd": float(row['total_fees']),
                "active_escrows": row['active'],
                "completed_escrows": row['completed']
            }
    
    async def add_controlled_node(self, node_data: Dict[str, Any]):
        """Add a controlled node to database."""
        async with self._pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO controlled_nodes (
                    node_id, node_type, host, port, control_method, status,
                    controlled_at, config
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (node_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    last_heartbeat = NOW(),
                    config = EXCLUDED.config
            """,
                node_data['node_id'],
                node_data['node_type'],
                node_data['host'],
                node_data['port'],
                node_data['control_method'],
                node_data['status'],
                datetime.utcnow(),
                json.dumps(node_data.get('config', {}))
            )
    
    async def get_controlled_nodes(self) -> List[Dict[str, Any]]:
        """Get all controlled nodes."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM controlled_nodes WHERE status = 'controlled'")
            return [dict(row) for row in rows]
    
    async def add_revenue_transaction(self, tx_data: Dict[str, Any]):
        """Add revenue transaction record."""
        async with self._pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO revenue_transactions (
                    id, transaction_type, amount_usd, complexity, scaling_multiplier,
                    destination, created_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
                tx_data['id'],
                tx_data['transaction_type'],
                tx_data['amount_usd'],
                tx_data.get('complexity', 1.0),
                tx_data.get('scaling_multiplier', 1.0),
                tx_data.get('destination'),
                datetime.utcnow()
            )
    
    async def get_total_revenue(self) -> float:
        """Get total revenue collected."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT COALESCE(SUM(amount_usd), 0) as total FROM revenue_transactions")
            return float(row['total']) if row else 0.0
    
    async def close(self):
        """Close database connection pool."""
        if self._pool:
            await self._pool.close()


# Global instance
_db_manager: Optional[RealDatabaseManager] = None


async def get_db_manager() -> RealDatabaseManager:
    global _db_manager
    if _db_manager is None:
        from ..config_production import config
        _db_manager = RealDatabaseManager(config.DATABASE_URL)
        await _db_manager.initialize()
    return _db_manager