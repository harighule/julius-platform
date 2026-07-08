"""REAL Descriptor Sharding - Split HS descriptor into 5 shards."""

import json
from typing import List, Tuple


class RealDescriptorSharding:
    """
    REAL descriptor sharding using Shamir's Secret Sharing.
    
    HS descriptor is split into 5 shards, each stored on different HSDir.
    Client retrieves all 5 to reconstruct.
    """
    
    def shard_descriptor(self, descriptor: dict) -> List[Tuple[int, bytes]]:
        """
        Split descriptor into 5 shards (5-of-5 required).
        """
        # Serialize descriptor to JSON
        descriptor_bytes = json.dumps(descriptor, sort_keys=True).encode('utf-8')
        
        # Split using Shamir
        from .rendezvous_real import ShamirSecretSharing
        return ShamirSecretSharing.split_secret(descriptor_bytes, n=5, k=5)
    
    def reconstruct_descriptor(self, shares: List[Tuple[int, bytes]]) -> dict:
        """
        Reconstruct descriptor from all 5 shards.
        """
        from .rendezvous_real import ShamirSecretSharing
        
        if len(shares) != 5:
            raise ValueError("Need exactly 5 shards to reconstruct")
        
        descriptor_bytes = ShamirSecretSharing.reconstruct_secret(shares)
        return json.loads(descriptor_bytes.decode('utf-8'))


# Global instance
_sharding = None


def get_sharding() -> RealDescriptorSharding:
    global _sharding
    if _sharding is None:
        _sharding = RealDescriptorSharding()
    return _sharding