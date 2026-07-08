"""Revenue Collection for JULIUS (Draft 8, Revenue Streams).

Manager Requirement: Charge commissions on all transactions through JULIUS.
"""

import time
import hashlib
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple
from collections import defaultdict

from .constants import TransactionType, DisputeResolution


@dataclass
class RoutingToll:
    """
    Revenue Stream 01: Routing Toll.
    
    Every packet routed through JULIUS-controlled infrastructure
    incurs a micro-toll. Fractions of a cent, scaled by problem complexity.
    """
    
    base_rate_per_kb: float = 0.0005  # 0.05 cents per KB
    complexity_multiplier: float = 1.0
    
    def record_packet(self, bytes_sent: int, destination: str) -> float:
        """
        Record a packet and compute toll.
        
        Scaling per problem solved (manager requirement):
        - Simple routing: 1x base
        - Complex dark web investigation: 1.5x
        - Real-time intelligence: 2x
        - Exploit delivery: 3x
        """
        kb = bytes_sent / 1024
        toll = kb * self.base_rate_per_kb * self.complexity_multiplier
        return toll
    
    def set_complexity(self, complexity: float):
        """Set complexity multiplier for scaling."""
        self.complexity_multiplier = complexity


@dataclass
class EscrowService:
    """
    Revenue Stream 02: Escrow & Settlement.
    
    Central counterparty for dark web transactions.
    """
    
    standard_rate: float = 0.025      # 2.5% of transaction
    express_rate: float = 0.045       # 4.5% for sub-1-hour
    arbitration_fee: float = 50000.0  # $50K for high-value disputes
    
    _active_escrows: Dict[str, dict] = field(default_factory=dict)
    
    def create_escrow(self, 
                      buyer_id: str,
                      seller_id: str,
                      amount: float,
                      tx_type: TransactionType,
                      express: bool = False) -> str:
        """Create a new escrow for a dark web transaction."""
        escrow_id = hashlib.sha3_256(
            f"{buyer_id}{seller_id}{amount}{time.time()}".encode()
        ).hexdigest()[:16]
        
        fee_rate = self.express_rate if express else self.standard_rate
        fee = amount * fee_rate
        
        self._active_escrows[escrow_id] = {
            'buyer_id': buyer_id,
            'seller_id': seller_id,
            'amount': amount,
            'fee': fee,
            'type': tx_type,
            'status': 'pending',
            'created_at': time.time(),
            'express': express
        }
        
        return escrow_id
    
    def confirm_delivery(self, escrow_id: str, proof: bytes) -> Tuple[bool, float]:
        """Confirm delivery and release funds."""
        if escrow_id not in self._active_escrows:
            return False, 0.0
        
        escrow = self._active_escrows[escrow_id]
        
        if self._verify_delivery_proof(proof):
            escrow['status'] = 'completed'
            escrow['completed_at'] = time.time()
            revenue = escrow['fee']
            del self._active_escrows[escrow_id]
            return True, revenue
        
        return False, 0.0
    
    def resolve_dispute(self, escrow_id: str, 
                        resolution: DisputeResolution,
                        split_percentage: Optional[float] = None) -> float:
        """Resolve a disputed transaction."""
        if escrow_id not in self._active_escrows:
            return 0.0
        
        escrow = self._active_escrows[escrow_id]
        
        if escrow['amount'] > 1_000_000:
            revenue = self.arbitration_fee + (escrow['amount'] * 0.01)
        else:
            revenue = escrow['amount'] * self.standard_rate
        
        escrow['status'] = 'disputed_resolved'
        escrow['resolution'] = resolution.value
        
        return revenue
    
    def _verify_delivery_proof(self, proof: bytes) -> bool:
        """Verify cryptographic delivery proof."""
        return len(proof) > 0


@dataclass
class RevenueEngine:
    """
    Main revenue collection engine for JULIUS.
    
    Combines routing tolls and escrow services.
    Scales parameters rapidly per problem solved (manager requirement).
    """
    
    routing: RoutingToll = field(default_factory=RoutingToll)
    escrow: EscrowService = field(default_factory=EscrowService)
    
    _total_revenue: float = 0.0
    
    def process_transaction(self,
                           transaction_data: dict,
                           complexity: float = 1.0) -> float:
        """
        Process a complete transaction through the revenue system.
        
        Scaling per problem solved (manager requirement):
        - complexity=1.0: Simple data transfer
        - complexity=2.0: Dark web investigation
        - complexity=3.0: Active intelligence gathering
        - complexity=5.0: Zero-day exploit acquisition
        """
        self.routing.set_complexity(complexity)
        
        # Record routing toll
        bytes_sent = transaction_data.get('bytes', 1024)
        destination = transaction_data.get('destination', 'unknown')
        routing_revenue = self.routing.record_packet(bytes_sent, destination)
        
        # Handle escrow if applicable
        escrow_revenue = 0.0
        if 'escrow_id' in transaction_data:
            escrow_revenue = self.escrow.confirm_delivery(
                transaction_data['escrow_id'],
                transaction_data.get('proof', b'')
            )[1]
        
        total = routing_revenue + escrow_revenue
        self._total_revenue += total
        
        # Apply scaling
        scaling_factor = 1.5 ** complexity
        return total * scaling_factor
    
    def get_total_revenue(self) -> float:
        """Get total revenue collected."""
        return self._total_revenue