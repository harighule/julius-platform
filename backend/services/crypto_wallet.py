"""
CRYPTO WALLET INTEGRATION - REAL IMPLEMENTATION
MetaMask / Ethereum / BSC
"""

import os
import json
import time
import hashlib
import logging
import sqlite3
from typing import Dict, Tuple, Optional, Any, List
from dataclasses import dataclass
from datetime import datetime

import requests

# ============================================================================
# Lazy web3 / eth_account helpers
# ============================================================================

def _get_Web3():
    """Lazy-load Web3 to avoid ImportError when web3 is not installed."""
    try:
        from web3 import Web3  # noqa: PLC0415
        return Web3
    except ImportError:
        return None


def _get_Account():
    """Lazy-load eth_account.Account to avoid ImportError when not installed."""
    try:
        from eth_account import Account  # noqa: PLC0415
        return Account
    except ImportError:
        return None


def _get_poa_middleware():
    """Lazy-load POA middleware; returns None when unavailable."""
    try:
        from web3.middleware import ExtraDataToPOAMiddleware  # noqa: PLC0415
        return ExtraDataToPOAMiddleware
    except ImportError:
        pass
    try:
        from web3.middleware import geth_poa_middleware  # noqa: PLC0415
        return geth_poa_middleware
    except ImportError:
        return None

logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURATION
# ============================================================================

# Database Path
import pathlib as _pathlib

# Resolve DB path relative to this file so it works on any machine:
#   backend/services/crypto_wallet.py  ->  parents[2] == project root
_PROJECT_ROOT = _pathlib.Path(__file__).resolve().parents[2]
DB_PATH = str(_PROJECT_ROOT / "data" / "julius.db")

# Network Configuration
ETH_MAINNET_RPC = "https://mainnet.infura.io/v3/YOUR_INFURA_KEY"
BSC_MAINNET_RPC = "https://bsc-dataseed.binance.org/"
POLYGON_MAINNET_RPC = "https://polygon-rpc.com/"

ETH_GOERLI_RPC = "https://goerli.infura.io/v3/YOUR_INFURA_KEY"
BSC_TESTNET_RPC = "https://data-seed-prebsc-1-s1.binance.org:8545/"


# ============================================================================
# DATABASE HELPER
# ============================================================================

def get_db_connection():
    """Get direct SQLite connection to the database."""
    try:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        return None


def close_db_connection(conn):
    """Safely close database connection."""
    if conn:
        try:
            conn.close()
        except:
            pass


# ============================================================================
# WALLET SERVICE
# ============================================================================

@dataclass
class WalletTransaction:
    tx_hash: str
    from_address: str
    to_address: str
    amount_eth: float
    amount_usd: float
    fee_percentage: float
    fee_amount: float
    status: str
    timestamp: str
    escrow_id: str
    block_number: int
    gas_used: int
    gas_price: float


@dataclass
class EscrowPayment:
    escrow_id: str
    buyer_address: str
    seller_address: str
    amount_eth: float
    amount_usd: float
    fee_percentage: float
    fee_usd: float
    status: str
    created_at: str
    release_hash: Optional[str] = None


class RealCryptoWallet:
    """REAL crypto wallet integration - MetaMask / Web3"""
    
    def __init__(self, network: str = "bsc", test_mode: bool = False):
        self.network = network
        self.test_mode = test_mode
        self.web3 = None
        self.account = None
        self.is_connected = False
        
        if network == "ethereum":
            self.rpc_url = ETH_GOERLI_RPC if test_mode else ETH_MAINNET_RPC
            self.chain_id = 5 if test_mode else 1
        elif network == "bsc":
            self.rpc_url = BSC_TESTNET_RPC if test_mode else BSC_MAINNET_RPC
            self.chain_id = 97 if test_mode else 56
        elif network == "polygon":
            self.rpc_url = "https://rpc-mumbai.maticvigil.com/" if test_mode else POLYGON_MAINNET_RPC
            self.chain_id = 80001 if test_mode else 137
        else:
            raise ValueError(f"Unknown network: {network}")
        
        self._connect()
    
    def _connect(self) -> bool:
        Web3 = _get_Web3()
        if Web3 is None:
            logger.error("web3 is not installed; blockchain connectivity unavailable")
            return False
        try:
            self.web3 = Web3(Web3.HTTPProvider(self.rpc_url))

            poa_mw = _get_poa_middleware()
            if self.network in ["bsc", "polygon"] and poa_mw is not None:
                try:
                    self.web3.middleware_onion.inject(poa_mw, layer=0)
                except Exception as e:
                    logger.warning(f"Could not inject POA middleware: {e}")

            if not self.web3.is_connected():
                logger.error("Failed to connect to blockchain")
                return False

            self.is_connected = True
            logger.info(f"Connected to {self.network} network (chain_id: {self.chain_id})")
            logger.info(f"Block number: {self.web3.eth.block_number}")
            return True
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            return False
    
    def set_account(self, private_key: str) -> bool:
        Account = _get_Account()
        if Account is None:
            logger.error("eth_account is not installed")
            return False
        try:
            self.account = Account.from_key(private_key)
            logger.info(f"Account loaded: {self.account.address}")
            return True
        except Exception as e:
            logger.error(f"Account loading failed: {e}")
            return False
    
    def get_balance(self, address: Optional[str] = None) -> Dict[str, Any]:
        if not self.is_connected:
            return {"error": "Not connected"}
        
        addr = address or (self.account.address if self.account else None)
        if not addr:
            return {"error": "No address provided"}
        
        try:
            balance_wei = self.web3.eth.get_balance(addr)
            balance_eth = self.web3.from_wei(balance_wei, 'ether')
            return {
                "address": addr,
                "balance_wei": balance_wei,
                "balance_eth": float(balance_eth),
                "network": self.network,
                "chain_id": self.chain_id
            }
        except Exception as e:
            return {"error": str(e)}
    
    def send_transaction(
        self,
        to_address: str,
        amount_eth: float,
        escrow_id: str,
        private_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Send REAL crypto transaction - compatible with all web3.py versions.
        """
        if not self.is_connected:
            return {"success": False, "error": "Not connected"}
        
        if not self.account and not private_key:
            return {"success": False, "error": "No account loaded"}

        Account = _get_Account()
        if Account is None:
            return {"success": False, "error": "eth_account is not installed"}

        key = private_key or self.account._private_key.hex()
        account = Account.from_key(key)
        
        try:
            nonce = self.web3.eth.get_transaction_count(account.address)
            gas_price = self.web3.eth.gas_price
            gas_estimate = 21000
            
            tx = {
                'nonce': nonce,
                'to': to_address,
                'value': self.web3.to_wei(amount_eth, 'ether'),
                'gas': gas_estimate,
                'gasPrice': gas_price,
                'chainId': self.chain_id
            }
            
            # Sign transaction
            signed_tx = account.sign_transaction(tx)
            
            # Get raw transaction bytes - different ways for different web3 versions
            raw_tx_bytes = None
            
            # Try different methods
            if hasattr(signed_tx, 'rawTransaction'):
                raw_tx_bytes = signed_tx.rawTransaction
            elif hasattr(signed_tx, 'raw_transaction'):
                raw_tx_bytes = signed_tx.raw_transaction
            elif hasattr(signed_tx, '_raw_transaction'):
                raw_tx_bytes = signed_tx._raw_transaction
            else:
                # For some versions, convert to bytes
                raw_tx_bytes = bytes(signed_tx)
            
            # If raw_tx_bytes is still None, try serialization
            if raw_tx_bytes is None:
                try:
                    # For eth_account v0.5+
                    raw_tx_bytes = signed_tx.rawTransaction
                except:
                    # Last resort
                    raw_tx_bytes = signed_tx.serialize()
            
            # Send transaction
            try:
                tx_hash = self.web3.eth.send_raw_transaction(raw_tx_bytes)
            except AttributeError:
                tx_hash = self.web3.eth.sendRawTransaction(raw_tx_bytes)
            
            # Convert to hex string
            if hasattr(tx_hash, 'hex'):
                tx_hash_hex = '0x' + tx_hash.hex()
            else:
                tx_hash_hex = '0x' + bytes(tx_hash).hex()
            
            logger.info(f"Transaction sent: {tx_hash_hex}")
            
            # Wait for confirmation
            receipt = self.web3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            
            block_number = int(receipt['blockNumber'])
            gas_used = int(receipt['gasUsed'])
            status = int(receipt['status'])
            
            tx_data = {
                "tx_hash": tx_hash_hex,
                "block_number": block_number,
                "gas_used": gas_used,
                "status": "confirmed" if status == 1 else "failed"
            }
            
            self._save_transaction({
                "tx_hash": tx_hash_hex,
                "from_address": account.address,
                "to_address": to_address,
                "amount_eth": amount_eth,
                "escrow_id": escrow_id,
                "status": tx_data["status"],
                "block_number": block_number,
                "gas_used": gas_used,
                "gas_price": float(gas_price)
            })
            
            return {
                "success": True,
                "tx_hash": tx_hash_hex,
                "block_number": block_number,
                "status": tx_data["status"],
                "gas_used": gas_used,
                "explorer_url": self._get_explorer_url(tx_hash_hex)
            }
            
        except Exception as e:
            logger.error(f"Transaction failed: {e}")
            return {"success": False, "error": str(e)}
    
    def _save_transaction(self, tx_data: dict):
        """Save transaction to database."""
        conn = None
        try:
            conn = get_db_connection()
            if conn is None:
                logger.error("No database connection")
                return
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS crypto_transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tx_hash TEXT NOT NULL,
                    from_address TEXT NOT NULL,
                    to_address TEXT NOT NULL,
                    amount_eth REAL NOT NULL,
                    escrow_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    block_number INTEGER,
                    gas_used INTEGER,
                    gas_price REAL,
                    created_at TEXT NOT NULL
                )
            """)
            conn.commit()
            
            conn.execute("""
                INSERT OR REPLACE INTO crypto_transactions 
                (tx_hash, from_address, to_address, amount_eth, escrow_id, status, block_number, gas_used, gas_price, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                tx_data.get('tx_hash'),
                tx_data.get('from_address'),
                tx_data.get('to_address'),
                tx_data.get('amount_eth'),
                tx_data.get('escrow_id'),
                tx_data.get('status'),
                tx_data.get('block_number'),
                tx_data.get('gas_used'),
                tx_data.get('gas_price'),
                datetime.now().isoformat()
            ))
            conn.commit()
            logger.info(f"Transaction saved: {tx_data.get('tx_hash')}")
            
        except Exception as e:
            logger.error(f"Failed to save transaction: {e}")
        finally:
            close_db_connection(conn)
    
    def _get_explorer_url(self, tx_hash: str) -> str:
        explorers = {
            "ethereum": f"https://etherscan.io/tx/{tx_hash}",
            "bsc": f"https://bscscan.com/tx/{tx_hash}",
            "polygon": f"https://polygonscan.com/tx/{tx_hash}"
        }
        return explorers.get(self.network, "")
    
    def get_transaction_status(self, tx_hash: str) -> Dict[str, Any]:
        try:
            receipt = self.web3.eth.get_transaction_receipt(tx_hash)
            if receipt:
                return {
                    "confirmed": int(receipt['status']) == 1,
                    "block_number": int(receipt['blockNumber']),
                    "gas_used": int(receipt['gasUsed']),
                    "status": "confirmed" if int(receipt['status']) == 1 else "failed"
                }
            return {"confirmed": False, "status": "pending"}
        except Exception as e:
            return {"error": str(e), "status": "unknown"}


# ============================================================================
# ESCROW WITH CRYPTO
# ============================================================================

class CryptoEscrowService:
    """REAL escrow service with crypto payments"""
    
    def __init__(self, wallet: RealCryptoWallet):
        self.wallet = wallet
        self._init_database()
    
    def _get_conn(self):
        return get_db_connection()
    
    def _init_database(self):
        conn = None
        try:
            conn = self._get_conn()
            if conn is None:
                return
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS crypto_escrow (
                    escrow_id TEXT PRIMARY KEY,
                    buyer_address TEXT NOT NULL,
                    seller_address TEXT NOT NULL,
                    amount_eth REAL NOT NULL,
                    amount_usd REAL NOT NULL,
                    fee_percentage REAL NOT NULL,
                    fee_usd REAL NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    released_at TEXT,
                    release_hash TEXT,
                    buyer_tx_hash TEXT,
                    seller_tx_hash TEXT
                )
            """)
            conn.commit()
            logger.info("✅ crypto_escrow table ready")
        except Exception as e:
            logger.error(f"Failed to create crypto_escrow table: {e}")
        finally:
            close_db_connection(conn)
    
    def create_escrow(
        self,
        buyer_address: str,
        seller_address: str,
        amount_eth: float,
        amount_usd: float,
        express: bool = False
    ) -> Dict[str, Any]:
        import secrets
        escrow_id = secrets.token_hex(16)
        fee_pct = 4.5 if express else 2.5
        fee_usd = amount_usd * (fee_pct / 100)
        
        conn = None
        try:
            conn = self._get_conn()
            if conn is None:
                return {"success": False, "error": "Database connection failed"}
            
            conn.execute("""
                INSERT INTO crypto_escrow 
                (escrow_id, buyer_address, seller_address, amount_eth, amount_usd, 
                 fee_percentage, fee_usd, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                escrow_id, buyer_address, seller_address,
                amount_eth, amount_usd, fee_pct, fee_usd,
                "pending", datetime.now().isoformat()
            ))
            conn.commit()
        except Exception as e:
            logger.error(f"Failed to create escrow: {e}")
            return {"success": False, "error": str(e)}
        finally:
            close_db_connection(conn)
        
        return {
            "success": True,
            "escrow_id": escrow_id,
            "buyer_address": buyer_address,
            "seller_address": seller_address,
            "amount_eth": amount_eth,
            "amount_usd": amount_usd,
            "fee_percentage": fee_pct,
            "fee_usd": fee_usd,
            "status": "pending"
        }
    
    def release_funds(
        self,
        escrow_id: str,
        seller_private_key: str,
        delivery_proof: str
    ) -> Dict[str, Any]:
        conn = None
        try:
            conn = self._get_conn()
            if conn is None:
                return {"success": False, "error": "Database connection failed"}
            
            row = conn.execute(
                "SELECT * FROM crypto_escrow WHERE escrow_id = ?",
                (escrow_id,)
            ).fetchone()
        except Exception as e:
            logger.error(f"Failed to fetch escrow: {e}")
            close_db_connection(conn)
            return {"success": False, "error": str(e)}
        
        if not row:
            close_db_connection(conn)
            return {"success": False, "error": "Escrow not found"}
        
        escrow = dict(row)
        
        if escrow['status'] != "pending":
            close_db_connection(conn)
            return {"success": False, "error": f"Escrow status: {escrow['status']}"}
        
        fee_eth = escrow['amount_eth'] * (escrow['fee_percentage'] / 100)
        seller_amount = escrow['amount_eth'] - fee_eth
        
        tx_result = self.wallet.send_transaction(
            to_address=escrow['seller_address'],
            amount_eth=seller_amount,
            escrow_id=escrow_id,
            private_key=seller_private_key
        )
        
        if tx_result['success']:
            try:
                conn2 = self._get_conn()
                if conn2:
                    conn2.execute("""
                        UPDATE crypto_escrow 
                        SET status = 'released', released_at = ?, seller_tx_hash = ?
                        WHERE escrow_id = ?
                    """, (datetime.now().isoformat(), tx_result['tx_hash'], escrow_id))
                    conn2.commit()
                    close_db_connection(conn2)
                    
                    try:
                        from .database.manager import get_db
                        main_db = get_db()
                        if hasattr(main_db, 'add_revenue'):
                            main_db.add_revenue("escrow_crypto", escrow['fee_usd'], 1.0, escrow_id)
                    except Exception as e:
                        logger.warning(f"Revenue tracking failed: {e}")
            except Exception as e:
                logger.error(f"Failed to update escrow: {e}")
        
        close_db_connection(conn)
        return tx_result
    
    def get_escrow(self, escrow_id: str) -> Optional[Dict[str, Any]]:
        conn = None
        try:
            conn = self._get_conn()
            if conn is None:
                return None
            
            row = conn.execute(
                "SELECT * FROM crypto_escrow WHERE escrow_id = ?",
                (escrow_id,)
            ).fetchone()
            if row:
                return dict(row)
            return None
        except Exception as e:
            logger.error(f"Failed to get escrow: {e}")
            return None
        finally:
            close_db_connection(conn)
    
    def get_all_escrows(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        conn = None
        try:
            conn = self._get_conn()
            if conn is None:
                return []
            
            if status:
                rows = conn.execute(
                    "SELECT * FROM crypto_escrow WHERE status = ? ORDER BY created_at DESC",
                    (status,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM crypto_escrow ORDER BY created_at DESC"
                ).fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to get escrows: {e}")
            return []
        finally:
            close_db_connection(conn)


# ============================================================================
# METAMASK CONNECTION
# ============================================================================

class MetaMaskIntegration:
    """REAL MetaMask integration via Web3"""
    
    def __init__(self, private_key: str = None, network: str = "bsc"):
        self.wallet = RealCryptoWallet(network=network)
        if private_key:
            self.wallet.set_account(private_key)
        self.is_connected = self.wallet.is_connected
    
    def get_balance(self) -> Dict[str, Any]:
        return self.wallet.get_balance()
    
    def sign_and_send(self, to_address: str, amount_eth: float, escrow_id: str = "") -> Dict:
        return self.wallet.send_transaction(to_address, amount_eth, escrow_id)
    
    def get_network_info(self) -> Dict[str, Any]:
        return {
            "network": self.wallet.network,
            "chain_id": self.wallet.chain_id,
            "rpc_url": self.wallet.rpc_url,
            "connected": self.wallet.is_connected,
            "block_number": self.wallet.web3.eth.block_number if self.wallet.web3 else None
        }