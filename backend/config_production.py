"""REAL Production Configuration for JULIUS VEIL."""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

class ProductionConfig:
    """Production configuration - all REAL settings."""
    
    # Database - PostgreSQL (REAL persistent storage)
    DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://julius:julius123@localhost:5432/julius")
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    
    # Tor Configuration (REAL Tor daemon)
    TOR_SOCKS_PORT = int(os.getenv("TOR_SOCKS_PORT", "9050"))
    TOR_CONTROL_PORT = int(os.getenv("TOR_CONTROL_PORT", "9051"))
    TOR_CONTROL_PASSWORD = os.getenv("TOR_CONTROL_PASSWORD", "julius_tor_pass")
    
    # Node Control - REAL SSH access
    NODE_SSH_KEY_PATH = Path(os.getenv("NODE_SSH_KEY_PATH", str(Path.home() / ".ssh/id_rsa")))
    NODE_CONTROL_TIMEOUT = int(os.getenv("NODE_CONTROL_TIMEOUT", "30"))
    
    # Revenue Configuration
    BASE_ROUTING_TOLL = float(os.getenv("BASE_ROUTING_TOLL", "0.0005"))  # 0.05 cents per KB
    ESCROW_STANDARD_FEE = float(os.getenv("ESCROW_STANDARD_FEE", "0.025"))  # 2.5%
    ESCROW_EXPRESS_FEE = float(os.getenv("ESCROW_EXPRESS_FEE", "0.045"))  # 4.5%
    ARBITRATION_FEE = float(os.getenv("ARBITRATION_FEE", "50000"))  # $50,000
    
    # Post-Quantum Security
    ML_KEM_ALGORITHM = "ML-KEM-768"  # NIST FIPS 203
    ENABLE_PQ_CIRCUITS = os.getenv("ENABLE_PQ_CIRCUITS", "true").lower() == "true"
    
    # Mixnet Configuration
    KATZENPOST_PROVIDER = os.getenv("KATZENPOST_PROVIDER", "")
    MIXNET_STRATA = int(os.getenv("MIXNET_STRATA", "3"))
    
    # Performance
    MAX_WORKERS = int(os.getenv("MAX_WORKERS", "4"))
    REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "30"))
    
    @classmethod
    def validate(cls):
        """Validate all required configuration is present."""
        required_vars = ["DATABASE_URL"]
        for var in required_vars:
            if not getattr(cls, var):
                raise ValueError(f"Missing required configuration: {var}")
        return True

config = ProductionConfig()