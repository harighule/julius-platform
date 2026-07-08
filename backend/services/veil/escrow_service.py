"""AXIOM Escrow Protocol - Manager Requirement: Central counterparty for shadow economy."""

import hashlib
import time
from datetime import datetime
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

class EscrowStatus(Enum):
    PENDING = "pending"
    RELEASED = "released"
    DISPUTED = "disputed"
    RESOLVED = "resolved"
    CANCELLED = "cancelled"

class DisputeOutcome(Enum):
    BUYER_WINS = "buyer_wins"
    SELLER_WINS = "seller_wins"
    SPLIT = "split"

@dataclass
class EscrowTransaction:
    escrow_id: str
    buyer_id: str
    seller_id: str
    amount_usd: float
    fee_percentage: float
    status: EscrowStatus
    created_at: str
    released_at: Optional[str] = None
    dispute_outcome: Optional[DisputeOutcome] = None


class AXIOMEscrowProtocol:
    """
    AXIOM Escrow Protocol - Central counterparty for dark web.
    
    Manager Requirements:
    - Standard escrow: 2-3% of transaction value
    - Express settlement (sub-1-hour): 4-5% premium
    - High-value dispute (>$1M): 1% + $50K retainer
    """
    
    STANDARD_FEE = 0.025      # 2.5%
    EXPRESS_FEE = 0.045       # 4.5%
    HIGH_VALUE_THRESHOLD = 1_000_000
    ARBITRATION_FEE = 50_000
    
    def __init__(self):
        self._escrows: Dict[str, EscrowTransaction] = {}
        self._total_escrow_volume = 0.0
        self._total_fees_collected = 0.0
    
    def create_escrow(self, buyer_id: str, seller_id: str, 
                      amount: float, express: bool = False) -> str:
        escrow_id = hashlib.sha3_256(
            f"{buyer_id}{seller_id}{amount}{time.time()}".encode()
        ).hexdigest()[:16]
        
        fee_pct = self.EXPRESS_FEE if express else self.STANDARD_FEE
        fee = amount * fee_pct
        
        self._escrows[escrow_id] = EscrowTransaction(
            escrow_id=escrow_id,
            buyer_id=buyer_id,
            seller_id=seller_id,
            amount_usd=amount,
            fee_percentage=fee_pct * 100,
            status=EscrowStatus.PENDING,
            created_at=datetime.utcnow().isoformat()
        )
        
        self._total_escrow_volume += amount
        return escrow_id
    
    def release_funds(self, escrow_id: str, delivery_proof: bytes) -> Tuple[bool, float]:
        if escrow_id not in self._escrows:
            return False, 0.0
        
        escrow = self._escrows[escrow_id]
        
        if self._verify_delivery_proof(delivery_proof):
            escrow.status = EscrowStatus.RELEASED
            escrow.released_at = datetime.utcnow().isoformat()
            
            fee = escrow.amount_usd * (escrow.fee_percentage / 100)
            self._total_fees_collected += fee
            
            return True, fee
        
        return False, 0.0
    
    def file_dispute(self, escrow_id: str, evidence: bytes) -> str:
        if escrow_id not in self._escrows:
            return "escrow_not_found"
        
        escrow = self._escrows[escrow_id]
        
        if escrow.amount_usd > self.HIGH_VALUE_THRESHOLD:
            arbitration_fee = (escrow.amount_usd * 0.01) + self.ARBITRATION_FEE
        else:
            arbitration_fee = escrow.amount_usd * 0.01
        
        escrow.status = EscrowStatus.DISPUTED
        self._total_fees_collected += arbitration_fee
        
        return f"dispute_filed_arbitration_fee_{arbitration_fee}"
    
    def resolve_dispute(self, escrow_id: str, outcome: DisputeOutcome, 
                        split_percentage: Optional[float] = None) -> Dict:
        if escrow_id not in self._escrows:
            return {"error": "escrow_not_found"}
        
        escrow = self._escrows[escrow_id]
        escrow.status = EscrowStatus.RESOLVED
        escrow.dispute_outcome = outcome
        
        result = {
            "escrow_id": escrow_id,
            "outcome": outcome.value,
            "resolved_at": datetime.utcnow().isoformat()
        }
        
        if outcome == DisputeOutcome.SPLIT and split_percentage:
            result["buyer_payout"] = escrow.amount_usd * (split_percentage / 100)
            result["seller_payout"] = escrow.amount_usd * ((100 - split_percentage) / 100)
        
        return result
    
    def _verify_delivery_proof(self, proof: bytes) -> bool:
        return len(proof) > 0
    
    def get_stats(self) -> Dict:
        return {
            "total_volume_usd": self._total_escrow_volume,
            "total_fees_collected_usd": self._total_fees_collected,
            "active_escrows": len([e for e in self._escrows.values() if e.status == EscrowStatus.PENDING]),
            "completed_escrows": len([e for e in self._escrows.values() if e.status == EscrowStatus.RELEASED])
        }


_escrow_service = None

def get_escrow_service() -> AXIOMEscrowProtocol:
    global _escrow_service
    if _escrow_service is None:
        _escrow_service = AXIOMEscrowProtocol()
    return _escrow_service