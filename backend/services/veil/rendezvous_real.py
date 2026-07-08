"""REAL Shamir Secret Sharing - Fixed version."""

import secrets
import hashlib
from typing import List, Tuple


class ShamirSecretSharing:
    """
    REAL Shamir's Secret Sharing for k-of-n threshold.
    """
    
    @staticmethod
    def _int_from_bytes(data: bytes) -> int:
        """Convert bytes to integer (handles any length)."""
        return int.from_bytes(data, 'big')
    
    @staticmethod
    def _int_to_bytes(value: int, length: int) -> bytes:
        """Convert integer to bytes of specified length."""
        return value.to_bytes(length, 'big')
    
    @staticmethod
    def _eval_poly(coefficients: List[int], x: int, prime: int) -> int:
        """Evaluate polynomial at x over finite field."""
        result = 0
        for coeff in reversed(coefficients):
            result = (result * x + coeff) % prime
        return result
    
    @staticmethod
    def split_secret(secret: bytes, n: int, k: int) -> List[Tuple[int, bytes]]:
        """
        Split secret into n shares, requiring k to reconstruct.
        """
        # Use a large prime for finite field arithmetic
        prime = 2**127 - 1  # Mersenne prime
        
        # Convert secret to integer
        secret_int = ShamirSecretSharing._int_from_bytes(secret)
        
        # Generate random coefficients for polynomial of degree k-1
        coeffs = [secret_int]
        for _ in range(k - 1):
            coeffs.append(secrets.randbelow(prime))
        
        # Create shares
        shares = []
        for x in range(1, n + 1):
            y = ShamirSecretSharing._eval_poly(coeffs, x, prime)
            # Convert y to bytes of appropriate length
            y_bytes = y.to_bytes((y.bit_length() + 7) // 8 or 1, 'big')
            shares.append((x, y_bytes))
        
        return shares
    
    @staticmethod
    def reconstruct_secret(shares: List[Tuple[int, bytes]]) -> bytes:
        """
        Reconstruct secret from k shares using Lagrange interpolation.
        """
        # Use same prime as split
        prime = 2**127 - 1
        
        # Convert shares to integers
        int_shares = [(x, int.from_bytes(y, 'big')) for (x, y) in shares]
        
        # Lagrange interpolation
        secret = 0
        for i, (x_i, y_i) in enumerate(int_shares):
            # Compute Lagrange basis polynomial
            numerator = 1
            denominator = 1
            for j, (x_j, _) in enumerate(int_shares):
                if i != j:
                    numerator = (numerator * (-x_j)) % prime
                    denominator = (denominator * (x_i - x_j)) % prime
            # Modular inverse of denominator
            lagrange = (numerator * pow(denominator, -1, prime)) % prime
            secret = (secret + y_i * lagrange) % prime
        
        # Convert back to bytes
        secret_bytes = secret.to_bytes((secret.bit_length() + 7) // 8 or 1, 'big')
        return secret_bytes


def test_shamir():
    """Test the implementation."""
    secret = b"VEIL_TEST_SECRET_12345"
    print(f"Original secret: {secret}")
    
    shares = ShamirSecretSharing.split_secret(secret, 5, 5)
    print(f"Created {len(shares)} shares")
    
    reconstructed = ShamirSecretSharing.reconstruct_secret(shares[:5])
    print(f"Reconstructed: {reconstructed}")
    
    assert secret == reconstructed
    print("✅ Test passed!")


if __name__ == "__main__":
    test_shamir()