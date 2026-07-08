"""REAL JULIUS VEIL Production Server."""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import darkweb_real, scanner_real
from database.manager_real import get_db_manager
from config_production import config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan manager for startup/shutdown."""
    # Startup
    logger.info("Starting JULIUS VEIL Production Server...")
    logger.info(f"Post-Quantum Crypto: {config.ML_KEM_ALGORITHM}")
    logger.info(f"Database: {config.DATABASE_URL.split('@')[-1]}")
    
    # Initialize database
    db = await get_db_manager()
    logger.info("Database connected")
    
    yield
    
    # Shutdown
    logger.info("Shutting down JULIUS VEIL...")
    await db.close()


app = FastAPI(
    title="JULIUS VEIL Production API",
    description="Maximum Anonymity Hybrid System with Post-Quantum Cryptography",
    version="2.0.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(darkweb_real.router)
# app.include_router(scanner_real.router)  # Add when ready


@app.get("/")
async def root():
    return {
        "service": "JULIUS VEIL",
        "version": "2.0.0-production",
        "status": "operational",
        "features": [
            "post-quantum-crypto (ML-KEM-768)",
            "tor-anonymity",
            "escrow-service (2.5%/4.5%)",
            "revenue-tracking",
            "database-persistence"
        ]
    }


@app.get("/health")
async def health():
    db = await get_db_manager()
    stats = await db.get_escrow_stats()
    
    return {
        "status": "healthy",
        "database": "connected",
        "pq_crypto": "available",
        "active_escrows": stats['active_escrows'],
        "total_revenue": await db.get_total_revenue()
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main_production:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        workers=config.MAX_WORKERS
    )